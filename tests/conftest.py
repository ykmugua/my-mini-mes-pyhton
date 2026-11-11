"""pytest 公共夹具：每个测试使用独立的临时数据库与程序目录。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.helpers import SHA_A, SHA_B


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("MES_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MES_DB_PATH", str(data_dir / "mes.db"))
    monkeypatch.setenv("MES_PROGRAM_DIR", str(data_dir / "programs"))
    monkeypatch.setenv("MES_API_PUBLIC_BASE", "http://testserver")
    monkeypatch.setenv("MES_TZ", "Asia/Shanghai")

    from py_server import db

    db.reset_for_tests()
    db.init_db()
    yield data_dir
    db.reset_for_tests()


@pytest.fixture()
def client(isolated):
    from py_server.api import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def bench(isolated):
    """三台设备、同一个产品、前道关系 D1 -> D2 -> D3，程序全部可信。"""
    from py_server import services

    bindings = [
        {
            "device_id": device,
            "product": "P1",
            "program_version": "v1",
            "download_url": f"http://testserver/programs/{device}.bin",
            "sha256": SHA_A,
        }
        for device in ("D1", "D2", "D3")
    ]
    services.replace_bindings(bindings)
    for device in ("D1", "D2", "D3"):
        services.report_program_status(
            device_id=device,
            product="P1",
            reported_version="v1",
            reported_sha256=SHA_A,
            sha256_ok=True,
        )
    services.replace_upstream_rules(
        [
            {"product": "", "device_id": "D2", "upstream_device_id": "D1"},
            {"product": "", "device_id": "D3", "upstream_device_id": "D2"},
        ]
    )
    return {"sha": SHA_A, "sha_b": SHA_B, "bindings": bindings}


@pytest.fixture()
def seeded(isolated):
    """写入与 `python -m py_server.seed --demo` 相同的演示数据。"""
    from py_server import seed

    seed.seed(reset=True, with_demo=True)
    return isolated
