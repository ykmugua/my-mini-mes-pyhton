"""测试辅助常量与请求封装。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from py_server.constants import DETAIL_RESULT_FAIL, DETAIL_RESULT_PASS

SHA_A = "a" * 64
SHA_B = "b" * 64


def _to_protocol_time(value: str | None) -> str:
    """把 ISO/任意测试时间转成 V1.3 协议时间；空值使用固定演示时间。"""
    if not value:
        from datetime import datetime

        now = datetime.now()
        return now.strftime("%Y/%m/%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"
    from datetime import datetime

    text = str(value).strip()
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y/%m/%d %H:%M:%S.%f")[:-3]
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y/%m/%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
    except ValueError:
        return "2026/11/24 10:00:00.000"


def push_result(
    client: TestClient,
    workpiece: str,
    device_id: str,
    *,
    test_item: str = "电压",
    result: str = "PASS",
    program_version: str = "v1",
    sha256: str = SHA_A,
    product: str | None = "P1",
    measured_value: str | None = "1.0V",
    tested_at: str | None = None,
) -> dict:
    """通过 V1.3 整单接口上报一条测试结果（测试辅助）。"""
    passed = result == "PASS"
    payload = {
        "barcode": workpiece,
        "componentcode": product or "P1",
        "station": device_id,
        "fixturecode": "/",
        "traycode": "/",
        "programname": "TEST-PROGRAM",
        "programversion": program_version,
        "testexecutetime": _to_protocol_time(tested_at),
        "testlongtime": "00:00:01.000",
        "result": result,
        "isfinalreport": "false",
        "details": [
            {
                "TestItem": test_item,
                "TestStep": test_item,
                "StandardValue": "1.00",
                "UpperValue": "2.00",
                "LowerValue": "0.00",
                "MeasureValue": str(measured_value or ""),
                "TestResult": DETAIL_RESULT_PASS if passed else DETAIL_RESULT_FAIL,
                "TestBeginTime": "10:00:00.000",
                "TestEndTime": "10:00:01.000",
            }
        ],
    }
    response = client.post("/api/v1/test-results", json=payload)
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert envelope.get("success") is True, envelope
    assert envelope.get("code") == "200", envelope
    return envelope
