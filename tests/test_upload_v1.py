"""MES V1.3 整单上传接口测试。"""

from __future__ import annotations

import uuid

from py_server.repositories import report_details_store, station_repo


HEADERS = {
    "x-device-sn": "SN-V1-001",
    "x-timestamp": "1745310935000",
}


def _payload(*, barcode="SN-V1-001", result="FAIL", step="S1", item="温度"):
    return {
        "station": "TEST-V1",
        "componentcode": "L120201091",
        "barcode": barcode,
        "programname": "TEST-DUT-001",
        "programversion": "V0.0.2",
        "testexecutetime": "2025/4/22 13:55:35.123",
        "result": result,
        "testlongtime": "00:00:06.300",
        "isfinalreport": "true",
        "details": [
            {
                "TestItem": item,
                "TestStep": step,
                "StandardValue": "1.10",
                "UpperValue": "1.20",
                "LowerValue": "0.90",
                "MeasureValue": "1.22" if result == "FAIL" else "1.12",
                "TestResult": "false" if result == "FAIL" else "true",
                "TestBeginTime": "13:55:35.123",
                "TestEndTime": "13:55:41.423",
            }
        ],
    }


def test_v1_upload_success_and_envelope(client):
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    response = client.post("/api/v1/test-results", json=_payload(), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "message", "code", "result"}
    assert body["success"] is True
    assert body["code"] == 0
    assert body["message"] == "success"
    assert body["result"]["workpiece"] == "SN-V1-001"
    assert body["result"]["retest"] is False


def test_v1_upload_requires_headers(client):
    response = client.post("/api/v1/test-results", json=_payload())
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 40001


def test_v1_upload_device_sn_mismatch(client):
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex, "x-device-sn": "OTHER"})
    response = client.post("/api/v1/test-results", json=_payload(), headers=headers)
    assert response.json()["code"] == 40003


def test_v1_upload_is_idempotent(client):
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    first = client.post("/api/v1/test-results", json=_payload(), headers=headers).json()
    second = client.post("/api/v1/test-results", json=_payload(), headers=headers).json()
    assert first["result"]["request_id"] == headers["x-request-id"]
    assert second["result"]["request_id"] == headers["x-request-id"]
    assert second["result"]["retest"] == first["result"]["retest"]


def test_v1_upload_updates_station_summary(client):
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    client.post("/api/v1/test-results", json=_payload(result="FAIL"), headers=headers)
    summary = station_repo.get_by_device("TEST-V1")
    assert summary is not None
    assert summary["status"] == "失败"
    assert summary["barcode"] == "SN-V1-001"
    assert summary["total"] == 1
    assert summary["fail"] == 1
    fails = station_repo.list_fail_details("TEST-V1")
    assert any(f["test_item"] == "温度" for f in fails)


def test_v1_upload_retest_counts_as_retest_pass(client):
    h1 = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    client.post("/api/v1/test-results", json=_payload(result="FAIL", step="S1"), headers=h1)
    h2 = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    response = client.post(
        "/api/v1/test-results",
        json=_payload(result="PASS", step="S2"),
        headers=h2,
    )
    assert response.json()["result"]["retest"] is True
    summary = station_repo.get_by_device("TEST-V1")
    assert summary["total"] == 2
    assert summary["retest_pass"] == 1


def test_v1_upload_master_detail_history(client):
    """上传后产品查询历史应返回整单结构（顶层字段 + details 列表）。"""
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    response = client.post("/api/v1/test-results", json=_payload(), headers=headers)
    assert response.json()["code"] == 0
    history = client.get("/api/ui/product/workpiece/SN-V1-001/history").json()["tests"]
    assert history, "历史不应为空"
    report = history[0]
    assert "details" in report, "应返回 V1.3 整单格式"
    assert report["station"] == "TEST-V1"
    assert report["componentcode"] == "L120201091"
    assert report["testexecutetime"] == "2025/4/22 13:55:35.123"
    assert report["barcode"] == "SN-V1-001"
    assert report["result"] == "FAIL"
    assert len(report["details"]) == 1
    assert report["details"][0]["LowerValue"] == "0.90"
    assert report["details"][0]["TestResult"] == "false"


def test_v1_upload_writes_overview(client):
    headers = dict(HEADERS, **{"x-request-id": uuid.uuid4().hex})
    response = client.post("/api/v1/test-results", json=_payload(), headers=headers)
    assert response.json()["code"] == 0
    overview = report_details_store.list_overview("SN-V1-001")
    assert overview
    row = overview[0]
    assert row["isfinalreport"] == "true"
    assert row["details_table"].startswith("SN_")
    assert len(row["details_table"].rsplit("_", 1)[-1]) == 16
    assert row["failed_step"] == "S1"
