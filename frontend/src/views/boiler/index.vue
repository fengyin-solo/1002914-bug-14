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
      <label v-for="field in filterFields" :key="field.name" class="filter-item">
        <span>{{ field.name }}</span>
        <select v-if="field.options" v-model="filters[field.name]">
          <option value="">全部</option>
          <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
        </select>
        <input v-else v-model="filters[field.name]" :placeholder="`按${field.name}检索`" />
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
          <td v-for="column in columns" :key="column">
            <button v-if="column === '锅炉编号'" class="link" type="button" @click="openDetail(Number(row.id))">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRunAction(action, row)"
              :title="canRunAction(action, row) ? '' : `当前为「${row['锅炉状态']}」，不能${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ loadFailed ? '锅炉列表读取失败，请稍后重试' : '暂无锅炉管理数据，可先登记锅炉' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条锅炉管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记锅炉</h3>
        <div class="form-grid">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}{{ requiredFields.includes(field) ? ' *' : '' }}</span>
            <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <div class="modal-foot">
          <span v-if="formError" class="error-text">{{ formError }}</span>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <h3>锅炉详情</h3>
        <table v-if="detail" class="data-table detail-table">
          <tbody>
            <tr v-for="column in columns" :key="column">
              <th>{{ column }}</th>
              <td>{{ detail[column] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="detailError" class="error-text">{{ detailError }}</p>
        <div class="modal-foot">
          <button class="btn primary" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/boiler'
const columns = ["锅炉编号", "锅炉型号", "额定蒸发量", "工作压力", "燃料类型", "使用年限", "司炉人员", "锅炉状态"]
const actions = ["降负荷运行", "停炉检修", "恢复运行"]
const statuses = ["正常运行", "低负荷", "检修中", "已停炉"]
const stats = [{"label": "运行锅炉", "value": 0}, {"label": "检修锅炉", "value": 0}, {"label": "停炉锅炉", "value": 0}]

// 与后端状态机保持一致：动作只能顺着正常运行一级一级走
const ACTION_MATRIX: Record<string, string[]> = {
  "正常运行": ["降负荷运行"],
  "低负荷": ["停炉检修"],
  "检修中": ["停炉检修", "恢复运行"],
  "已停炉": ["停炉检修"],
}

const formFields = ["锅炉编号", "锅炉型号", "额定蒸发量", "工作压力", "燃料类型", "使用年限", "司炉人员"]
const requiredFields = ["锅炉编号", "锅炉型号", "额定蒸发量"]

const filterFields = [
  { name: "锅炉编号" },
  { name: "司炉人员" },
  { name: "锅炉状态", options: statuses },
]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const loadFailed = ref(false)
const filters = ref<Record<string, string>>({})

const createVisible = ref(false)
const submitting = ref(false)
const formError = ref('')
const createForm = ref<Record<string, string>>({})

const detailVisible = ref(false)
const detail = ref<Row | null>(null)
const detailError = ref('')

function canRunAction(action: string, row: Row): boolean {
  return ACTION_MATRIX[String(row['锅炉状态'] ?? '')]?.includes(action) ?? false
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown }
    const message = payload.message ?? payload.detail
    if (typeof message === 'string' && message) {
      return message
    }
  } catch {
    // 响应不是 JSON 时退回兜底提示
  }
  return fallback
}

function buildQuery(): string {
  const params = new URLSearchParams()
  if (filters.value['锅炉编号']?.trim()) params.set('keyword', filters.value['锅炉编号'].trim())
  if (filters.value['司炉人员']?.trim()) params.set('operator', filters.value['司炉人员'].trim())
  if (filters.value['锅炉状态']) params.set('status', filters.value['锅炉状态'])
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function exportRows() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/export${buildQuery()}`)
    if (!response.ok) {
      throw new Error(await readError(response, '锅炉清单导出失败'))
    }
    const payload = (await response.json()) as { items: Row[] }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = '锅炉管理清单.json'
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '锅炉清单导出失败'
  }
}

function openCreate() {
  createForm.value = Object.fromEntries(formFields.map((field) => [field, '']))
  formError.value = ''
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
  formError.value = ''
}

async function submitCreate() {
  formError.value = ''
  const values = Object.fromEntries(
    formFields.map((field) => [field, createForm.value[field]?.trim() ?? '']),
  )
  try {
    submitting.value = true
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (!response.ok || payload.ok === false) {
      formError.value = payload.message || '锅炉登记失败，请检查填写内容'
      return
    }
    closeCreate()
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '锅炉登记失败'
  } finally {
    submitting.value = false
  }
}

async function openDetail(id: number) {
  detail.value = null
  detailError.value = ''
  detailVisible.value = true
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      throw new Error(await readError(response, '锅炉详情读取失败'))
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '锅炉详情读取失败'
  }
}

function closeDetail() {
  detailVisible.value = false
  detail.value = null
  detailError.value = ''
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok?: boolean; message?: string }
    if (!response.ok || payload.ok === false) {
      errorMessage.value = payload.message || '锅炉管理动作未生效，请稍后重试'
      return
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
      throw new Error(await readError(response, '锅炉列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    loadFailed.value = false
  } catch (error) {
    // 接口报错时保留上一次的数据，不把表格清空成一片空白
    loadFailed.value = true
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
  background: #fff;
  border-radius: 8px;
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  overflow: auto;
  padding: 18px 20px;
}
.modal h3 { margin: 0 0 14px; }
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-foot {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}
.modal-foot .error-text { margin-right: auto; }
.detail-table th { width: 120px; white-space: nowrap; }
.link:disabled { color: #94a3b8; cursor: not-allowed; }
</style>
