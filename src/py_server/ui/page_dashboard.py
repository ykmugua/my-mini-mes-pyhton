"""页面：测试数据看板。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import config, services
from . import common

ALL_DEVICES = "全部设备"


def _metrics(snapshot: dict) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("今日测试总数", snapshot["total"])
    col2.metric("PASS", snapshot["pass"])
    col3.metric("FAIL", snapshot["fail"])
    yield_text = "—" if snapshot["yield"] is None else f"{snapshot['yield'] * 100:.1f}%"
    col4.metric("合格率（可信数据）", yield_text)
    st.caption("测试总数 / PASS / FAIL 包含全部上报；合格率只统计可信数据。")
    if snapshot["untrusted"]:
        st.warning(
            f"有 {snapshot['untrusted']} 条今日测试数据因程序版本/校验和不匹配被标记为"
            "“不可信”，已排除出合格率统计。"
        )
    else:
        st.caption("今日所有测试数据均通过程序版本/校验和验证。")


def _yield_chart(snapshot: dict) -> None:
    st.subheader("按设备合格率")
    rows = snapshot["by_device"]
    if not rows:
        st.info("今日暂无数据。")
        return
    frame = pd.DataFrame(
        [
            {
                "设备": item["device_id"],
                "合格率(%)": round((item["yield"] or 0) * 100, 1),
                "测试数": item["total"],
            }
            for item in rows
        ]
    ).set_index("设备")
    st.bar_chart(frame["合格率(%)"], height=320, width="stretch")
    st.caption("仅统计可信数据；合格率 = PASS / (PASS + FAIL)。")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "设备": item["device_id"],
                    "测试数": item["total"],
                    "PASS": item["pass"],
                    "FAIL": item["fail"],
                    "合格率": "—" if item["yield"] is None else f"{item['yield'] * 100:.1f}%",
                }
                for item in rows
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _fail_charts(snapshot: dict) -> None:
    st.subheader("FAIL 分布")
    st.caption("包含不可信数据，便于现场排查；合格率仍只统计可信数据。")
    tab_item, tab_device = st.tabs(["按测试项", "按设备"])
    for tab, key, label in (
        (tab_item, "fail_by_item", "测试项"),
        (tab_device, "fail_by_device", "设备"),
    ):
        with tab:
            rows = snapshot[key]
            if not rows:
                st.info("今日没有 FAIL 记录。")
                continue
            frame = pd.DataFrame(
                [{"标签": item["label"], "FAIL 数": item["count"]} for item in rows]
            ).set_index("标签")
            st.bar_chart(frame["FAIL 数"], height=300, width="stretch", horizontal=True)


def _latest_table(snapshot: dict) -> None:
    st.subheader("最新测试（今日）")
    latest = snapshot["latest"]
    if not latest:
        st.info("今日暂无测试数据。")
        return
    frame = pd.DataFrame(
        [
            {
                "上报时间": common.local_time(item["reported_at"]),
                "工件码": item["workpiece"],
                "设备": item["device_id"],
                "测试项": item["test_item"],
                "实测值": item.get("measured_value") or "",
                "判定": item["result"],
                "数据可信": "是" if item["trusted"] else "否（排除统计）",
                "程序版本": item.get("program_version") or "",
                "测试时间": common.local_time(item.get("tested_at")),
            }
            for item in latest
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch")


def _render_live(device_filter: str | None) -> None:
    snapshot = services.dashboard_snapshot(device_filter)
    st.caption(
        f"统计范围：{snapshot['date']}（{config.timezone().key}）· 按测试时间统计"
        + (f" · 设备 {device_filter}" if device_filter else "")
    )
    _metrics(snapshot)
    left, right = st.columns(2)
    with left:
        _yield_chart(snapshot)
    with right:
        _fail_charts(snapshot)
    _latest_table(snapshot)
    st.caption(f"每 10 秒自动刷新 · 数据截至 {common.now_text()}")


def render() -> None:
    st.title("📊 测试数据看板")
    st.caption("今日实时结果、合格率、FAIL 分布；不可信数据自动排除出合格率统计。")
    common.render_flash()
    common.render_readonly_notice()

    devices = services.list_devices()
    options = [ALL_DEVICES] + devices
    if st.session_state.get("dash_device") not in options:
        st.session_state["dash_device"] = ALL_DEVICES
    device_choice = st.sidebar.selectbox("设备筛选", options, key="dash_device")
    device_filter = None if device_choice == ALL_DEVICES else device_choice

    @st.fragment(run_every=10)
    def live() -> None:
        _render_live(device_filter)

    live()
