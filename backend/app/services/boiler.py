"""锅炉管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "boiler"
REQUIRED_FIELDS = ["锅炉编号", "锅炉型号", "额定蒸发量"]
# 登记时可保存的全部台账字段；前三个为必填，其余选填但不能静默丢失。
OPTIONAL_FIELDS = ["工作压力", "燃料类型", "使用年限", "司炉人员"]
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
STATUS_FIELD = "锅炉状态"
STATUS_ORDER = ["正常运行", "低负荷", "检修中", "已停炉"]
# 动作只能沿状态序列逐级执行：正常运行→低负荷→检修中→已停炉；
# 「停炉检修」在低负荷时表示进入检修，在检修中再次执行表示检修完成、正式停炉；
# 已停炉后想恢复，得先执行停炉检修回到检修中（把检修做完），再恢复运行。
ACTION_BY_STATUS: dict[str, dict[str, str]] = {
    "正常运行": {"降负荷运行": "低负荷"},
    "低负荷": {"停炉检修": "检修中"},
    "检修中": {"停炉检修": "已停炉", "恢复运行": "正常运行"},
    "已停炉": {"停炉检修": "检修中"},
}
NEGATIVE_ACTIONS = ["降负荷运行", "停炉检修"]


class BoilerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        operator: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            key = keyword.strip()
            rows = [
                row
                for row in rows
                if key in str(row.get("锅炉编号", "")) or key in str(row.get("锅炉型号", ""))
            ]
        if operator:
            name = operator.strip()
            rows = [row for row in rows if name in str(row.get("司炉人员", ""))]
        if status:
            rows = [row for row in rows if str(row.get("status", "")) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = str(value).strip()
            else:
                entry[field] = None
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"锅炉 {entry_id} 不存在或已归档"
        current = str(entry.get("status") or "")
        allowed = ACTION_BY_STATUS.get(current)
        if allowed is None:
            return None, f"当前状态「{current}」无法识别，请联系管理员核对台账"

        target = allowed.get(action)
        if target is None:
            allowed_names = "、".join(allowed)
            if current == "已停炉" and action == "恢复运行":
                return None, "锅炉已停炉，需先完成停炉检修才能恢复运行"
            return None, f"当前状态为「{current}」，仅可执行：{allowed_names}"

        entry["status"] = target
        # 台账里的「锅炉状态」列与内部状态保持同一份口径，详情与列表读起来一致。
        entry[STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"锅炉已{action}"
