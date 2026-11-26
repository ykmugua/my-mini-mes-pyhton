"""设备控制状态路由：供设备端读取自身开启状态。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from .... import services
from ...schemas import DeviceHeartbeatIn, DeviceTestStartIn

router = APIRouter(tags=["device"])


@router.get("/api/device/enable")
def get_device_enable(device_id: str = Query(..., min_length=1)) -> dict:
    """查询指定设备是否开启。"""
    return services.device_enabled(device_id)


@router.post("/api/device/heartbeat")
def post_device_heartbeat(payload: DeviceHeartbeatIn) -> dict:
    """记录设备心跳。"""
    return services.record_device_heartbeat(payload.device_id)


@router.post("/api/device/test-start")
def post_device_test_start(payload: DeviceTestStartIn) -> dict:
    """记录测试开始。"""
    return services.record_test_start(
        device_id=payload.device_id,
        workpiece=payload.workpiece,
    )
