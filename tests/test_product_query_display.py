"""产品查询展示规则测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

UI_DIR = Path(__file__).resolve().parent / "ui_apps"

def test_result_table_ignores_stale_selection_index(client, seeded, monkeypatch):
    from py_server.ui import page_product_query

    class FakeEvent:
        class Selection:
            rows = [999]

        selection = Selection()

    monkeypatch.setattr(page_product_query.st, "dataframe", lambda *args, **kwargs: FakeEvent())

    class NullContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(page_product_query.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(page_product_query.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(page_product_query.st, "rerun", lambda *args, **kwargs: None)
    st_session = page_product_query.st.session_state
    st_session["pq_current"] = "SN202611180001"
    page_product_query._render_results([{"barcode": "SN202611180001"}])
    assert st_session.get("pq_current") is None

def test_product_query_uses_product_overview_and_hides_id(client, seeded):
    flow_row = next(
        row
        for row in client.get("/api/ui/product/flow-overview").json()
        if row["barcode"] == "SN202611180001"
    )
    assert "tray_slot" in flow_row

    at = AppTest.from_file(
        str(UI_DIR / "product_query_app.py"),
        default_timeout=90,
    ).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    frame = at.dataframe[0].value
    row = frame[frame["barcode"] == "SN202611180001"].iloc[0]
    assert row["traycode"] == flow_row["traycode"]
    assert "id" not in frame.columns
    assert list(frame.columns).index("tray_slot") == list(frame.columns).index("traycode") + 1


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
        "工件流转查询",
        "测试报告查询",
    ]
    at.session_state["pq_tabs"] = "测试报告查询"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    labels = [select.label for select in at.selectbox]
    for label in [
        "barcode",
        "componentcode",
        "station",
        "fixturecode",
        "traycode",
        "step_no",
        "result",
        "isfinalreport",
    ]:
        assert label in labels
    at.selectbox(key="pq_report_product").select("L120201091")
    at.selectbox(key="pq_report_step").select("1 · S1")
    at.button(key="pq_report_query_btn").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    report_table = at.dataframe(key="pq_report_result_table")
    assert list(report_table.value.columns)[:3] == [
        "barcode",
        "componentcode",
        "station",
    ]
    assert list(report_table.value.columns) == [
        "barcode",
        "componentcode",
        "station",
        "fixturecode",
        "traycode",
        "programname",
        "programversion",
        "testexecutetime",
        "testlongtime",
        "result",
        "isfinalreport",
    ]
    # 查询按钮只在点击的 rerun 为 True；后续 rerun 保留结果表但不显示旧详情。
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.dataframe(key="pq_report_result_table").value.shape[0] >= 1
    assert at.session_state.get("pq_report_detail_caption") is None
    assert at.session_state.get("pq_report_details_caption") is None
    assert at.session_state.get("pq_report_details_title_markdown") is None
