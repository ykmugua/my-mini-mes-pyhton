"""设备看板状态计算用例：组合启用状态、心跳与测试结果。"""

from __future__ import annotations

import time
from typing import Any

from .. import constants
from ..repositories import device_heartbeat_repo


def resolve_display_status(
    *,
    summary: dict[str, Any] | None,
    enabled: bool,
    heartbeat_timeout: int = constants.DEVICE_HEARTBEAT_TIMEOUT_SECONDS,
    idle_threshold: int = constants.DEVICE_IDLE_THRESHOLD_SECONDS,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """按优先级计算卡片状态：禁用 > 离线 > 测试中 > 通过/失败 > 空闲。"""
    summary = dict(summary or {})
    if not summary.get("device_id"):
        summary["device_id"] = str(summary.get("device") or "")
    now = int(now_ts if now_ts is not None else time.time())
    raw_status = str(summary.get("status") or constants.DEVICE_STATUS_IDLE)
    status_since = summary.get("status_since")
    test_duration = int(summary.get("test_duration") or 0)
    last_seen = device_heartbeat_repo.last_seen_at(str(summary.get("device_id") or ""))

    if not enabled:
        return {"status": constants.DEVICE_STATUS_DISABLED, "elapsed": None, "show_timer": False}
    if last_seen is None or now - int(last_seen) > heartbeat_timeout:
        return {"status": constants.DEVICE_STATUS_OFFLINE, "elapsed": None, "show_timer": False}

    if raw_status == constants.DEVICE_STATUS_TESTING:
        elapsed = max(0, now - int(status_since)) if status_since else 0
        return {"status": constants.DEVICE_STATUS_TESTING, "elapsed": elapsed, "show_timer": True}

    if raw_status in (constants.STATUS_PASS_TEXT, constants.STATUS_FAIL_TEXT) and status_since:
        elapsed = now - int(status_since)
        if elapsed <= idle_threshold:
            return {
                "status": raw_status,
                "elapsed": test_duration,
                "show_timer": True,
                "test_time": int(status_since),
            }

    elapsed = max(0, now - int(status_since)) if status_since else 0
    return {"status": constants.DEVICE_STATUS_IDLE, "elapsed": elapsed, "show_timer": True}
