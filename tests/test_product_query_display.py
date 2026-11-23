"""产品查询展示规则测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

UI_DIR = Path(__file__).resolve().parent / "ui_apps"


def test_product_query_shows_last_test_report_traycode(client, seeded):
    traycodes = client.get("/api/ui/product/report-traycodes").json()
    by_barcode = {row["barcode"]: row["traycode"] for row in traycodes}
    assert by_barcode["SN202611180001"] == "T02001"

    flow_row = next(
        row
        for row in client.get("/api/ui/product/flow-overview").json()
        if row["barcode"] == "SN202611180001"
    )
    assert flow_row["traycode"] == ""

    at = AppTest.from_file(
        str(UI_DIR / "product_query_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    frame = at.dataframe[0].value
    row = frame[frame["barcode"] == "SN202611180001"].iloc[0]
    assert row["traycode"] == "T02001"


def test_report_query_by_product_and_step_reads_unified_db(client, seeded):
    options = client.get("/api/ui/product/report-filter-options").json()
    step_values = {row["step_no"]: row for row in options["steps"]}
    assert step_values["1"]["db_name"] == "TestReport.db"
    assert "L120201091" in options["products"]

    response = client.get(
        "/api/ui/product/report-query",
        params={"product": "L120201091", "step_no": "1"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert {row["source_db"] for row in rows} == {"TestReport.db"}
    assert {row["componentcode"] for row in rows} == {"L120201091"}
    assert {row["step_no"] for row in rows} == {"1"}

    at = AppTest.from_file(
        str(UI_DIR / "product_query_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert [tab.label for tab in at.tabs] == [
        "产品流转查询",
        "测试报告查询",
    ]
    at.session_state["pq_tabs"] = "测试报告查询"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    labels = [select.label for select in at.selectbox]
    for label in [
        "barcode",
        "componentcode",
        "traycode",
        "board_status",
        "current_step",
        "last_report_device",
        "step_no",
        "result",
    ]:
        assert label in labels
    at.selectbox(key="pq_report_product").select("L120201091")
    at.selectbox(key="pq_report_step").select("1 · S1")
    at.button(key="pq_report_query_btn").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    report_table = at.dataframe(key="pq_report_result_table")
    assert list(report_table.value.columns)[:3] == [
        "barcode",
        "step_no",
        "source_db",
    ]
    # 查询按钮只在点击的 rerun 为 True；后续 rerun 保留结果表但不显示旧详情。
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.dataframe(key="pq_report_result_table").value.shape[0] == 1
    assert at.session_state.get("pq_report_detail_caption") is None
    assert at.session_state.get("pq_report_details_caption") is None
    assert at.session_state.get("pq_report_details_title_markdown") is None
