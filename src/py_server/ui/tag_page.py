"""工位操作台当前已绑定托盘列表。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import client
from .pages.constants import BOUND_TRAY_SECTION

BOUND_TRAY_COLUMNS = ["载具号", "条码数量", "产品条码", "当前工序"]


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
            all_rows = client.product_flow_overview()
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

        st.dataframe(
            pd.DataFrame(trays, columns=BOUND_TRAY_COLUMNS),
            hide_index=True,
            width="stretch",
            alt="当前已绑定托盘列表",
        )
