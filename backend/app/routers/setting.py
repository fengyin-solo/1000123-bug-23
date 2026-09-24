"""系统设置接口：维护系统参数，覆盖修改参数、回滚参数、生效参数等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.setting import VALID_STATUSES, SettingService

router = APIRouter(prefix="/api/setting", tags=["系统设置"])

service = SettingService()

LIST_FIELDS = ["参数编码", "版本", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]
STATUSES = VALID_STATUSES


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按参数编码检索"),
    status: str | None = Query(default=None, description="已生效、待生效、已回滚"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按参数编码与状态过滤系统设置列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：固定路径必须排在 /{entry_id} 之前，否则 /export 会被当成参数 id 解析
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出系统设置清单：返回当前过滤条件下的全量数据（含历史版本）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "setting", "total": total, "items": items}


@router.get("/{entry_id}/history", response_model=dict)
def list_history(entry_id: int) -> dict[str, Any]:
    """列出某条版本所属参数编码下的全部版本，历史取值原样返回。"""
    history = service.list_history(entry_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"系统参数 {entry_id} 不存在或已归档")
    return {"items": history, "total": len(history)}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条系统参数版本明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"系统参数 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条系统参数，缺字段时说明原因而不是静默丢弃。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="系统参数已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条系统参数版本执行修改参数、回滚参数、生效参数；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
