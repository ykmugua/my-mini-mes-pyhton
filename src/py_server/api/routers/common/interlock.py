"""工序锁路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from .... import services
from ...schemas import UnlockIn, UpstreamRulesIn

router = APIRouter(tags=["interlock"])


@router.get("/api/ui/interlock-check")
def ui_interlock_check(
    workpiece: str = Query(..., min_length=1),
    device_id: str | None = Query(default=None),
    product: str | None = Query(default=None),
) -> dict:
    """UI 模拟设备查询联锁放行结果。"""
    return services.interlock_check(workpiece=workpiece, device_id=device_id, product=product)


@router.get("/api/ui/workpieces/locked")
def ui_locked() -> list[dict]:
    """执行 ui_locked。"""
    return services.list_locked_workpieces()


@router.get("/api/ui/unlock-logs")
def ui_unlock_logs(limit: int = 50) -> list[dict]:
    """执行 ui_unlock_logs。"""
    return services.list_unlock_logs(limit)


@router.post("/api/ui/unlock")
def ui_unlock(payload: UnlockIn) -> dict:
    """执行 ui_unlock。"""
    return services.unlock_workpiece(
        workpiece=payload.workpiece,
        operator=payload.operator,
        reason=payload.reason,
        confirmed=payload.confirmed,
        target_step=payload.target_step,
        note=payload.note,
    )


@router.get("/api/ui/upstream")
def ui_upstream() -> list[dict]:
    """执行 ui_upstream。"""
    return services.list_upstream_rules()


@router.post("/api/ui/upstream")
def ui_replace_upstream(payload: UpstreamRulesIn) -> dict:
    """执行 ui_replace_upstream。"""
    return {"count": services.replace_upstream_rules(payload.rows)}
