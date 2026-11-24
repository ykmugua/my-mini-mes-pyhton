"""工位操作台入线状态：查看产品入线总览，并允许删除单条入线状态。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import client, common

TAG_COLUMNS = [
    "载具号",
    "条码数量",
    "产品条码",
    "产品型号",
    "状态",
    "当前工序",
    "最近设备",
    "最近说明",
    "更新时间",
]
DELETE_CLICK_KEY = "tag_page_delete_click"
PENDING_DELETE_KEY = "pending_tag_page_delete"
DISPLAY_TRAYS_KEY = "tag_page_display_trays"
STATUS_LABELS = {
    "normal": "NORMAL",
    "lock": "LOCK",
    "final": "END",
    "end": "END",
}


def _joined(values: list[Any]) -> str:
    """执行 joined。"""
    unique = [
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    ]
    return "、".join(dict.fromkeys(unique))


def _status_label(value: Any) -> str:
    """执行 status_label。"""
    status = str(value or "")
    return STATUS_LABELS.get(status, status)


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
            "产品条码": _joined([item.get("barcode") for item in items]),
            "产品型号": _joined([item.get("componentcode") for item in items]),
            "状态": _joined([
                _status_label(item.get("board_status")) for item in items
            ]),
            "当前工序": _joined([item.get("current_step") for item in items]),
            "最近设备": _joined([
                item.get("last_report_device") for item in items
            ]),
            "最近说明": _joined([
                item.get("last_report_note") for item in items
            ]),
            "更新时间": max(
                (str(item.get("updated_at") or "") for item in items),
                default="",
            ),
        }
        for traycode, items in grouped.items()
    ]
    records.sort(key=lambda record: record["更新时间"], reverse=True)
    return records


def _status_frame(
    trays: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
    """执行 status_frame。"""
    records = [
        {
            column: row.get(column, "")
            for column in TAG_COLUMNS
        }
        for row in trays
    ]
    columns = list(TAG_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _column_config(*, include_delete: bool) -> dict[str, Any]:
    """执行 column_config。"""
    config: dict[str, Any] = {
        "载具号": st.column_config.TextColumn("载具号", width="small"),
        "条码数量": st.column_config.NumberColumn("条码数量", width="small"),
        "产品条码": st.column_config.TextColumn("产品条码", width="large"),
        "产品型号": st.column_config.TextColumn("产品型号", width="small"),
        "状态": st.column_config.TextColumn("状态", width="small"),
        "当前工序": st.column_config.TextColumn("当前工序", width="small"),
        "最近设备": st.column_config.TextColumn("最近设备", width="medium"),
        "最近说明": st.column_config.TextColumn("最近说明", width="large"),
        "更新时间": st.column_config.TextColumn("更新时间", width="medium"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除",
            type="tertiary",
            on_click=_request_delete,
            key=DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _request_delete() -> None:
    """执行 request_delete。"""
    click = st.session_state.get(DELETE_CLICK_KEY)
    if click is None:
        return
    row_index = int(click["row"])
    traycodes = st.session_state.get(DISPLAY_TRAYS_KEY, [])
    if 0 <= row_index < len(traycodes) and traycodes[row_index]:
        st.session_state[PENDING_DELETE_KEY] = str(traycodes[row_index])


def _clear_pending_delete() -> None:
    """执行 clear_pending_delete。"""
    st.session_state.pop(PENDING_DELETE_KEY, None)


@st.dialog(
    "确认删除入线状态",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_delete,
)
def _confirm_delete(tray: dict[str, Any]) -> None:
    """执行 confirm_delete。"""
    traycode = str(tray.get("载具号") or "")
    barcodes = str(tray.get("产品条码") or "")
    st.write(f"确定删除托盘 **{traycode}** 的当前入线状态吗？")
    st.caption(f"共 {tray.get('条码数量') or 0} 个产品")
    if barcodes:
        st.caption(f"条码：{barcodes}")
    st.warning("将删除整盘产品的入线总览和流转历史，测试报告等其他业务数据不会删除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_tag_page_delete"):
            _clear_pending_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_tag_page_delete",
        ):
            try:
                result = client.delete_tray_flow(traycode)
            except client.ApiError as exc:
                st.error(f"删除失败：{exc}")
                return
            _clear_pending_delete()
            common.flash(
                "success",
                f"已删除托盘 {traycode} 的 {result['count']} 条入线状态",
            )
            st.rerun()


def render_content(*, read_only: bool) -> None:
    """在工位操作台标签页中渲染入线状态列表。"""
    with st.container(border=True):
        with st.container(
            horizontal=True,
            vertical_alignment="center",
            horizontal_alignment="distribute",
        ):
            st.subheader("正在流转的托盘")
            if st.button(
                "刷新",
                icon=":material/refresh:",
                key="tag_page_refresh",
            ):
                st.rerun()

        try:
            all_rows = client.product_flow_overview()
        except client.ApiError as exc:
            st.error(f"读取入线状态失败：{exc}")
            return

        rows = [
            row
            for row in all_rows
            if str(row.get("traycode") or "")
        ]
        trays = _aggregate_trays(rows)
        if not trays:
            st.session_state[DISPLAY_TRAYS_KEY] = []
            st.info("暂无正在流转的托盘")
            return

        st.session_state[DISPLAY_TRAYS_KEY] = [
            str(tray["载具号"]) for tray in trays
        ]
        include_delete = not read_only
        st.dataframe(
            _status_frame(trays, include_delete=include_delete),
            column_config=_column_config(include_delete=include_delete),
            hide_index=True,
            width="stretch",
            alt="正在流转的托盘状态列表",
        )

        pending_traycode = st.session_state.get(PENDING_DELETE_KEY)
        if pending_traycode is None:
            return
        if not include_delete:
            _clear_pending_delete()
            return
        pending_tray = next(
            (
                tray
                for tray in trays
                if str(tray.get("载具号") or "") == str(pending_traycode)
            ),
            None,
        )
        if pending_tray is None:
            _clear_pending_delete()
        else:
            _confirm_delete(pending_tray)
