"""工位操作台当前已绑定载具列表。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import client
from ..constants import is_missing_traycode
from .pages.constants import BOUND_TRAY_SECTION, BOUND_TRAY_UNBIND_BUTTON

BOUND_TRAY_COLUMNS = ["载具号", "条码数量", "工件条码", "当前工序"]
UNBIND_CLICK_KEY = "tag_page_unbind_click"
UNBIND_TRAYS_KEY = "tag_page_unbind_trays"
PENDING_UNBIND_KEY = "tag_page_pending_unbind"


def _aggregate_trays(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """执行 aggregate_trays。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        traycode = str(row.get("traycode") or "")
        if traycode and not is_missing_traycode(traycode):
            grouped.setdefault(traycode, []).append(row)
    records = [
        {
            "载具号": traycode,
            "条码数量": len(items),
            "工件条码": "、".join(
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


def _render_unbind_actions(traycode: str, keys: dict[str, str], *, inline: bool) -> None:
    """渲染解绑确认动作：普通模式用 dialog，全屏模式用行内确认。"""
    if inline:
        st.write(f"确定解绑载具 **{traycode}** 绑定的全部工件吗？")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key=keys["cancel"]):
            st.session_state[keys["pending"]] = ""
            st.rerun()
        if st.button("确认解绑", type="primary", key=keys["confirm"]):
            try:
                result = client.unbind_tray(
                    traycode=traycode,
                    operator=st.session_state.get("mes_operator", ""),
                    confirmed=True,
                )
            except client.ApiError as exc:
                st.error(f"载具解绑失败：{exc}")
                return
            st.session_state[keys["pending"]] = ""
            st.toast(f"载具 {result['traycode']} 已解绑 {result['count']} 个工件")
            st.rerun()


def render_content(*, read_only: bool) -> None:
    """在工位操作台标签页中渲染当前已绑定载具列表。"""
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
            st.error(f"读取载具绑定失败：{exc}")
            return

        rows = [
            row
            for row in all_rows
            if str(row.get("traycode") or "").strip()
            and not is_missing_traycode(row.get("traycode"))
        ]
        trays = _aggregate_trays(rows)
        if not trays:
            st.info("暂无已绑定载具")
            return

        traycodes = [str(tray["载具号"]) for tray in trays]
        st.session_state[UNBIND_TRAYS_KEY] = traycodes
        display = [dict(tray) for tray in trays]
        column_config = {
            "载具号": st.column_config.TextColumn("载具号", width="small"),
            "条码数量": st.column_config.NumberColumn("条码数量", width="small"),
            "工件条码": st.column_config.TextColumn("工件条码", width="large"),
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
            alt="当前已绑定载具列表",
        )
        pending_traycode = str(st.session_state.get(PENDING_UNBIND_KEY) or "")
        if not pending_traycode or read_only:
            st.session_state[PENDING_UNBIND_KEY] = ""
            return
        _confirm_unbind(pending_traycode)


def _request_unbind() -> None:
    """记录列表里点击解绑的载具。"""
    click = st.session_state.get(UNBIND_CLICK_KEY)
    if click is None:
        return
    traycodes = st.session_state.get(UNBIND_TRAYS_KEY, [])
    row_index = int(click["row"])
    if 0 <= row_index < len(traycodes):
        st.session_state[PENDING_UNBIND_KEY] = str(traycodes[row_index])


def _clear_pending_unbind() -> None:
    """关闭确认弹窗时清空待解绑载具。"""
    st.session_state[PENDING_UNBIND_KEY] = ""


@st.dialog("确认载具解绑", icon=":material/link_off:", on_dismiss=_clear_pending_unbind)
def _confirm_unbind(traycode: str) -> None:
    """确认后解除载具与全部工件的绑定。"""
    st.write(f"确定解绑载具 **{traycode}** 绑定的全部工件吗？")
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
                st.error(f"载具解绑失败：{exc}")
                return
            _clear_pending_unbind()
            st.toast(f"载具 {result['traycode']} 已解绑 {result['count']} 个工件")
            st.rerun()
