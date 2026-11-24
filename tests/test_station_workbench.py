"""工位操作台：产品倒查工艺、批量入站、托盘解绑。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from py_server import seed, services
from tests.helpers import push_result
from py_server.repositories import product_flow_store

UI_DIR = Path(__file__).resolve().parent / "ui_apps"


@pytest.fixture()
def workbench_seeded(isolated):
    seed.seed(reset=True, with_demo=False)
    return isolated


def _v1_result_payload(
    *,
    barcode: str,
    traycode: str,
    result: str,
    is_final: bool,
) -> dict:
    return {
        "station": "TEST-03",
        "componentcode": "P-1001",
        "traycode": traycode,
        "barcode": barcode,
        "programname": "TEST-DUT-S3",
        "programversion": "v1",
        "testexecutetime": "2026/11/21 16:20:00.000",
        "result": result,
        "testlongtime": "00:00:01.000",
        "isfinalreport": "true" if is_final else "false",
        "details": [
            {
                "TestItem": "终态自动解绑测试",
                "TestStep": "S3_01",
                "StandardValue": "1.00",
                "UpperValue": "1.10",
                "LowerValue": "0.90",
                "MeasureValue": "1.00",
                "TestResult": "true" if result == "PASS" else "false",
                "TestBeginTime": "16:20:00.000",
                "TestEndTime": "16:20:01.000",
            }
        ],
    }


def _post_v1_result(
    client,
    *,
    barcode: str,
    traycode: str,
    result: str,
    is_final: bool,
) -> dict:
    response = client.post(
        "/api/v1/test-results",
        json=_v1_result_payload(
            barcode=barcode,
            traycode=traycode,
            result=result,
            is_final=is_final,
        ),
        headers={
            "x-device-sn": "TEST-03",
            "x-timestamp": "1763713200000",
            "x-request-id": uuid.uuid4().hex,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0, body
    return body


def test_workbench_inbound_and_tray_unbind_roundtrip(client, workbench_seeded):
    recipe = client.get("/api/ui/workbench/recipe", params={"product": "P-1001"})
    assert recipe.status_code == 200
    body = recipe.json()
    assert body["process"]["process_code"] == "PROC-001"
    assert body["first_step"] == "1"
    assert "TM-A" in body["tray_models"]
    assert [step["step_no"] for step in body["steps"]] == ["1", "2", "3"]
    assert body["steps"][0]["tray_models"] == ["TM-A"]
    assert body["steps"][2]["tray_models"] == ["TM-B"]

    prepared = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02001",
            "operator": "工位测试员",
            "confirmed": True,
        },
    )
    # 演示数据是否占用该载具由初始化流程决定；先确保它处于可入站状态。
    assert prepared.status_code in {200, 404}, prepared.text

    barcodes = [f"WB-{index:04d}" for index in range(1, 21)]
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "工位测试员",
        },
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["count"] == 20
    assert inbound.json()["current_step"] == "1"

    overview = client.get(
        "/api/ui/product/flow-overview",
        params={"traycode": "T02001"},
    ).json()
    assert len(overview) == 20
    assert {row["componentcode"] for row in overview} == {"P-1001"}
    assert {row["board_status"] for row in overview} == {"normal"}
    assert {row["current_step"] for row in overview} == {"1"}

    detail = client.get(f"/api/ui/product/workpiece/{barcodes[0]}/detail")
    assert detail.status_code == 200
    assert detail.json()["product"] == "P-1001"
    assert detail.json()["status"] == "PENDING"

    occupied = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": [f"WB-OCCUPIED-{index:02d}" for index in range(1, 21)],
            "operator": "工位测试员",
        },
    )
    assert occupied.status_code == 409
    assert "先解除托盘绑定" in occupied.json()["detail"]

    rejected = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02001",
            "operator": "工位测试员",
            "confirmed": False,
        },
    )
    assert rejected.status_code == 400

    unbound = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02001",
            "operator": "工位测试员",
            "confirmed": True,
        },
    )
    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["count"] == 20

    remaining = client.get(
        "/api/ui/product/flow-overview",
        params={"traycode": "T02001"},
    ).json()
    assert remaining == []
    rows = client.get("/api/ui/product/flow-overview").json()
    assert all(row["barcode"] not in barcodes for row in rows)

    from py_server.repositories import product_flow_store

    history = product_flow_store.list_flow(product_flow_store.flow_table_name(barcodes[0]))
    assert any(row["device"] == "托盘解绑" for row in history)

    reused = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": [barcodes[0]],
            "operator": "工位测试员",
        },
    )
    assert reused.status_code == 200, reused.text


def test_delete_inbound_releases_barcode_but_keeps_test_data(client, seeded):
    barcode = "SN202611180001"
    before = client.get("/api/ui/product/report-query", params={"barcode": barcode}).json()
    assert before

    assert client.delete("/api/ui/product/flow", params={"barcode": barcode}).status_code == 200
    assert client.get("/api/ui/product/flow-overview", params={"barcode": barcode}).json() == []

    after = client.get("/api/ui/product/report-query", params={"barcode": barcode}).json()
    assert len(after) == len(before)

    client.post(
        "/api/ui/workbench/tray-unbind",
        json={"traycode": "T02001", "operator": "工位测试员", "confirmed": True},
    )
    reused = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": [barcode],
            "operator": "工位测试员",
        },
    )
    assert reused.status_code == 200, reused.text


def test_delete_tray_flow_releases_all_barcodes(client, workbench_seeded):
    client.post(
        "/api/ui/workbench/tray-unbind",
        json={"traycode": "T02001", "operator": "工位测试员", "confirmed": True},
    )
    barcodes = ["WB-DELETE-001", "WB-DELETE-002"]
    assert client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "工位测试员",
        },
    ).status_code == 200
    assert client.delete("/api/ui/product/tray-flow", params={"traycode": "T02001"}).status_code == 200
    assert client.get("/api/ui/product/flow-overview", params={"traycode": "T02001"}).json() == []
    assert client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "工位测试员",
        },
    ).status_code == 200


def test_workbench_inbound_rejects_more_than_tray_capacity(client, workbench_seeded):
    prepared = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02001",
            "operator": "工位测试员",
            "confirmed": True,
        },
    )
    assert prepared.status_code in {200, 404}, prepared.text
    response = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": [f"OVER-{index:02d}" for index in range(1, 22)],
            "operator": "工位测试员",
        },
    )
    assert response.status_code == 400
    assert "最多可填写 20" in response.json()["detail"]


def test_workbench_inbound_checks_tray_against_selected_step(
    client, workbench_seeded
):
    response = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "3",
            "traycode": "T02001",
            "barcodes": ["STEP-TRAY-0001"],
            "operator": "工位测试员",
        },
    )
    assert response.status_code == 400
    assert "产品 P-1001、工序 3" in response.json()["detail"]


def test_workbench_page_scans_tray_and_auto_submits(client, workbench_seeded):
    prepared = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02001",
            "operator": "工位测试员",
            "confirmed": True,
        },
    )
    assert prepared.status_code in {200, 404}, prepared.text
    prepared_again = client.post(
        "/api/ui/workbench/tray-unbind",
        json={
            "traycode": "T02002",
            "operator": "工位测试员",
            "confirmed": True,
        },
    )
    assert prepared_again.status_code in {200, 404}, prepared_again.text

    at = AppTest.from_file(
        str(UI_DIR / "workbench_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.title[0].value == "工位操作台"
    assert [item.label for item in at.tabs] == [
        "手动入站",
        "入线状态",
        "托盘解绑",
        "产品解锁",
    ]
    assert at.selectbox(key="workbench_product_model").value is None
    assert at.selectbox(key="workbench_process_step").disabled
    assert at.number_input(key="workbench_barcode_columns").value == 2
    at.number_input(key="workbench_barcode_columns").set_value(3).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    at.selectbox(key="workbench_product_model").select("P-1001").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.selectbox(key="workbench_process_step").value is None
    assert not at.selectbox(key="workbench_process_step").disabled
    assert not any(
        str(checkbox.key).startswith("workbench_barcode_enabled_")
        for checkbox in at.checkbox
    )
    at.selectbox(key="workbench_process_step").select("1 · S1").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    preview_token = at.session_state["workbench_inbound_token"]
    assert at.text_input(
        key=f"workbench_barcode_input_{preview_token}_1"
    ).disabled
    assert len([
        checkbox
        for checkbox in at.checkbox
        if str(checkbox.key).startswith(
            f"workbench_barcode_enabled_{preview_token}_"
        )
    ]) == 20

    at.text_input(key="workbench_inbound_tray_input").input("T02001").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert not at.error, [str(item.value) for item in at.error]
    assert at.session_state["workbench_inbound_capacity"] == 20
    assert at.text_input(key="workbench_inbound_tray_input").value == "T02001"
    token = at.session_state["workbench_inbound_token"]
    assert at.checkbox(key=f"workbench_barcode_enabled_{token}_1").value is True
    assert at.checkbox(key=f"workbench_barcode_enabled_{token}_20").value is True

    at.text_input(key=f"workbench_barcode_input_{token}_1").input("SCAN-0001").run()
    at.text_input(key=f"workbench_barcode_input_{token}_2").input("SCAN-0002").run()
    at.checkbox(key=f"workbench_barcode_enabled_{token}_2").set_value(False).run()
    assert at.session_state[f"workbench_barcode_enabled_{token}_2"] is False
    assert at.text_input(key=f"workbench_barcode_disabled_{token}_2").disabled
    assert at.text_input(key=f"workbench_barcode_disabled_{token}_2").value == "SCAN-0002"
    assert any("已输入 1/19" in item.value for item in at.caption)

    at.session_state["workbench_tabs"] = "托盘解绑"
    at.run()
    at.session_state["workbench_tabs"] = "手动入站"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.selectbox(key="workbench_product_model").value == "P-1001"
    assert at.selectbox(key="workbench_process_step").value == "1 · S1"
    assert at.number_input(key="workbench_barcode_columns").value == 3
    assert at.text_input(key="workbench_inbound_tray_input").value == "T02001"
    assert at.text_input(
        key=f"workbench_barcode_input_{token}_1"
    ).value == "SCAN-0001"
    assert at.text_input(
        key=f"workbench_barcode_disabled_{token}_2"
    ).value == "SCAN-0002"
    assert at.checkbox(key=f"workbench_barcode_enabled_{token}_2").value is False

    barcodes = [f"SCAN-{index:04d}" for index in range(3, 21)]
    for index, barcode in zip(range(3, 21), barcodes):
        at.text_input(key=f"workbench_barcode_input_{token}_{index}").input(
            barcode
        ).run()
        assert not at.exception, [str(item.value) for item in at.exception]
        assert not at.error, [str(item.value) for item in at.error]

    assert at.session_state["workbench_inbound_submitted"] is True
    assert at.text_input(key="workbench_inbound_tray_input").value == "T02001"
    assert at.text_input(
        key=f"workbench_barcode_locked_{token}_1"
    ).value == "SCAN-0001"
    assert any("19 个产品已入站" in item.value for item in at.success)
    overview = client.get(
        "/api/ui/product/flow-overview",
        params={"traycode": "T02001"},
    ).json()
    assert {row["barcode"] for row in overview} == {
        "SCAN-0001",
        *barcodes,
    }

    at.text_input(key="workbench_inbound_tray_input").input("T02002").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["workbench_inbound_submitted"] is False
    assert at.text_input(key="workbench_inbound_tray_input").value == "T02002"
    next_token = at.session_state["workbench_inbound_token"]
    assert at.text_input(
        key=f"workbench_barcode_input_{next_token}_1"
    ).value == ""
    at.text_input(key=f"workbench_barcode_input_{next_token}_1").input(
        "CLEAR-ME"
    ).run()
    at.button(key="workbench_inbound_clear").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.text_input(key="workbench_inbound_tray_input").value == ""
    cleared_token = at.session_state["workbench_inbound_token"]
    assert at.text_input(
        key=f"workbench_barcode_input_{cleared_token}_1"
    ).value == ""
    assert at.text_input(
        key=f"workbench_barcode_input_{cleared_token}_1"
    ).disabled


def test_workbench_page_is_read_only(workbench_seeded):
    at = AppTest.from_file(
        str(UI_DIR / "workbench_app.py"),
        default_timeout=90,
    )
    at.session_state["mes_role"] = "只读"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    at.selectbox(key="workbench_product_model").select("P-1001").run()
    at.selectbox(key="workbench_process_step").select("1 · S1").run()
    assert at.text_input(key="workbench_inbound_tray_input").disabled


def test_workbench_unlock_can_choose_target_step(client, workbench_seeded):
    push_result(
        client,
        "WB-LOCK",
        "TEST-01",
        test_item="人工解锁测试",
        result="FAIL",
        measured_value="NG",
        program_version="v1.2.0",
        product="",
    )
    at = AppTest.from_file(
        str(UI_DIR / "workbench_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    at.session_state["workbench_tabs"] = "产品解锁"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]

    step_select = at.selectbox(key="workbench_unlock_next_step")
    assert step_select.options == ["保持当前工序", "1 · S1", "2 · S2", "3 · S3"]
    step_select.select("2 · S2").run()
    at.text_input(key="workbench_unlock_scan_0").input("WB-LOCK").run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert not at.error, [str(item.value) for item in at.error]
    overview = client.get(
        "/api/ui/product/flow-overview",
        params={"barcode": "WB-LOCK"},
    ).json()
    assert overview[0]["board_status"] == "normal"
    assert overview[0]["current_step"] == "2"


def test_tag_page_delete_api_removes_entire_tray_status(
    client, workbench_seeded
):
    barcodes = ["TAG-DELETE-0001", "TAG-DELETE-0002"]
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "入线状态测试员",
        },
    )
    assert inbound.status_code == 200, inbound.text
    overview = client.get("/api/ui/product/flow-overview").json()
    affected = [row for row in overview if row["barcode"] in barcodes]
    flow_tables = [row["flow_table"] for row in affected]

    deleted = client.delete(
        "/api/ui/product/tray-flow",
        params={"traycode": "T02001"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["count"] == 2
    assert set(deleted.json()["barcodes"]) == set(barcodes)
    assert product_flow_store.list_overview(traycode="T02001") == []
    with product_flow_store._eng().connect() as conn:
        for flow_table in flow_tables:
            exists = conn.execute(
                text(
                    "SELECT count(*) FROM sqlite_master "
                    "WHERE type='table' AND name=:table"
                ),
                {"table": flow_table},
            ).scalar()
            assert exists == 0

    # 入线状态删除后，入站占位被释放；测试相关数据保持不变。
    detail = client.get(f"/api/ui/product/workpiece/{barcodes[0]}/detail")
    assert detail.status_code == 404


def test_tag_page_lists_status_without_enabled_and_confirms_delete(
    client, workbench_seeded
):
    barcodes = ["TAG-PAGE-0001", "TAG-PAGE-0002"]
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "入线状态测试员",
        },
    )
    assert inbound.status_code == 200, inbound.text

    at = AppTest.from_file(
        str(UI_DIR / "workbench_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    at.session_state["workbench_tabs"] = "入线状态"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.title[0].value == "工位操作台"
    assert len(at.dataframe) == 1
    assert list(at.dataframe[0].value.columns) == [
        "载具号",
        "条码数量",
        "产品条码",
        "当前工序",
        "操作",
    ]
    assert len(at.dataframe[0].value) == 1
    page_row = at.dataframe[0].value.iloc[0]
    assert page_row["载具号"] == "T02001"
    assert page_row["条码数量"] == 2
    assert set(str(page_row["产品条码"]).split("、")) == set(barcodes)

    assert "删除" not in at.dataframe[0].value.columns


@pytest.mark.parametrize(
    ("result", "is_final", "expected_status"),
    [
        ("PASS", True, "final"),
        ("FAIL", False, "lock"),
    ],
)
def test_terminal_result_auto_unbinds_entire_tray(
    client,
    workbench_seeded,
    result,
    is_final,
    expected_status,
):
    barcodes = [
        f"AUTO-{expected_status.upper()}-0001",
        f"AUTO-{expected_status.upper()}-0002",
    ]
    inbound = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "自动解绑测试员",
        },
    )
    assert inbound.status_code == 200, inbound.text

    _post_v1_result(
        client,
        barcode=barcodes[0],
        traycode="T02001",
        result=result,
        is_final=is_final,
    )

    overview = client.get(
        "/api/ui/product/flow-overview",
        params={"componentcode": "P-1001"},
    ).json()
    affected = [row for row in overview if row["barcode"] in barcodes]
    assert {row["traycode"] for row in affected} == {""}
    assert next(
        row for row in affected if row["barcode"] == barcodes[0]
    )["board_status"] == expected_status

    flow = client.get(
        "/api/ui/product/flow-details",
        params={"flow_table": affected[0]["flow_table"]},
    ).json()
    trigger = next(row for row in affected if row["barcode"] == barcodes[0])
    trigger_flow = client.get(
        "/api/ui/product/flow-details",
        params={"flow_table": trigger["flow_table"]},
    ).json()
    assert trigger_flow[-1]["device"] == "TEST-03"
    assert trigger_flow[-1]["note"] in {"test pass", "test fail"}
    assert all(row["device"] != "托盘自动解绑" for row in trigger_flow)
    assert all(row["device"] != "托盘自动解绑" for row in flow)


def test_tag_page_shows_only_flowing_trays(
    client,
    workbench_seeded,
):
    ending = "TAG-END-0001"
    sibling = "TAG-END-0002"
    bound = "TAG-BOUND-0001"
    for traycode, barcodes in (
        ("T02001", [ending, sibling]),
        ("T02002", [bound]),
    ):
        response = client.post(
            "/api/ui/workbench/inbound",
            json={
                "product": "P-1001",
                "step_no": "1",
                "traycode": traycode,
                "barcodes": barcodes,
                "operator": "状态展示测试员",
            },
        )
        assert response.status_code == 200, response.text
    _post_v1_result(
        client,
        barcode=ending,
        traycode="T02001",
        result="PASS",
        is_final=True,
    )

    at = AppTest.from_file(
        str(UI_DIR / "workbench_app.py"),
        default_timeout=90,
    ).run()
    at.session_state["workbench_tabs"] = "入线状态"
    at.run()

    assert not at.exception, [str(item.value) for item in at.exception]
    rows = at.dataframe[0].value
    ending_row = rows[rows["载具号"] == "T02001"].iloc[0]
    assert ending_row["条码数量"] == 1
    assert ending_row["产品条码"] == sibling
    assert ending not in str(ending_row["产品条码"])
    bound_row = rows[rows["载具号"] == "T02002"].iloc[0]
    assert bound_row["条码数量"] == 1
    assert bound_row["产品条码"] == bound


def test_auto_unbind_terminal_trays_cleans_existing_bindings(
    client,
    workbench_seeded,
):
    barcodes = ["AUTO-MIGRATE-0001", "AUTO-MIGRATE-0002"]
    response = client.post(
        "/api/ui/workbench/inbound",
        json={
            "product": "P-1001",
            "step_no": "1",
            "traycode": "T02001",
            "barcodes": barcodes,
            "operator": "自动解绑迁移测试员",
        },
    )
    assert response.status_code == 200, response.text
    with product_flow_store._eng().begin() as conn:
        conn.execute(
            text(
                "UPDATE product_overview SET board_status = 'lock' "
                "WHERE barcode = :barcode"
            ),
            {"barcode": barcodes[0]},
        )

    assert product_flow_store.auto_unbind_terminal_trays(
        changed_at="2026-11-21T16:30:00+08:00"
    ) == ["T02001"]
    rows = product_flow_store.list_overview(componentcode="P-1001")
    affected = [row for row in rows if row["barcode"] in barcodes]
    assert {row["traycode"] for row in affected} == {""}
    assert {row["last_report_device"] for row in affected} == {"手动入站"}
    assert all(
        "托盘自动解绑" not in row["last_report_note"] for row in affected
    )
