"""页面：产品查询（产品追溯 + 工序解绑）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import config
from . import client, common
from .client import ApiError as ServiceError

STATUS_OPTIONS = ["全部", "PENDING", "PASS", "FAIL"]


def _status_text(row: dict) -> str:
    parts = [row.get("status") or ""]
    if row.get("lock_reason"):
        parts.append("🔒")
    return " ".join(parts)


def _result_frame(results: list[dict]) -> pd.DataFrame:
    """查询结果直接显示 ProductFlow.db 的 product_overview 字段。"""
    return pd.DataFrame([{
        "id": r.get("id") or "",
        "barcode": r.get("barcode") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": r.get("traycode") or "",
        "board_status": r.get("board_status") or "",
        "current_step": r.get("current_step") or "",
        "last_report_device": r.get("last_report_device") or "",
        "last_report_note": r.get("last_report_note") or "",
        "updated_at": r.get("updated_at") or "",
    } for r in results])


def _render_query() -> list[dict]:
    with st.container(border=True):
        st.subheader("查询条件")
        # 选项来自产品流转总览表
        try:
            all_wps = client.product_flow_overview()
        except ServiceError:
            all_wps = []
        def opts(values):
            return ["全部"] + sorted({str(v) for v in values if v not in (None, "")})
        products = opts([r.get("componentcode") for r in all_wps])
        traycodes = opts([r.get("traycode") for r in all_wps])
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
        query = st.button("🔍 查询", key="pq_query_btn")

    # 结果常驻 session_state：首次进入自动加载全部；之后只在点“查询”时更新
    if "pq_results" not in st.session_state:
        st.session_state["pq_results"] = client.product_flow_overview()

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
            new_results = client.product_flow_overview(
                barcode=None if workpiece == "全部" else workpiece,
                componentcode=None if product == "全部" else product,
                traycode=None if traycode == "全部" else traycode,
                device=None if device == "全部" else device,
                board_status=None if board_status == "全部" else board_status,
                current_step=None if test_step == "全部" else test_step,
            )
            st.session_state["pq_results"] = new_results
            # 已选工件若仍在新结果中则保留；否则清掉，避免详情指向旧数据
            current = st.session_state.get("pq_current")
            ids = [r["barcode"] for r in new_results]
            if current and current not in ids:
                st.session_state.pop("pq_current", None)
        except ServiceError as exc:
            st.error(f"查询失败：{exc}")
    return st.session_state["pq_results"]


def _render_results(results: list[dict]) -> None:
    with st.container(border=True):
        st.subheader("查询结果")
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
        "linecode": r.get("linecode") or "",
        "station": r.get("station") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": r.get("traycode") or "",
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
    st.markdown("**测试明细 details**")
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
    st.markdown("**产品流转总览**")
    try:
        overview = client.product_flow_overview(barcode)
    except ServiceError as exc:
        st.error(f"读取产品流转总览失败：{exc}")
        return
    if not overview:
        st.info("暂无产品流转数据")
        return
    # 表头使用 product_overview 数据库字段名
    frame = pd.DataFrame([{
        "id": r["id"],
        "barcode": r.get("barcode") or "",
        "componentcode": r.get("componentcode") or "",
        "traycode": r.get("traycode") or "",
        "board_status": r.get("board_status") or "",
        "current_step": r.get("current_step") or "",
        "last_report_device": r.get("last_report_device") or "",
        "last_report_note": r.get("last_report_note") or "",
        "updated_at": r.get("updated_at") or "",
    } for r in overview])
    # 总览只展示当前条码对应的一行
    st.dataframe(frame.head(1), hide_index=True, width="stretch", alt="产品流转总览")
    selected = overview[0]
    st.caption(f"具体流转记录：{selected['barcode']}")
    try:
        details = client.product_flow_details(selected["flow_table"])
    except ServiceError as exc:
        st.error(f"读取具体流转失败：{exc}")
        return
    if not details:
        st.info("该产品暂无流转记录")
        return
    st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch", alt="产品具体流转记录")


def _render_detail(wp_id: str) -> None:
    editable = common.can_edit()
    try:
        detail = client.workpiece_detail(wp_id)
    except ServiceError as exc:
        st.error(f"读取追溯失败：{exc}")
        return

    with st.container(border=True):
        st.subheader(f"追溯详情：{wp_id}")

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
                    st.caption("该产品未配置工序流程")
            except ServiceError:
                pass

        # 产品流转（顺序排列，不用 tab）
        st.markdown("**产品流转**")
        _render_product_flow(wp_id)

        # 工序解绑（顺序排列，不用 tab）
        st.markdown("**工序解绑**")
        if not editable:
            st.info("只读角色不可执行解绑")
            return

        flow_locked = False
        try:
            flow_rows = client.product_flow_overview(wp_id)
            flow_locked = bool(flow_rows and flow_rows[0].get("board_status") == "lock")
        except ServiceError:
            flow_locked = False
        if not detail.get("locked") and not flow_locked:
            st.info("当前工件未锁定，无需解绑")
            return

        st.warning("解绑将写入一条手动解锁流转记录，并更新产品当前状态。")
        try:
            steps = client.step_options()
        except ServiceError:
            steps = []
        step_options = [str(x.get("step_no")) for x in steps] if steps else []
        with st.form("pq_unlock_form", clear_on_submit=False):
            u1, u2 = st.columns([1, 2])
            operator = u1.text_input("操作人", value=common.operator(), key="pq_unlock_op")
            target_step = u2.selectbox("切换到的工序", step_options or ["原工序"], key="pq_unlock_step")
            note = st.text_input("备注（写入流转记录）", key="pq_unlock_note", placeholder="例如：手动解锁放行")
            confirmed = st.checkbox("我已确认该工件可以放行，本次操作将记录操作人和备注", key="pq_unlock_confirm")
            submitted = st.form_submit_button("执行解绑", type="primary")
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
                    st.error(f"解绑失败：{exc}")
                else:
                    st.toast("解绑成功，工件已放行")
                    st.rerun()


def render() -> None:
    st.title("🔎 产品查询｜追溯与解绑")
    st.caption("按产品/工件/状态/时间查询工件，点击结果行查看追溯详情，并对锁定工件执行人工解绑放行。")
    common.render_flash()
    common.render_readonly_notice()

    results = _render_query()
    _render_results(results)

    current = st.session_state.get("pq_current")
    if current:
        with st.container(border=True):
            st.subheader("测试履历")
            try:
                steps = client.step_options()
            except ServiceError:
                steps = []
            step_names = [(str(x.get("step_no")), str(x.get("step_name"))) for x in steps]
            if step_names:
                hist_tabs = st.tabs([f"{no}-{name}" for no, name in step_names])
                try:
                    hist = client.workpiece_history(current)
                    tests = hist.get("tests", [])
                except ServiceError:
                    tests = []
                for idx, (no, _name) in enumerate(step_names):
                    with hist_tabs[idx]:
                        _render_test_history(tests, current, no)
            else:
                _render_test_history([], current)


    ids = [r["barcode"] for r in results]
    if current and current not in ids:
        st.session_state.pop("pq_current", None)
        current = None
    if current:
        st.divider()
        _render_detail(current)
    else:
        st.info("请点击查询结果中的一行查看追溯详情")
