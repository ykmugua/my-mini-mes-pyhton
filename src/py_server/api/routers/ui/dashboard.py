"""看板与设备清单路由。"""

from __future__ import annotations

from fastapi import APIRouter

from .... import services

router = APIRouter(tags=["dashboard"])


@router.get("/api/ui/devices")
def ui_devices() -> list[str]:
    """执行 ui_devices。"""
    return services.list_devices()


@router.get("/api/ui/dashboard")
def ui_dashboard(device: str | None = None) -> dict:
    """执行 ui_dashboard。"""
    return services.dashboard_snapshot(device)


@router.get("/api/ui/stations/{device_id}")
def ui_station_summary(device_id: str) -> dict | None:
    """按设备读取 station_summary 汇总。"""
    return services.station_summary(device_id)


@router.get("/api/ui/stations/{device_id}/status")
def ui_device_status(device_id: str) -> dict:
    """按设备读取看板卡片显示状态。"""
    return services.device_status(device_id)


@router.get("/api/ui/stations/{device_id}/fail-details")
def ui_station_fail_details(device_id: str, limit: int = 50) -> list[dict]:
    """按设备读取失败项明细。"""
    return services.station_fail_details(device_id, limit=limit)
