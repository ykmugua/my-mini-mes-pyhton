"""工位操作台当前已绑定托盘列表。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import client
from .pages.constants import BOUND_TRAY_SECTION, BOUND_TRAY_UNBIND_BUTTON

BOUND_TRAY_COLUMNS = ["载具号", "条码数量", "产品条码", "当前工序"]
UNBIND_CLICK_KEY = "tag_page_unbind_click"
UNBIND_TRAYS_KEY = "tag_page_unbind_trays"
PENDING_UNBIND_KEY = "tag_page_pending_unbind"


def _aggregate_trays(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """执行 aggregate_trays。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        traycode = str(row.get("traycode") or "")
        if traycode:
            grouped.setdefault(traycode, []).append(row)
    records = [
        {
            "载具号": traycode,
            "条码数量": len(items),
            "产品条码": "、".join(
                str(item.get("barcode") or "")
                for item in items
                if item.get("barcode")
            ),
            "当前工序": "、".join(dict.fromkeys(
                str(item.get("current_step") or "")
                for item in items
                if item.get("current_step")
            )),
        }
        for traycode, items in grouped.items()
    ]
    return records


def render_content(*, read_only: bool) -> None:
    """在工位操作台标签页中渲染当前已绑定托盘列表。"""
    with st.container(border=True):
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            horizontal_alignment="distribute",
        ):
            st.subheader(BOUND_TRAY_SECTION)
            if st.button(
                "刷新",
                icon=":material/refresh:",
                key="tag_page_refresh",
            ):
                st.rerun()

        try:
            all_rows = client.active_products()
        except client.ApiError as exc:
            st.error(f"读取托盘绑定失败：{exc}")
            return

        rows = [
            row
            for row in all_rows
            if str(row.get("traycode") or "")
        ]
        trays = _aggregate_trays(rows)
        if not trays:
            st.info("暂无已绑定托盘")
            return

        traycodes = [str(tray["载具号"]) for tray in trays]
        st.session_state[UNBIND_TRAYS_KEY] = traycodes
        display = [dict(tray) for tray in trays]
        column_config = {
            "载具号": st.column_config.TextColumn("载具号", width="small"),
            "条码数量": st.column_config.NumberColumn("条码数量", width="small"),
            "产品条码": st.column_config.TextColumn("产品条码", width="large"),
            "当前工序": st.column_config.TextColumn("当前工序", width="medium"),
        }
        if not read_only:
            for record in display:
                record["操作"] = BOUND_TRAY_UNBIND_BUTTON
            column_config["操作"] = st.column_config.ButtonColumn(
                "操作",
                type="tertiary",
                on_click=_request_unbind,
                key=UNBIND_CLICK_KEY,
                width="small",
            )
        st.dataframe(
            pd.DataFrame(display),
            column_config=column_config,
            hide_index=True,
            width="stretch",
            alt="当前已绑定托盘列表",
        )
        pending_traycode = str(st.session_state.get(PENDING_UNBIND_KEY) or "")
        if not pending_traycode or read_only:
            st.session_state[PENDING_UNBIND_KEY] = ""
            return
        _confirm_unbind(pending_traycode)


def _request_unbind() -> None:
    """记录列表里点击解绑的托盘。"""
    click = st.session_state.get(UNBIND_CLICK_KEY)
    if click is None:
        return
    traycodes = st.session_state.get(UNBIND_TRAYS_KEY, [])
    row_index = int(click["row"])
    if 0 <= row_index < len(traycodes):
        st.session_state[PENDING_UNBIND_KEY] = str(traycodes[row_index])


def _clear_pending_unbind() -> None:
    """关闭确认弹窗时清空待解绑托盘。"""
    st.session_state[PENDING_UNBIND_KEY] = ""


@st.dialog("确认解绑托盘", icon=":material/link_off:", on_dismiss=_clear_pending_unbind)
def _confirm_unbind(traycode: str) -> None:
    """确认后解除托盘与全部产品的绑定。"""
    st.write(f"确定解绑托盘 **{traycode}** 绑定的全部产品吗？")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="tag_page_unbind_cancel"):
            _clear_pending_unbind()
            st.rerun()
        if st.button("确认解绑", type="primary", key="tag_page_unbind_confirm"):
            try:
                result = client.unbind_tray(
                    traycode=traycode,
                    operator=st.session_state.get("mes_operator", ""),
                    confirmed=True,
                )
            except client.ApiError as exc:
                st.error(f"托盘解绑失败：{exc}")
                return
            _clear_pending_unbind()
            st.toast(f"载具 {result['traycode']} 已解绑 {result['count']} 个产品")
            st.rerun()
