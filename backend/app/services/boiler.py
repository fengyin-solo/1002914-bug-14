"""锅炉管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "boiler"
REQUIRED_FIELDS = ["锅炉编号", "锅炉型号", "额定蒸发量"]
# 登记页可以填写的全部字段，列表、详情与导出共用这一份口径
OPTIONAL_FIELDS = ["工作压力", "燃料类型", "使用年限", "司炉人员"]
LIST_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS + ["锅炉状态"]
STATUS_ORDER = ["正常运行", "低负荷", "检修中", "已停炉"]
# 动作只能顺着正常运行一级一级走；已停炉想恢复，必须先经停炉检修回到检修中，
# 检修做完后才能恢复运行，不允许跨级跳变。
TRANSITIONS: dict[tuple[str, str], str] = {
    ("正常运行", "降负荷运行"): "低负荷",
    ("低负荷", "停炉检修"): "检修中",
    ("检修中", "停炉检修"): "已停炉",
    ("已停炉", "停炉检修"): "检修中",
    ("检修中", "恢复运行"): "正常运行",
}
PENDING_STATUSES = {"正常运行", "低负荷"}
ABNORMAL_STATUSES = {"低负荷"}


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """列表、详情、导出共用同一份取数口径：展示列与内部状态保持一致。"""
    item: dict[str, Any] = {"id": row.get("id")}
    for field in LIST_FIELDS:
        if field == "锅炉状态":
            item[field] = row.get("status")
        else:
            item[field] = row.get(field)
    return item


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
            rows = [row for row in rows if keyword in str(row.get("锅炉编号", ""))]
        if operator:
            rows = [row for row in rows if operator in str(row.get("司炉人员", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _serialize(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 登记时把编号、型号、蒸发量连同使用年限、司炉人员等字段一次存全
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            value = values.get(field)
            entry[field] = str(value).strip() if value is not None else None
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _serialize(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"锅炉 {entry_id} 不存在或已归档"
        if not any(name == action for (_, name) in TRANSITIONS):
            return None, f"动作「{action}」不属于锅炉管理可执行范围"
        current = str(entry.get("status") or "")
        target = TRANSITIONS.get((current, action))
        if target is None:
            return None, f"锅炉当前为「{current}」，不能直接{action}，请按运行、低负荷、检修、停炉的顺序逐级操作"
        entry["status"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = target in ABNORMAL_STATUSES
        return _serialize(entry), f"锅炉已{action}"
