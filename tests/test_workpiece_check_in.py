"""产品进站校验接口验收测试。"""

from __future__ import annotations

from sqlalchemy import text

from py_server import db, engine as eg, seed
from py_server.repositories import active_product_repo, product_flow_store
from py_server.repositories.base import with_conn


def _seed_resources(client):
    """写入进站校验所需主数据。"""
    seed.seed(reset=True, with_demo=False)
    with with_conn() as conn:
        from py_server.repositories import master_data_repo

        devices = master_data_repo.list_devices(conn)
        for device in devices:
            if device["device_id"] == "TEST-01":
                device["device_model"] = "DM-T01"
        master_data_repo.replace_devices(conn, devices)
        needle_beds = [
            {
                "needle_bed_code": "F1002",
                "needle_bed_name": "治具 F1002",
                "needle_bed_number": "N1002",
                "needle_bed_model": "NB-T01",
                "enabled": 1,
                "remark": "",
            },
            {
                "needle_bed_code": "F9999",
                "needle_bed_name": "治具 F9999",
                "needle_bed_number": "N9999",
                "needle_bed_model": "NB-OTHER",
                "enabled": 1,
                "remark": "",
            },
        ]
        master_data_repo.replace_needle_beds(conn, needle_beds)
        resources = master_data_repo.list_process_step_resources(conn)
        for row in resources:
            if row["process_code"] == "PROC-001" and str(row["step_no"]) == "1":
                row["needle_bed_models"] = "NB-T01"
                row["tray_models"] = "TM-A"
        master_data_repo.replace_process_step_resources(conn, resources)


def _inbound(client, barcode="CHECK-001", traycode="T02001"):
    """创建一条在制产品作为校验对象。"""
    response = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "process_code": "PROC-001",
            "step_no": "1",
            "traycode": traycode,
            "barcodes": [barcode],
            "tray_slots": ["1"],
            "operator": "op",
        },
    )
    assert response.status_code == 200, response.text


def _check(client, **overrides):
    """调用进站校验接口。"""
    payload = {
        "barcode": "CHECK-001",
        "station": "TEST-01",
        "fixturecode": "F1002",
        "traycode": "T02001",
    }
    payload.update(overrides)
    return client.post("/api/workpiece/check-in", json=payload)


def _snapshot():
    """读取在制产品和流转历史快照，验证只读性。"""
    active = active_product_repo.list_active()
    flow = product_flow_store.list_overview()
    return active, flow


def test_check_in_success_and_readonly(client, isolated):
    _seed_resources(client)
    _inbound(client)
    before = _snapshot()
    response = _check(client)
    after = _snapshot()
    assert response.status_code == 200, response.text
    assert response.json() == {
        "success": True,
        "code": "200",
        "message": "产品允许进站",
        "data": {"processcode": "PROC-001", "stepon": "1"},
    }
    assert before == after


def test_check_in_rejects_missing_product(client, isolated):
    _seed_resources(client)
    response = _check(client, barcode="NO-SUCH-WP")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "产品不存在" in response.json()["message"]


def test_check_in_rejects_locked_product(client, isolated):
    _seed_resources(client)
    _inbound(client)
    with with_conn() as conn:
        conn.execute(
            text("UPDATE workpieces SET lock_reason='test fail', status='FAIL' WHERE workpiece='CHECK-001'")
        )
    response = _check(client)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "锁定状态" in response.json()["message"]


def test_check_in_rejects_failed_result(client, isolated):
    _seed_resources(client)
    _inbound(client)
    with with_conn() as conn:
        conn.execute(text("UPDATE workpieces SET status='FAIL' WHERE workpiece='CHECK-001'"))
    response = _check(client)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "FAIL" in response.json()["message"]


def test_check_in_rejects_wrong_step(client, isolated):
    _seed_resources(client)
    _inbound(client)
    response = _check(client, station="NO-SUCH-STATION")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "未注册" in response.json()["message"]


def test_check_in_rejects_wrong_fixture_model(client, isolated):
    _seed_resources(client)
    _inbound(client)
    response = _check(client, fixturecode="F9999")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "治具" in response.json()["message"]


def test_check_in_rejects_wrong_tray_model(client, isolated):
    _seed_resources(client)
    _inbound(client)
    response = _check(client, traycode="T02003")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "载具" in response.json()["message"]


def test_check_in_rejects_tray_not_bound_to_barcode(client, isolated):
    _seed_resources(client)
    _inbound(client, barcode="CHECK-BOUND", traycode="T02001")
    response = _check(client, barcode="CHECK-BOUND", traycode="T02002")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "当前绑定载具" in response.json()["message"]


def test_check_in_rejects_missing_resource(client, isolated):
    _seed_resources(client)
    _inbound(client)
    with with_conn() as conn:
        conn.execute(
            text("DELETE FROM process_step_resources WHERE process_code='PROC-001' AND step_no='1'")
        )
    response = _check(client)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "工序资源配置不存在" in response.json()["message"]


def test_check_in_rejects_missing_required_field(client, isolated):
    _seed_resources(client)
    response = client.post(
        "/api/workpiece/check-in",
        json={"barcode": "", "station": "TEST-01", "fixturecode": "F1002", "traycode": "T02001"},
    )
    assert response.status_code == 422
