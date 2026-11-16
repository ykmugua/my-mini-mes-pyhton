"""看板与设备清单路由。"""

from __future__ import annotations

from fastapi import APIRouter

from ... import services

router = APIRouter(tags=["dashboard"])


@router.get("/api/ui/devices")
def ui_devices() -> list[str]:
    return services.list_devices()


@router.get("/api/ui/dashboard")
def ui_dashboard(device: str | None = None) -> dict:
    return services.dashboard_snapshot(device)