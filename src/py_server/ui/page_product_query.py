"""页面：产品查询（工件流转追溯 + 测试履历 + 测试报告查询）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import client, common
from ..constants import MISSING_TRAYCODE, is_missing_traycode
from .client import ApiError as ServiceError
from .pages.constants import (
    PAGE_TITLE_PRODUCT_QUERY,
    QUERY_BUTTON,
    QUERY_CONDITIONS_SECTION,
    QUERY_RESULTS_SECTION,
)



def _result_frame(results: list[dict]) -> pd.DataFrame:
    """工件流转查询：按 product_overview 字段顺序展示，隐藏内部 id。"""
    frame = pd.DataFrame([dict(row) for row in results])
    if "id" in frame.columns:
        frame = frame.drop(columns=["id"])
    return frame


def _report_query_frame(results: list[dict]) -> pd.DataFrame:
    """测试报告总览列表：按 mesUploadTestDataFormat.json 主字段顺序展示。"""
    frame = pd.DataFrame([{
        "barcode": r.get("barcode") or "",
        "componentcode": r.get("componentcode") or "",
        "station": r.get("station") or "",
        "fixturecode": r.get("fixturecode") or "/",
        "traycode": MISSING_TRAYCODE if is_missing_traycode(r.get("traycode")) else r.get("traycode"),
        "programname": r.get("programname") or "",
        "programversion": r.get("programversion") or "",
        "testexecutetime": r.get("testexecutetime") or "",
        "testlongtime": r.get("testlongtime") or "",
        "result": r.get("result") or "",
        "isfinalreport": r.get("isfinalreport") or "",
    } for r in results])
    return frame


def _render_report_query() -> None:
    """按指定产品型号和测试工序直接查询工序报告库。"""
    try:
        options = client.report_filter_options()
    except ServiceError as exc:
        st.error(f"读取测试报告筛选项失败：{exc}")
        return

    def opts(values):
        """执行 opts。"""
        return ["全部"] + sorted({str(v) for v in values if v not in (None, "")})

    barcode_options = opts(options.get("barcodes", []))
    product_options = opts(options.get("products", []))
    traycode_options = opts(options.get("traycodes", []))
    fixturecode_options = opts(options.get("fixturecodes", []))
    result_options = ["全部", "PASS", "FAIL"]
    isfinalreport_options = ["全部", "true", "false"]
    steps = options.get("steps", [])
    display_step_options = [
        "全部",
        *[
            f"{row['step_no']} · {row['step_name'] or row['db_name']}"
            for row in steps
        ],
    ]
    step_display_to_no = {
        f"{row['step_no']} · {row['step_name'] or row['db_name']}": row["step_no"]
        for row in steps
    }

    with st.container(border=True):
        st.subheader(QUERY_CONDITIONS_SECTION)
        c1, c2, c3, c4 = st.columns(4)
        report_barcode = c1.selectbox(
            "barcode",
            barcode_options,
            key="pq_report_barcode",
            persist_state="session",
        )
        report_product = c2.selectbox(
            "componentcode",
            product_options,
            key="pq_report_product",
            persist_state="session",
        )
        report_station = c3.selectbox(
            "station",
            opts(options.get("stations", [])),
            key="pq_report_station",
            persist_state="session",
        )
        report_fixturecode = c4.selectbox(
            "fixturecode",
            fixturecode_options,
            key="pq_report_fixturecode",
            persist_state="session",
        )
        c5, c6, c7, c8 = st.columns(4)
        report_traycode = c5.selectbox(
            "traycode",
            traycode_options,
            key="pq_report_traycode",
            persist_state="session",
        )
        report_result = c6.selectbox(
            "result",
            result_options,
            key="pq_report_result",
            persist_state="session",
        )
        report_isfinalreport = c7.selectbox(
            "isfinalreport",
            isfinalreport_options,
            key="pq_report_isfinalreport",
            persist_state="session",
        )
        report_step_display = c8.selectbox(
            "step_no",
            display_step_options,
            key="pq_report_step",
            persist_state="session",
        )
        submitted = st.button(QUERY_BUTTON, key="pq_report_query_btn", icon=":material/search:")

    if submitted:
        try:
            rows = client.report_query(
                product=None if report_product == "全部" else report_product,
                step_no=step_display_to_no.get(report_step_display),
                barcode=None if report_barcode == "全部" else report_barcode,
                traycode=None if report_traycode == "全部" else report_traycode,
                fixturecode=None if report_fixturecode == "全部" else report_fixturecode,
                result=None if report_result == "全部" else report_result,
                isfinalreport=None if report_isfinalreport == "全部" else report_isfinalreport,
                last_report_device=None if report_station == "全部" else report_station,
            )
        except ServiceError as exc:
            st.error(f"查询测试报告失败：{exc}")
            return
        st.session_state["pq_report_rows"] = rows
        st.session_state.pop("pq_report_current", None)

    if "pq_report_rows" not in st.session_state:
        try:
            rows = client.report_query()
        except ServiceError as exc:
            st.error(f"读取测试报告失败：{exc}")
            rows = []
        st.session_state["pq_report_rows"] = rows
    rows = st.session_state.get("pq_report_rows", [])
    if submitted and not rows:
        st.info("暂无匹配测试报告")
        return
    if not rows:
        return

    event = st.dataframe(
        _report_query_frame(rows),
        hide_index=True,
        width="stretch",
        height=280,
        alt="按产品型号和测试工序查询的测试报告列表",
        on_select="rerun",
        selection_mode="single-row",
        key="pq_report_result_table",
    )
    selection = event.selection.rows if hasattr(event, "selection") else []
    selected = None
    if selection:
        idx = selection[0]
        if isinstance(idx, int) and 0 <= idx < len(rows):
            selected = rows[idx]
            key = f"{selected.get('barcode')}|{selected.get('step_no')}|{selected.get('id')}"
            st.session_state["pq_report_current"] = key
        else:
            st.session_state.pop("pq_report_current", None)
    else:
        st.session_state.pop("pq_report_current", None)
        st.session_state.pop("pq_report_detail_caption", None)
        st.session_state.pop("pq_report_details_caption", None)
        st.session_state.pop("pq_report_details_title_markdown", None)
    _render_selected_report_detail(selected)


def _render_selected_report_detail(selected: dict | None = None) -> None:
    """执行 render_selected_report_detail。"""
    if selected is None:
        return
    barcode = str(selected.get("barcode") or "")
    step_no = str(selected.get("step_no") or "") or None
    st.markdown("**测试报告明细**")
    with st.container(border=True):
        st.caption(
            f"工件条码 {barcode} · 工序 {step_no or '默认'} · "
            f"来源 {selected.get('source_db') or ''}"
        )
        st.session_state["pq_report_detail_caption"] = "选中的测试报告总览"
        st.dataframe(
            pd.DataFrame([{
                "barcode": selected.get("barcode") or "",
                "componentcode": selected.get("componentcode") or "",
                "station": selected.get("station") or "",
                "fixturecode": selected.get("fixturecode") or "/",
        "traycode": MISSING_TRAYCODE if is_missing_traycode(selected.get("traycode")) else selected.get("traycode"),
                "programname": selected.get("programname") or "",
                "programversion": selected.get("programversion") or "",
                "testexecutetime": selected.get("testexecutetime") or "",
                "testlongtime": selected.get("testlongtime") or "",
                "result": selected.get("result") or "",
                "isfinalreport": selected.get("isfinalreport") or "",
                "failed_step": selected.get("failed_step") or "",
            }]),
            hide_index=True,
            width="stretch",
            alt="选中的测试报告总览",
        )
        details_table = str(selected.get("details_table") or "")
        if not details_table:
            st.info("该测试报告暂无测试明细")
            return
        try:
            details = client.report_details(details_table, step_no)
        except ServiceError as exc:
            st.error(f"读取测试明细失败：{exc}")
            return
        if not details:
            st.info("该报告暂无明细")
            return
        detail_frame = pd.DataFrame(details)
        if "id" in detail_frame.columns:
            detail_frame = detail_frame.drop(columns=["id"])
        detail_frame.insert(0, "序号", range(1, len(detail_frame) + 1))
        st.session_state["pq_report_details_caption"] = "选中的测试报告明细"
        st.session_state["pq_report_details_title_markdown"] = "**测试明细**"
        st.markdown(st.session_state["pq_report_details_title_markdown"])
        st.dataframe(
            detail_frame,
            hide_index=True,
            width="stretch",
            alt="选中的测试报告明细",
        )


def _render_query() -> list[dict]:
    """查询 product_overview；筛选项同样来自 product_overview。"""
    with st.container(border=True):
        st.subheader(QUERY_CONDITIONS_SECTION)
        try:
            overview_rows = client.product_flow_overview()
        except ServiceError:
            overview_rows = []
        def opts(values):
            """执行 opts。"""
            return ["全部"] + sorted({str(v) for v in values if v not in (None, "")})
        products = opts([r.get("componentcode") for r in overview_rows])
        process_codes = opts([r.get("process_code") for r in overview_rows])
        workpiece_options = opts([r.get("barcode") for r in overview_rows])
        traycodes = opts([r.get("traycode") for r in overview_rows])
        tray_slots = opts([r.get("tray_slot") for r in overview_rows])
        test_step_options = opts([r.get("current_step") for r in overview_rows])

        c1, c2, c3, c4 = st.columns(4)
        workpiece = c1.selectbox("barcode", workpiece_options, key="pq_workpiece")
        product = c2.selectbox("componentcode", products, key="pq_product")
        process_code = c3.selectbox("process_code", process_codes, key="pq_process_code")
        traycode = c4.selectbox("traycode", traycodes, key="pq_traycode")
        c5, c6, c7, _ = st.columns(4)
        tray_slot = c5.selectbox("tray_slot", tray_slots, key="pq_tray_slot")
        board_status = c6.selectbox("board_status", ["全部", "normal", "lock", "final"], key="pq_board_status")
        test_step = c7.selectbox("current_step", test_step_options, key="pq_test_step")
        query = st.button(QUERY_BUTTON, key="pq_query_btn", icon=":material/search:")

    # 结果常驻 session_state：首次进入自动加载全部；之后只在点“查询”时更新
    if "pq_results" not in st.session_state:
        st.session_state["pq_results"] = overview_rows

    if query:
        try:
            st.session_state["pq_results"] = client.product_flow_overview(
                barcode=None if workpiece == "全部" else workpiece,
                componentcode=None if product == "全部" else product,
                process_code=None if process_code == "全部" else process_code,
                traycode=None if traycode == "全部" else traycode,
                tray_slot=None if tray_slot == "全部" else tray_slot,
                board_status=None if board_status == "全部" else board_status,
                current_step=None if test_step == "全部" else test_step,
            )
            # 已选工件若仍在新结果中则保留；否则清掉，避免详情指向旧数据
            current = st.session_state.get("pq_current")
            ids = [r.get("barcode") or "" for r in st.session_state["pq_results"]]
            if current and current not in ids:
                st.session_state.pop("pq_current", None)
        except ServiceError as exc:
            st.error(f"查询失败：{exc}")
    return st.session_state["pq_results"]


def _render_results(results: list[dict]) -> None:
    """执行 render_results。"""
    with st.container(border=True):
        st.subheader(QUERY_RESULTS_SECTION)
        if not results:
            st.info("暂无结果，请调整查询条件")
            st.session_state.pop("pq_current", None)
            return
        frame = _result_frame(results)
        event = st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=260,
            alt="工件流转查询结果列表（点击行查看流转明细和测试履历）",
            on_select="rerun",
            selection_mode="single-row",
            key="pq_result_table",
        )
        rows = event.selection.rows if hasattr(event, "selection") else []
        if rows:
            idx = rows[0]
            if not isinstance(idx, int) or idx < 0 or idx >= len(results):
                st.session_state.pop("pq_current", None)
                st.rerun()
                return
            selected = results[idx].get("barcode") or ""
            if not selected:
                st.session_state.pop("pq_current", None)
                st.rerun()
                return
            if st.session_state.get("pq_current") != selected:
                st.session_state["pq_current"] = selected
                st.rerun()
        elif st.session_state.get("pq_current"):
            # 取消勾选：清掉暂存的选中条码，下方明细不再显示
            st.session_state.pop("pq_current", None)
            st.rerun()


def _render_test_history(tests: list[dict], barcode: str, step_no: str | None = None) -> None:
    """测试履历分两块：总览表（选中一条）+ 下方显示该条 details。"""
    # 上块：总览表
    st.markdown("**测试报告总览**")
    try:
        overview = client.report_index(barcode, step_no)
    except ServiceError as exc:
        st.error(f"读取总览失败：{exc}")
        overview = []
    if not overview:
        st.info("该工件暂无测试报告总览")
        return

    # 列顺序严格按 mesUploadTestDataFormat.json 的字段顺序
    ov_frame = pd.DataFrame([{
        "station": r.get("station") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": MISSING_TRAYCODE if is_missing_traycode(r.get("traycode")) else r.get("traycode"),
        "barcode": r.get("barcode") or "",
        "programname": r.get("programname") or "",
        "programversion": r.get("programversion") or "",
        "testexecutetime": r.get("testexecutetime") or "",
        "testlongtime": r.get("testlongtime") or "",
        "result": r.get("result") or "",
        "isfinalreport": r.get("isfinalreport") or "",
        "failed_step": r.get("failed_step") or "",
    } for r in overview])
    event = st.dataframe(
        ov_frame, hide_index=True, width="stretch", height=200,
        alt="测试报告总览列表（点击行查看明细）",
        on_select="rerun", selection_mode="single-row",
        key=f'pq_overview_{barcode}_{step_no or "all"}',
    )
    rows = event.selection.rows if hasattr(event, "selection") else []
    if not rows:
        st.info("请点击上方总览中的一行查看测试明细")
        return
    selected = overview[rows[0]]

    # 下块：details
    st.markdown("**测试明细**")
    try:
        details = client.report_details(selected["details_table"], step_no)
    except ServiceError as exc:
        st.error(f"读取明细失败：{exc}")
        return
    if not details:
        st.info("该报告暂无明细")
        return
    # 列名完全来自数据库；只按当前顺序补一列自增 ID 在最前
    df = pd.DataFrame(details)
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    df.insert(0, "序号", range(1, len(df) + 1))
    st.dataframe(df, hide_index=True, width="stretch", alt="测试明细列表（列来自数据库）")


def _render_product_flow(barcode: str | None = None) -> None:
    """按选中行的 flow_table 列出对应流转明细。"""
    if not barcode:
        st.info("请先选择一条查询结果")
        return
    try:
        overview = client.product_flow_overview(barcode)
    except ServiceError as exc:
        st.error(f"读取工件流转总览失败：{exc}")
        return
    if not overview:
        st.info("暂无工件流转数据")
        return
    selected = overview[0]
    flow_table = str(selected.get("flow_table") or "")
    if not flow_table:
        st.info("该工件暂无流转明细")
        return
    try:
        details = client.product_flow_details(flow_table)
    except ServiceError as exc:
        st.error(f"读取具体流转失败：{exc}")
        return
    if not details:
        st.info("该工件暂无流转记录")
        return
    frame = pd.DataFrame(details)
    if "id" in frame.columns:
        frame = frame.drop(columns=["id"])
    st.dataframe(frame, hide_index=True, width="stretch", alt="工件具体流转记录")

def render() -> None:
    """执行 render。"""
    st.title(PAGE_TITLE_PRODUCT_QUERY)
    st.caption("按条件查询 product_overview；选中行后显示流转明细和测试履历。")
    common.render_flash()
    common.render_readonly_notice()

    flow_tab, report_tab = st.tabs(
        ["工件流转查询", "测试报告查询"],
        key="pq_tabs",
        on_change="rerun",
    )
    if flow_tab.open:
        with flow_tab:
            results = _render_query()
            _render_results(results)

            current = st.session_state.get("pq_current")
            if current:
                with st.container(border=True):
                    st.subheader("流转明细")
                    _render_product_flow(current)
                with st.container(border=True):
                    st.subheader("测试履历")
                    try:
                        history_rows = client.report_index(current)
                    except ServiceError:
                        history_rows = []
                    try:
                        steps = {
                            str(x.get("step_no")): str(x.get("step_name") or "")
                            for x in client.step_options()
                        }
                    except ServiceError:
                        steps = {}
                    available_steps = sorted({
                        str(row.get("step_no") or "")
                        for row in history_rows
                        if str(row.get("step_no") or "")
                    }, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
                    if available_steps:
                        hist_tabs = st.tabs(
                            [f"{no}-{steps.get(no, '')}".rstrip("-") for no in available_steps]
                        )
                        for idx, no in enumerate(available_steps):
                            with hist_tabs[idx]:
                                _render_test_history(history_rows, current, no)
                    else:
                        st.info("当前产品暂无测试履历数据")
                        _render_test_history([], current)

    if report_tab.open:
        with report_tab:
            _render_report_query()
