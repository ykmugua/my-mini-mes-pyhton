"""工序锁路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ... import services
from ..schemas import UnlockIn, UpstreamRulesIn

router = APIRouter(tags=["interlock"])


@router.get("/api/interlock")
def get_interlock(
    workpiece: str = Query(..., min_length=1),
    device_id: str | None = Query(default=None),
    product: str | None = Query(default=None),
) -> dict:
    return services.interlock_check(workpiece=workpiece, device_id=device_id, product=product)


@router.get("/api/ui/workpieces/locked")
def ui_locked() -> list[dict]:
    return services.list_locked_workpieces()


@router.get("/api/ui/unlock-logs")
def ui_unlock_logs(limit: int = 50) -> list[dict]:
    return services.list_unlock_logs(limit)


@router.post("/api/ui/unlock")
def ui_unlock(payload: UnlockIn) -> dict:
    return services.unlock_workpiece(
        workpiece=payload.workpiece,
        operator=payload.operator,
        reason=payload.reason,
        confirmed=payload.confirmed,
    )


@router.get("/api/ui/upstream")
def ui_upstream() -> list[dict]:
    return services.list_upstream_rules()


@router.post("/api/ui/upstream")
def ui_replace_upstream(payload: UpstreamRulesIn) -> dict:
    return {"count": services.replace_upstream_rules(payload.rows)}