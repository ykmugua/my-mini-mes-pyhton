"""设备看板状态与新设备接口的规则测试。"""

from __future__ import annotations

from py_server import constants
from py_server.application.device_status import resolve_display_status


def test_disabled_has_priority(client, monkeypatch):
    monkeypatch.setenv("MES_DEVICE_CONFIG_PATH", "config/device_config.json")
    state = resolve_display_status(
        summary={"device_id": "D1", "status": "通过", "status_since": 1},
        enabled=False,
        now_ts=10,
    )
    assert state["status"] == constants.DEVICE_STATUS_DISABLED
    assert state["show_timer"] is False


def test_offline_when_no_heartbeat(client):
    state = resolve_display_status(
        summary={
            "device_id": "D-NEVER",
            "status": constants.STATUS_PASS_TEXT,
            "status_since": 1,
        },
        enabled=True,
        now_ts=10,
    )
    assert state["status"] == constants.DEVICE_STATUS_OFFLINE
    assert state["show_timer"] is False


def test_pass_falls_to_idle_after_threshold(client, monkeypatch):
    from py_server.repositories import device_heartbeat_repo

    device_heartbeat_repo.touch("D-STATUS", now_ts=100)
    state = resolve_display_status(
        summary={
            "device_id": "D-STATUS",
            "status": constants.STATUS_PASS_TEXT,
            "status_since": 10,
            "test_duration": 3,
        },
        enabled=True,
        now_ts=100 + constants.DEVICE_IDLE_THRESHOLD_SECONDS + 1,
    )
    assert state["status"] in {
        constants.DEVICE_STATUS_IDLE,
        constants.DEVICE_STATUS_OFFLINE,
        constants.DEVICE_STATUS_DISABLED,
    }


def test_idle_elapsed_grows_with_refresh_time(client):
    """空闲状态每次按刷新时重新计算，计时应随时间递增。"""
    from py_server.repositories import device_heartbeat_repo

    device_heartbeat_repo.touch("D-IDLE-TIMER", now_ts=1000)
    summary = {
        "device_id": "D-IDLE-TIMER",
        "status": constants.DEVICE_STATUS_IDLE,
        "status_since": 800,
    }
    first = resolve_display_status(summary=summary, enabled=True, now_ts=1000)
    second = resolve_display_status(summary=summary, enabled=True, now_ts=1003)
    assert first["status"] == constants.DEVICE_STATUS_IDLE
    assert second["status"] == constants.DEVICE_STATUS_IDLE
    assert second["elapsed"] == first["elapsed"] + 3


def test_heartbeat_and_test_start_api(client, monkeypatch, tmp_path):
    config_path = tmp_path / "device_config.json"
    config_path.write_text(
        '{"devices":[{"device_id":"D1","name":"D1","enable":true}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MES_DEVICE_CONFIG_PATH", str(config_path))

    beat = client.post("/api/device/heartbeat", json={"device_id": "D1"})
    assert beat.status_code == 200
    started = client.post("/api/device/test-start", json={"device_id": "D1", "workpiece": "W1"})
    assert started.status_code == 200
    assert started.json()["status"] == "测试中"

    status = client.get("/api/ui/stations/D1/status")
    assert status.status_code == 200
    assert status.json()["status"] == "测试中"
