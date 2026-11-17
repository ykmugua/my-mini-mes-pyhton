"""页面：产品查询（产品追溯 + 工序解绑）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import client, common
from .client import ApiError as ServiceError

STATUS_OPTIONS = ["全部", "PENDING", "PASS", "FAIL"]


def _status_text(row: dict) -> str:
    parts = [row.get("status") or ""]
    if row.get("lock_reason"):
        parts.append("🔒")
    return " ".join(parts)


def _render_query() -> list[dict]:
    with st.container(border=True):
        st.subheader("查询条件")
        try:
            products = ["全部"] + client.product_options()
        except ServiceError:
            products = ["全部"]
        c1, c2, c3 = st.columns(3)
        product = c1.selectbox("产品型号", products, key="pq_product")
        workpiece = c2.text_input("工件码（模糊）", key="pq_workpiece", placeholder="输入工件码片段")
        status = c3.selectbox("工件状态", STATUS_OPTIONS, key="pq_status")
        c4, c5, c6 = st.columns(3)
        date_from = c4.text_input("起始时间（ISO/时间戳）", key="pq_from", placeholder="例如 2026-11-17T00:00:00+08:00")
        date_to = c5.text_input("结束时间（ISO/时间戳）", key="pq_to", placeholder="例如 2026-11-18T00:00:00+08:00")
        query = c6.button("🔍 查询", key="pq_query_btn")

    if "pq_results" not in st.session_state:
        st.session_state["pq_results"] = []
    if query:
        params = {"limit": 200}
        if product != "全部":
            params["product"] = product
        if workpiece.strip():
            params["workpiece"] = workpiece.strip()
        if status != "全部":
            params["status"] = status
        if date_from.strip():
            params["date_from"] = date_from.strip()
        if date_to.strip():
            params["date_to"] = date_to.strip()
        try:
            st.session_state["pq_results"] = client.query_workpieces(**params)
        except ServiceError as exc:
            st.error(f"查询失败：{exc}")
    return st.session_state["pq_results"]


def _render_results(results: list[dict]) -> None:
    with st.container(border=True):
        st.subheader("查询结果")
        if not results:
            st.info("暂无结果，请调整查询条件")
            return
        frame = pd.DataFrame([
            {
                "工件码": r["workpiece"],
                "产品型号": r.get("product") or "",
                "状态": _status_text(r),
                "当前设备": r.get("current_device") or "",
                "锁定原因": r.get("lock_reason") or "",
                "更新时间": common.local_time(r.get("updated_at")),
            }
            for r in results
        ])
        st.dataframe(frame, hide_index=True, width="stretch", height=260)
        ids = [r["workpiece"] for r in results]
        chosen = st.selectbox("选择工件查看追溯", ids, key="pq_selected")
        if st.button("查看追溯详情", type="primary", key="pq_detail_btn"):
            st.session_state["pq_current"] = chosen
            st.rerun()


def _render_detail(wp_id: str) -> None:
    editable = common.can_edit()
    try:
        detail = client.workpiece_detail(wp_id)
        history = client.workpiece_history(wp_id)
    except ServiceError as exc:
        st.error(f"读取追溯失败：{exc}")
        return

    st.subheader(f"追溯详情：{wp_id}")
    with st.container(border=True):
        st.markdown("#### 基本信息")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("状态", detail.get("status") or "-")
        c2.metric("产品型号", detail.get("product") or "-")
        c3.metric("当前设备", detail.get("current_device") or "-")
        c4.metric("锁定", "是" if detail.get("locked") else "否")
        if detail.get("lock_reason"):
            st.warning(f"锁定原因：{detail['lock_reason']}")

    # 工艺路线对比
    product = detail.get("product")
    if product:
        try:
            route_data = client.product_route(product)
            route = route_data.get("route", [])
            with st.container(border=True):
                st.markdown("#### 工艺路线")
                if route:
                    rf = pd.DataFrame([
                        {
                            "工序": r["step_no"],
                            "成功下站": str(r.get("success_next_step") or ""),
                            "失败下站": str(r.get("fail_next_step") or ""),
                        }
                        for r in route
                    ])
                    st.dataframe(rf, hide_index=True, width="stretch")
                else:
                    st.caption("该产品未配置工序流程")
        except ServiceError:
            pass

    tab_tests, tab_unlock = st.tabs(["测试履历", "解锁记录"])
    with tab_tests:
        with st.container(border=True):
            st.markdown("#### 测试履历")
            tests = history.get("tests", [])
            if tests:
                tf = pd.DataFrame([
                    {
                        "时间": common.local_time(t.get("tested_at")),
                        "设备": t.get("device_id") or "",
                        "测试项": t.get("test_item") or "",
                        "结果": t.get("result") or "",
                        "实测值": t.get("measured_value") or "",
                        "可信": "是" if t.get("trusted") else "否",
                        "不可信原因": t.get("untrusted_reason") or "",
                    }
                    for t in tests
                ])
                st.dataframe(tf, hide_index=True, width="stretch", height=300)
            else:
                st.info("暂无测试记录")
    with tab_unlock:
        with st.container(border=True):
            st.markdown("#### 解锁记录")
            unlocks = history.get("unlocks", [])
            if unlocks:
                uf = pd.DataFrame([
                    {
                        "时间": common.local_time(u.get("unlocked_at")),
                        "操作人": u.get("operator") or "",
                        "原因": u.get("reason") or "",
                        "设备": u.get("device_id") or "",
                        "原锁定原因": u.get("lock_reason") or "",
                    }
                    for u in unlocks
                ])
                st.dataframe(uf, hide_index=True, width="stretch", height=200)
            else:
                st.info("暂无解锁记录")

    # 工序解绑（人工解锁放行）
    with st.container(border=True):
        st.subheader("工序解绑（人工放行）")
        if not editable:
            st.info("只读角色不可执行解绑")
        elif not detail.get("locked"):
            st.info("当前工件未锁定，无需解绑")
        else:
            st.warning("解绑将清除工件锁、状态回 PENDING，并记录操作人与原因；原始测试记录不变。")
            with st.form("pq_unlock_form", clear_on_submit=False):
                u1, u2 = st.columns([1, 2])
                operator = u1.text_input("操作人", value=common.operator(), key="pq_unlock_op")
                reason = u2.text_input("解绑原因（必填）", key="pq_unlock_reason", placeholder="例如：返修完成，确认放行")
                confirmed = st.checkbox("我已确认该工件可以放行，本次操作将记录操作人、原因和时间", key="pq_unlock_confirm")
                submitted = st.form_submit_button("执行解绑", type="primary")
            if submitted:
                if not reason.strip():
                    st.error("请填写解绑原因")
                elif not confirmed:
                    st.error("请勾选确认")
                elif not operator.strip():
                    st.error("请填写操作人")
                else:
                    try:
                        client.unlock_workpiece(wp_id, operator.strip(), reason.strip(), True)
                    except ServiceError as exc:
                        st.error(f"解绑失败：{exc}")
                    else:
                        st.toast("解绑成功，工件已放行")
                        st.rerun()


def render() -> None:
    st.title("🔎 产品查询｜追溯与解绑")
    st.caption("按产品/工件/状态/时间查询工件，查看测试履历与工艺路线，并对锁定工件执行人工解绑放行。")
    common.render_flash()
    common.render_readonly_notice()

    results = _render_query()
    _render_results(results)

    if st.session_state.get("pq_current"):
        st.divider()
        _render_detail(st.session_state["pq_current"])
        if st.button("关闭详情", key="pq_close_detail"):
            st.session_state.pop("pq_current", None)
            st.rerun()