"""注册页通用辅助函数。

设备、载具、工序、组件四类主数据注册页遵循相同的交互流程：
1. 从 HTTP 接口加载主数据到 session_state；
2. 在 expander 表单中新增；
3. 在 data_editor 中直接修改；
4. 删除前通过 pending state 触发确认弹窗；
5. 保存时先做整表校验，再整表写回后端。

这里抽出与具体业务无关的公共逻辑，避免每个页面重复实现。
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from . import _common as master
from .constants import (
    EMPTY_TEXT_VALUES,
    ENABLED_NO,
    ENABLED_OPTIONS,
    ENABLED_YES,
    ROLE_EDIT,
    ROLE_VIEW,
)


def clean_text(value: Any) -> str:
    """把编辑器里的任意单元格值转成干净字符串；空值占位返回空串。"""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in EMPTY_TEXT_VALUES else text


def is_editable() -> bool:
    """当前角色是否可编辑；页面 role key 与主入口保持一致。"""
    return st.session_state.get("role", ROLE_EDIT) != ROLE_VIEW


def enabled_from_text(text: str) -> bool:
    """把新增表单的“是/否”下拉值转成布尔。"""
    return text == ENABLED_YES


def enabled_from_cell(value: Any) -> bool:
    """把 data_editor 的启用列转成布尔；空值按启用处理。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    return bool(value)


def make_frame(
    rows: list[dict[str, Any]],
    *,
    columns: list[str],
    field_map: dict[str, str],
    include_delete: bool = False,
) -> pd.DataFrame:
    """把后端字典列表转成 Streamlit 编辑器 DataFrame。

    field_map: 显示列名 -> 后端字段名。
    """
    records: list[dict[str, Any]] = []
    for row in rows:
        record = {
            column: row.get(field_map[column], "")
            for column in columns
            if column in field_map
        }
        if include_delete:
            record["删除"] = "删除"
        records.append(record)
    final_columns = list(columns) + (["删除"] if include_delete else [])
    return pd.DataFrame(records, columns=final_columns)


def request_delete(click_key: str, pending_key: str, rows_key: str, id_field: str) -> None:
    """ButtonColumn 点击后把待删除行主键写入 pending state。"""
    click = st.session_state.get(click_key)
    if click is None:
        return
    row_index = int(click["row"])
    rows = st.session_state.get(rows_key, [])
    if 0 <= row_index < len(rows):
        st.session_state[pending_key] = str(rows[row_index][id_field])


def clear_pending(pending_key: str) -> None:
    """清除待删除状态；供 dialog 取消/关闭时调用。"""
    st.session_state.pop(pending_key, None)


def save_rows(key: str, rows: list[dict[str, Any]], success_message: str) -> None:
    """保存整表数据到后端并提示成功。"""
    st.session_state[key] = rows
    master.save_key(key)
    st.toast(success_message)
    st.rerun()


def enabled_column(width: str = "small") -> Any:
    """统一的启用勾选列配置。"""
    return st.column_config.CheckboxColumn("启用", default=True, width=width)


def enabled_selectbox(key: str) -> Any:
    """统一的启用下拉选择框。"""
    return st.selectbox("启用", options=list(ENABLED_OPTIONS), key=key)


def delete_column(click_key: str, on_click: Callable[[], None]) -> Any:
    """统一的删除按钮列配置。"""
    return st.column_config.ButtonColumn(
        "删除", type="tertiary", on_click=on_click, key=click_key, width="small"
    )
