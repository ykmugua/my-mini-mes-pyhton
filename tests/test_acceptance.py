"""7 条验收标准的自动化测试（对应需求文档第六节）。"""

from __future__ import annotations

import pytest

from py_server import services
from tests.helpers import SHA_A, SHA_B, push_result


def test_acceptance_1_program_pull_returns_updated_binding(client, bench):
    """改绑定后设备调用 GET /api/program 能拿到新版本、URL 和 SHA256。"""
    services.replace_bindings(
        [
            {
                "device_id": "D1",
                "product": "P1",
                "program_version": "v2",
                "download_url": "http://testserver/programs/D1_v2.bin",
                "sha256": SHA_B,
            }
        ]
    )
    response = client.get("/api/program", params={"device_id": "D1", "product": "P1"})
    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "D1"
    assert body["product"] == "P1"
    assert body["program_version"] == "v2"
    assert body["download_url"] == "http://testserver/programs/D1_v2.bin"
    assert body["sha256"] == SHA_B

    pulls = services.list_program_pulls(10)
    assert pulls[0]["device_id"] == "D1"
    assert pulls[0]["program_version"] == "v2"


def test_acceptance_2_version_drift_alert(client, bench):
    """设备上报版本与绑定不一致时，漂移清单中出现该设备；恢复一致后消失。"""
    response = client.post(
        "/api/program/status",
        json={
            "device_id": "D1",
            "product": "P1",
            "program_version": "v0",
            "sha256": SHA_A,
            "sha256_ok": True,
        },
    )
    assert response.json()["trusted"] is False

    drifts = services.program_drift()
    assert [item["device_id"] for item in drifts] == ["D1"]
    assert "版本" in drifts[0]["drift_reason"]

    response = client.post(
        "/api/program/status",
        json={
            "device_id": "D1",
            "product": "P1",
            "program_version": "v1",
            "sha256": SHA_A,
            "sha256_ok": True,
        },
    )
    assert response.json()["can_produce"] is True
    assert services.program_drift() == []


def test_acceptance_3_interlock_rules(client, bench):
    """前道无 PASS 拒绝；前道 PASS 后放行；FAIL 工件后续设备拦截。"""
    denied = client.get(
        "/api/interlock", params={"workpiece": "W1", "device_id": "D2"}
    )
    assert denied.status_code == 200
    body = denied.json()
    assert body["allowed"] is False
    assert "D1" in body["reason"]

    # 前道 D1 上报 PASS 后，D2 放行
    push_result(client, "W1", "D1")
    allowed = client.get(
        "/api/interlock", params={"workpiece": "W1", "device_id": "D2"}
    ).json()
    assert allowed["allowed"] is True

    # D2 上报 FAIL 后工件被锁定，后续 D3 查询被拒绝
    failed = push_result(client, "W1", "D2", test_item="绝缘", result="FAIL")
    assert failed["workpiece_status"]["locked"] is True
    later = client.get(
        "/api/interlock", params={"workpiece": "W1", "device_id": "D3"}
    ).json()
    assert later["allowed"] is False
    assert "FAIL" in later["reason"]

    # 从未通过前道的工件同样是拒绝
    later = client.get(
        "/api/interlock", params={"workpiece": "W-NO-PREV", "device_id": "D2"}
    ).json()
    assert later["allowed"] is False
    assert "D1" in later["reason"]


def test_acceptance_4_unlock_requires_reason_and_confirm(client, bench):
    """解锁必须填写原因并勾选确认；解锁后放行恢复，且留痕可查。"""
    push_result(client, "W2", "D1", result="FAIL")

    with pytest.raises(services.ValidationError):
        services.unlock_workpiece("W2", "operator", "", True)
    with pytest.raises(services.ValidationError):
        services.unlock_workpiece("W2", "operator", "返修复测", False)
    with pytest.raises(services.ValidationError):
        services.unlock_workpiece("W2", "", "返修复测", True)

    result = services.unlock_workpiece("W2", "张工", "返修复测确认", True)
    assert result["locked"] is False
    assert result["status"] == "PENDING"

    allowed = client.get(
        "/api/interlock", params={"workpiece": "W2", "device_id": "D2"}
    ).json()
    assert allowed["allowed"] is True
    assert "人工解锁" in allowed["reason"]

    logs = services.list_unlock_logs()
    assert len(logs) == 1
    assert logs[0]["workpiece"] == "W2"
    assert logs[0]["operator"] == "张工"
    assert logs[0]["reason"] == "返修复测确认"
    assert "FAIL" in logs[0]["lock_reason"]

    with pytest.raises(services.ValidationError):
        services.unlock_workpiece("W2", "张工", "重复解锁", True)


def test_acceptance_5_dashboard_excludes_untrusted(client, bench):
    """看板统计今日数据，且校验和/版本不匹配的数据不计入合格率。"""
    push_result(client, "W1", "D1")
    push_result(client, "W2", "D1")

    # 让 D2 的程序状态与绑定不一致，之后上报的数据应标记为不可信
    client.post(
        "/api/program/status",
        json={
            "device_id": "D2",
            "product": "P1",
            "program_version": "v0",
            "sha256": SHA_B,
            "sha256_ok": False,
        },
    )
    untrusted = push_result(client, "W3", "D2")
    assert untrusted["trusted"] is False
    assert untrusted["workpiece_status"]["locked"] is True

    snapshot = services.dashboard_snapshot()
    assert snapshot["total"] == 3  # 总数包含全部上报
    assert snapshot["pass"] == 3
    assert snapshot["fail"] == 0
    assert snapshot["trusted_total"] == 2
    assert snapshot["untrusted"] == 1
    assert snapshot["yield"] == 1.0  # 合格率只统计可信数据
    assert [item["device_id"] for item in snapshot["by_device"]] == ["D1"]

    d2 = services.dashboard_snapshot("D2")
    assert d2["total"] == 1
    assert d2["trusted_total"] == 0
    assert d2["untrusted"] == 1
    assert d2["yield"] is None


def test_acceptance_6_variables_roundtrip(client, bench):
    """新增变量后设备能读到初始值；设备写入后数据层/页面数据可见。"""
    created = services.add_variable("line_mode", "str", "AUTO")
    assert created["value"] == "AUTO"

    read = client.get("/api/variable/line_mode")
    assert read.status_code == 200
    assert read.json()["value"] == "AUTO"

    written = client.post(
        "/api/variable/line_mode",
        json={"value": "MANUAL", "device_id": "D2"},
    )
    assert written.status_code == 200
    assert written.json()["value"] == "MANUAL"
    assert written.json()["last_device"] == "D2"

    listed = services.list_variables()
    assert listed[0]["name"] == "line_mode"
    assert listed[0]["value"] == "MANUAL"

    with pytest.raises(services.ConflictError):
        services.add_variable("line_mode", "str", "other")
    with pytest.raises(services.ValidationError):
        services.add_variable("", "str", "x")


def test_acceptance_7_duplicate_report_is_idempotent(client, bench):
    """同一工件同一测试项重复上报只记一次。"""
    first = push_result(client, "W1", "D1")
    second = push_result(client, "W1", "D1")
    assert second["duplicate"] is True
    assert second["id"] == first["id"]
    assert services.dashboard_snapshot()["total"] == 1

    failed_first = push_result(client, "W2", "D1", result="FAIL")
    failed_second = push_result(client, "W2", "D1", result="FAIL")
    assert failed_second["duplicate"] is True
    assert failed_second["workpiece_status"]["locked"] is True
    assert services.dashboard_snapshot()["total"] == 2
