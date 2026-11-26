"""无载具工序的入站、下线规则测试。"""

from __future__ import annotations

import pytest

from py_server import services
from py_server import db, engine as eg, master_seed, seed
from py_server.repositories.base import Conn, with_conn
from py_server.repositories import master_data_repo
from py_server.repositories import active_product_repo


@pytest.fixture()
def no_tray_product(client, isolated):
    seed.seed(reset=True, with_demo=False)
    with with_conn() as conn:
        rows = master_data_repo.list_process_step_resources(conn)
        for row in rows:
            if row["process_code"] == "PROC-001" and str(row["step_no"]) == "1":
                row["tray_models"] = ""
        master_data_repo.replace_process_step_resources(conn, rows)
    return "P-1001"


def test_no_tray_inbound_and_downline(client, no_tray_product):
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "",
            "barcodes": ["NT-001", "NT-002"],
            "operator": "op",
        },
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["traycode"] == "/"

    active = active_product_repo.list_active(barcode="NT-001")
    assert active and active[0]["traycode"] == "/"

    downline = client.post(
        "/api/ui/workbench/workpiece-downline",
        json={"barcode": "NT-001", "operator": "op", "confirmed": True},
    )
    assert downline.status_code == 200, downline.text
    assert not active_product_repo.list_active(barcode="NT-001")


def test_no_tray_step_rejects_traycode(client, no_tray_product):
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": ["NT-ERR-001"],
            "operator": "op",
        },
    )
    assert inbound.status_code == 400
    assert "未配置载具" in inbound.json()["detail"]


def test_legacy_empty_traycode_can_downline(client, no_tray_product):
    """旧数据里的空 traycode 也应按无载具处理。"""
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "",
            "barcodes": ["NT-LEGACY-001"],
            "operator": "op",
        },
    )
    assert inbound.status_code == 200, inbound.text

    with with_conn() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "UPDATE active_products SET traycode='' WHERE barcode='NT-LEGACY-001'"
            )
        )

    downline = client.post(
        "/api/ui/workbench/workpiece-downline",
        json={"barcode": "NT-LEGACY-001", "operator": "op", "confirmed": True},
    )
    assert downline.status_code == 200, downline.text
    assert not active_product_repo.list_active(barcode="NT-LEGACY-001")
