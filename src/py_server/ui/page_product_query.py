"""页面：产品查询（工件追溯 + 工件解锁）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import config
from . import client, common
from ..constants import MISSING_TRAYCODE, is_missing_traycode
from .client import ApiError as ServiceError
from .pages.constants import (
    PAGE_TITLE_PRODUCT_QUERY,
    QUERY_BUTTON,
    QUERY_CONDITIONS_SECTION,
    QUERY_RESULTS_SECTION,
)

STATUS_OPTIONS = ["全部", "PENDING", "PASS", "FAIL"]


def _status_text(row: dict) -> str:
    """执行 status_text。"""
    parts = [row.get("status") or ""]
    if row.get("lock_reason"):
        parts.append("🔒")
    return " ".join(parts)


def _result_frame(results: list[dict], *, report_trays: dict[str, str]) -> pd.DataFrame:
    """产品查询的托盘码取最后一次测试上报，不取当前托盘绑定。"""
    return pd.DataFrame([{
        "id": r.get("id") or "",
        "barcode": r.get("barcode") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": (
            MISSING_TRAYCODE
            if is_missing_traycode(report_trays.get(str(r.get("barcode") or ""), ""))
            else report_trays.get(str(r.get("barcode") or ""), "")
        ),
        "board_status": r.get("board_status") or "",
        "current_step": r.get("current_step") or "",
        "last_report_device": r.get("last_report_device") or "",
        "last_report_note": r.get("last_report_note") or "",
        "updated_at": r.get("updated_at") or "",
    } for r in results])


def _report_query_frame(results: list[dict]) -> pd.DataFrame:
    """执行 report_query_frame。"""
    return pd.DataFrame([{
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
        "failed_step": r.get("failed_step") or "",
        "step_no": r.get("step_no") or "",
        "source_db": r.get("source_db") or "",
    } for r in results])


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

    product_options = opts(options.get("products", []))
    barcode_options = opts(options.get("barcodes", []))
    traycode_options = opts(options.get("traycodes", []))
    fixturecode_options = opts(options.get("fixturecodes", []))
    device_options = opts(options.get("stations", []))
    board_status_options = ["全部", "normal", "lock", "final"]
    result_options = ["全部", "PASS", "FAIL"]
    steps = options.get("steps", [])
    step_labels = {
        row["step_no"]: row["step_no"]
        for row in steps
    }
    step_options = ["全部", *step_labels]
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
        c1, c2, c3 = st.columns(3)
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
        report_traycode = c3.selectbox(
            "traycode",
            traycode_options,
            key="pq_report_traycode",
            persist_state="session",
        )
        c4, c5, c6 = st.columns(3)
        report_fixturecode = c4.selectbox(
            "fixturecode",
            fixturecode_options,
            key="pq_report_fixturecode",
            persist_state="session",
        )
        report_board_status = c5.selectbox(
            "board_status",
            board_status_options,
            key="pq_report_board_status",
            persist_state="session",
        )
        report_current_step = c6.selectbox(
            "current_step",
            step_options,
            key="pq_report_current_step",
            persist_state="session",
        )
        c7, c8, c9 = st.columns(3)
        report_device = c7.selectbox(
            "last_report_device",
            device_options,
            key="pq_report_last_report_device",
            persist_state="session",
        )
        report_step_display = c8.selectbox(
            "step_no",
            display_step_options,
            key="pq_report_step",
            persist_state="session",
        )
        report_result = c9.selectbox(
            "result",
            result_options,
            key="pq_report_result",
            persist_state="session",
        )
        submitted = st.button(QUERY_BUTTON, key="pq_report_query_btn", icon=":material/search:")

    if submitted:
        if report_step_display == "全部" and report_product == "全部":
            st.info("请选择产品型号或测试工序后查询")
            return
        try:
            rows = client.report_query(
                product=None if report_product == "全部" else report_product,
                step_no=step_display_to_no.get(report_step_display),
                barcode=None if report_barcode == "全部" else report_barcode,
                traycode=None if report_traycode == "全部" else report_traycode,
                fixturecode=None if report_fixturecode == "全部" else report_fixturecode,
                result=None if report_result == "全部" else report_result,
                board_status=None if report_board_status == "全部" else report_board_status,
                current_step=None if report_current_step == "全部" else report_current_step,
                last_report_device=None if report_device == "全部" else report_device,
            )
        except ServiceError as exc:
            st.error(f"查询测试报告失败：{exc}")
            return
        st.session_state["pq_report_rows"] = rows
        st.session_state.pop("pq_report_current", None)

    rows = st.session_state.get("pq_report_rows", [])
    if submitted and not rows:
        st.info("暂无匹配测试报告")
        return
    if not rows:
        return

    event = st.dataframe(
        _report_query_frame(rows)[[
            "barcode", "componentcode", "station", "fixturecode", "traycode",
            "programname", "programversion", "testexecutetime", "testlongtime",
            "result", "isfinalreport", "failed_step", "step_no", "source_db",
        ]],
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
        selected = rows[selection[0]]
        key = f"{selected.get('barcode')}|{selected.get('step_no')}|{selected.get('id')}"
        st.session_state["pq_report_current"] = key
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
    """执行 render_query。"""
    try:
        report_trays = client.latest_report_traycodes()
    except ServiceError:
        report_trays = {}
    st.session_state["pq_report_traycodes"] = report_trays
    with st.container(border=True):
        st.subheader(QUERY_CONDITIONS_SECTION)
        # 选项来自产品流转总览表
        try:
            all_wps = client.query_workpieces(limit=500)
        except ServiceError:
            all_wps = []
        def opts(values):
            """执行 opts。"""
            return ["全部"] + sorted({str(v) for v in values if v not in (None, "")})
        products = opts([r.get("componentcode") for r in all_wps])
        traycodes = opts(report_trays.values())
        workpiece_options = opts([r.get("barcode") for r in all_wps])
        device_options = opts(
            [r.get("last_report_device") for r in all_wps]
        )
        board_status_options = ["全部", "normal", "lock", "final"]
        test_step_options = opts(
            [r.get("test_step") for r in all_wps] + [r.get("current_step") for r in all_wps]
        )

        # 顺序按 product_overview 字段顺序：barcode/componentcode/traycode/board_status/current_step/last_report_device
        c1, c2, c3 = st.columns(3)
        workpiece = c1.selectbox("barcode", workpiece_options, key="pq_workpiece")
        product = c2.selectbox("componentcode", products, key="pq_product")
        traycode = c3.selectbox("traycode", traycodes, key="pq_traycode")
        c4, c5, c6 = st.columns(3)
        board_status = c4.selectbox("board_status", board_status_options, key="pq_board_status")
        test_step = c5.selectbox("current_step", test_step_options, key="pq_test_step")
        device = c6.selectbox("last_report_device", device_options, key="pq_device")
        query = st.button(QUERY_BUTTON, key="pq_query_btn", icon=":material/search:")

    # 结果常驻 session_state：首次进入自动加载全部；之后只在点“查询”时更新
    if "pq_results" not in st.session_state:
        st.session_state["pq_results"] = client.query_workpieces(limit=500)
        st.session_state["pq_results"] = [
            {
                **row,
                "barcode": row.get("workpiece") or "",
                "componentcode": row.get("product") or "",
                "traycode": report_trays.get(
                    str(row.get("workpiece") or ""), ""
                ),
            }
            for row in st.session_state["pq_results"]
        ]

    if query:
        params = {"limit": 200}
        if product != "全部":
            params["product"] = product
        if workpiece != "全部":
            params["workpiece"] = workpiece
        if device != "全部":
            params["device"] = device
        if board_status != "全部":
            params["board_status"] = board_status
        if test_step != "全部":
            params["test_step"] = test_step
        try:
            new_results = client.query_workpieces(
                workpiece=None if workpiece == "全部" else workpiece,
                product=None if product == "全部" else product,
                device=None if device == "全部" else device,
                board_status=None if board_status == "全部" else board_status,
                current_step=None if test_step == "全部" else test_step,
                limit=500,
            )
            st.session_state["pq_results"] = [
                {
                    **row,
                    "barcode": row.get("workpiece") or "",
                    "componentcode": row.get("product") or "",
                    "traycode": report_trays.get(
                        str(row.get("workpiece") or ""), ""
                    ),
                }
                for row in new_results
            ]
            if traycode != "全部":
                st.session_state["pq_results"] = [
                    row
                    for row in st.session_state["pq_results"]
                    if row["traycode"] == traycode
                ]
            # 已选工件若仍在新结果中则保留；否则清掉，避免详情指向旧数据
            current = st.session_state.get("pq_current")
            ids = [r.get("workpiece") or r.get("barcode") or "" for r in new_results]
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
        frame = _result_frame(
            results,
            report_trays=st.session_state.get("pq_report_traycodes", {}),
        )
        event = st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=260,
            alt="工件查询结果列表（点击行查看追溯）",
            on_select="rerun",
            selection_mode="single-row",
            key="pq_result_table",
        )
        rows = event.selection.rows if hasattr(event, "selection") else []
        if rows:
            idx = rows[0]
            selected = results[idx]["barcode"]
            if st.session_state.get("pq_current") != selected:
                st.session_state["pq_current"] = selected
                st.rerun()
        elif st.session_state.get("pq_current"):
            # 取消勾选：清掉暂存的选中条码，下方的测试履历/追溯不再显示
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
    """产品流转：上块总览表，点行选产品，下块显示该产品具体流转表。"""
    st.markdown("**工件流转总览**")
    try:
        overview = client.product_flow_overview(barcode)
    except ServiceError as exc:
        st.error(f"读取工件流转总览失败：{exc}")
        return
    if not overview:
        st.info("暂无工件流转数据")
        return
    # 表头使用 product_overview 数据库字段名
    frame = pd.DataFrame([{
        "id": r["id"],
        "barcode": r.get("barcode") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": MISSING_TRAYCODE if is_missing_traycode(r.get("traycode")) else r.get("traycode"),
        "board_status": r.get("board_status") or "",
        "current_step": r.get("current_step") or "",
        "last_report_device": r.get("last_report_device") or "",
        "last_report_note": r.get("last_report_note") or "",
        "updated_at": r.get("updated_at") or "",
    } for r in overview])
    # 总览只展示当前条码对应的一行
    st.dataframe(frame.head(1), hide_index=True, width="stretch", alt="工件流转总览")
    selected = overview[0]
    st.caption(f"具体流转记录：{selected['barcode']}")
    try:
        details = client.product_flow_details(selected["flow_table"])
    except ServiceError as exc:
        st.error(f"读取具体流转失败：{exc}")
        return
    if not details:
        st.info("该工件暂无流转记录")
        return
    st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch", alt="工件具体流转记录")


def _render_detail(wp_id: str) -> None:
    """执行 render_detail。"""
    editable = common.can_edit()
    try:
        detail = client.workpiece_detail(wp_id)
    except ServiceError as exc:
        st.error(f"读取追溯失败：{exc}")
        return

    with st.container(border=True):
        st.subheader(f"追溯明细：{wp_id}")

        # 工艺路线
        product = detail.get("product")
        if product:
            try:
                route = client.product_route(product).get("route", [])
                if route:
                    rf = pd.DataFrame([
                        {
                            "工序": r["step_no"],
                            "成功下站": str(r.get("success_next_step") or ""),
                            "失败下站": str(r.get("fail_next_step") or ""),
                        }
                        for r in route
                    ])
                    with st.expander("工艺路线", expanded=False):
                        st.dataframe(rf, hide_index=True, width="stretch", alt="产品工艺路线表")
                else:
                    st.caption("该工件未配置工序流程")
            except ServiceError:
                pass

        # 工件流转（顺序排列，不用 tab）
        st.markdown("**工件流转**")
        _render_product_flow(wp_id)

        # 工件解锁（顺序排列，不用 tab）
        st.markdown("**工件解锁**")
        if not editable:
            st.info("只读角色不可执行工件解锁")
            return

        flow_locked = False
        try:
            flow_rows = client.product_flow_overview(wp_id)
            flow_locked = bool(flow_rows and flow_rows[0].get("board_status") == "lock")
        except ServiceError:
            flow_locked = False
        if not detail.get("locked") and not flow_locked:
            st.info("当前工件未锁定，无需解锁")
            return

        st.warning("工件解锁将写入一条手动解锁流转记录，并更新工件当前状态。")
        try:
            steps = client.step_options()
        except ServiceError:
            steps = []
        step_options = [str(x.get("step_no")) for x in steps] if steps else []
        with st.form("pq_unlock_form", clear_on_submit=False):
            u1, u2 = st.columns([1, 2])
            operator = u1.text_input("操作人", value=common.operator(), key="pq_unlock_op")
            target_step = u2.selectbox("切换到的工序", step_options or ["原工序"], key="pq_unlock_step")
            note = st.text_input("备注（写入流转记录）", key="pq_unlock_note", placeholder="例如：手动解锁")
            confirmed = st.checkbox("我已确认该工件可以放行，本次操作将记录操作人和备注", key="pq_unlock_confirm")
            submitted = st.form_submit_button("执行解锁", type="primary")
        if submitted:
            if not confirmed:
                st.error("请勾选确认")
            elif not operator.strip():
                st.error("请填写操作人")
            else:
                reason_text = note.strip() or "unlock"
                try:
                    client.unlock_workpiece(
                        wp_id, operator.strip(), reason_text, True,
                        target_step=target_step if step_options else None,
                        note=reason_text,
                    )
                except ServiceError as exc:
                    st.error(f"工件解锁失败：{exc}")
                else:
                    st.toast("工件解锁成功；可重新判定放行")
                    st.rerun()


def render() -> None:
    """执行 render。"""
    st.title(PAGE_TITLE_PRODUCT_QUERY)
    st.caption("按产品型号/工件/状态/时间查询工件，点击结果行查看追溯明细，并对锁定工件执行工件解锁。")
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

            ids = [r["barcode"] for r in results]
            if current and current not in ids:
                st.session_state.pop("pq_current", None)
                current = None
            if current:
                st.divider()
                _render_detail(current)
            else:
                st.info("请点击查询结果中的一行查看追溯明细")
    if report_tab.open:
        with report_tab:
            _render_report_query()
