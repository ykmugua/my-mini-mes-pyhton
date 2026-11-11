"""测试辅助常量与请求封装。"""

from __future__ import annotations

from fastapi.testclient import TestClient

SHA_A = "a" * 64
SHA_B = "b" * 64


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
) -> dict:
    payload = {
        "workpiece": workpiece,
        "device_id": device_id,
        "test_item": test_item,
        "result": result,
        "program_version": program_version,
        "program_sha256": sha256,
        "measured_value": measured_value,
    }
    if product:
        payload["product"] = product
    response = client.post("/api/test-result", json=payload)
    assert response.status_code == 200, response.text
    return response.json()
