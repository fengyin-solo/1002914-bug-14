<template>
  <section class="page" data-module="boiler">
    <header class="page-head">
      <div>
        <h2>锅炉管理管理</h2>
        <p class="page-desc">维护锅炉，围绕锅炉编号、锅炉型号、额定蒸发量、工作压力做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记锅炉</button>
        <button class="btn" type="button" @click="exportRows">导出锅炉管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>锅炉编号/型号</span>
        <input v-model="filters.keyword" placeholder="按锅炉编号或型号检索" />
      </label>
      <label class="filter-item">
        <span>司炉人员</span>
        <input v-model="filters.operator" placeholder="按司炉人员检索" />
      </label>
      <label class="filter-item">
        <span>锅炉状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRunAction(action, row)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的锅炉数据，可调整筛选条件或先登记锅炉</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条锅炉管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记锅炉</h3>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <label v-for="field in formFields" :key="field" class="filter-item">
          <span>{{ field }}{{ requiredFields.includes(field) ? '（必填）' : '' }}</span>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '保存' }}
          </button>
          <button class="btn ghost" type="button" :disabled="submitting" @click="closeCreate">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/boiler'
const columns = ["锅炉编号", "锅炉型号", "额定蒸发量", "工作压力", "燃料类型", "使用年限", "司炉人员", "锅炉状态"]
const formFields = ["锅炉编号", "锅炉型号", "额定蒸发量", "工作压力", "燃料类型", "使用年限", "司炉人员"]
const requiredFields = ["锅炉编号", "锅炉型号", "额定蒸发量"]
const actions = ["降负荷运行", "停炉检修", "恢复运行"]
const statuses = ["正常运行", "低负荷", "检修中", "已停炉"]
// 每个状态下允许的动作：下行只能逐级走；已停炉需先停炉检修回到检修中，才能恢复运行
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  '正常运行': ['降负荷运行'],
  '低负荷': ['停炉检修'],
  '检修中': ['停炉检修', '恢复运行'],
  '已停炉': ['停炉检修'],
}
const stats = [{"label": "运行锅炉", "value": 0}, {"label": "检修锅炉", "value": 0}, {"label": "停炉锅炉", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<{ keyword: string; operator: string; status: string }>({
  keyword: '',
  operator: '',
  status: '',
})

const createOpen = ref(false)
const submitting = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>(
  Object.fromEntries(formFields.map((field) => [field, ''])),
)

function rowStatus(row: Row): string {
  return String(row.status ?? row['锅炉状态'] ?? '')
}

function displayValue(row: Row, column: string): string | number | null {
  if (column === '锅炉状态') {
    return rowStatus(row) || '—'
  }
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : (value as string | number)
}

function canRunAction(action: string, row: Row): boolean {
  return (ACTIONS_BY_STATUS[rowStatus(row)] ?? []).includes(action)
}

function resetFilters() {
  filters.keyword = ''
  filters.operator = ''
  filters.status = ''
  void reload()
}

function buildQuery(extra?: Record<string, string>): string {
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.operator.trim()) params.set('operator', filters.operator.trim())
  if (filters.status) params.set('status', filters.status)
  for (const [key, value] of Object.entries(extra ?? {})) {
    if (value) params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function exportRows() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/export${buildQuery()}`)
    if (!response.ok) {
      let detail = ''
      try {
        detail = (await response.json())?.detail ?? ''
      } catch {
        detail = ''
      }
      throw new Error(detail || `导出失败（接口返回 ${response.status}）`)
    }
    const payload = (await response.json()) as { items: Row[]; total: number }
    if (!payload.items || !payload.items.length) {
      errorMessage.value = '当前筛选条件下没有可导出的锅炉记录'
      return
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '锅炉管理清单.json'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '锅炉清单导出失败'
  }
}

function openCreate() {
  createError.value = ''
  for (const field of formFields) {
    createForm[field] = ''
  }
  createOpen.value = true
}

function closeCreate() {
  if (submitting.value) return
  createOpen.value = false
}

async function submitCreate() {
  createError.value = ''
  const missing = requiredFields.filter((field) => !createForm[field].trim())
  if (missing.length) {
    createError.value = `缺少必填字段：${missing.join('、')}`
    return
  }
  submitting.value = true
  try {
    const values: Record<string, string> = {}
    for (const field of formFields) {
      const value = createForm[field].trim()
      if (value) values[field] = value
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '锅炉登记失败')
    }
    createOpen.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '锅炉登记失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  if (!canRunAction(action, row)) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '锅炉管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '锅炉管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}${buildQuery()}`)
    if (!response.ok) {
      let detail = ''
      try {
        detail = (await response.json())?.detail ?? ''
      } catch {
        detail = ''
      }
      throw new Error(detail || '锅炉列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '锅炉管理列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 420px;
  max-height: 86vh;
  overflow: auto;
  background: #fff;
  border-radius: 8px;
  padding: 18px 20px;
}
.modal h3 { margin: 0 0 12px; }
.modal .filter-item { margin-bottom: 10px; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 14px; }
.link:disabled { color: #9aa4b2; cursor: not-allowed; }
</style>
