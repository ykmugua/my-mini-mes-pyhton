"""载具注册页面：维护载具（托盘）主数据，风格与设备注册一致。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from . import registry_helpers as helpers
from .constants import (
    BLANK_TEMPLATE,
    CREATE_TRAY_BUTTON,
    CREATE_TRAY_SECTION,
    ENABLED_OPTIONS,
    SAVE_TRAY_BUTTON,
    TRAY_LIST_SECTION,
)

TRAY_COLUMNS = ["载具码", "载具名称", "载具型号", "载荷数量", "启用", "备注"]
DELETE_CLICK_KEY = "tray_delete_click"
PENDING_DELETE_KEY = "pending_tray_delete"


def _text(value: Any) -> str:
    """统一空值清洗。"""
    return helpers.clean_text(value)


def _integer(value: Any) -> int | None:
    """执行 integer。"""
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
        return int(number) if number > 0 else None
    except (TypeError, ValueError):
        return None


def _tray_frame(trays: list[dict[str, Any]], *, include_delete: bool) -> pd.DataFrame:
    """执行 tray_frame。"""
    records = [
        {
            "载具码": tray.get("traycode", ""),
            "载具名称": tray.get("tray_name", ""),
            "载具型号": tray.get("tray_model", ""),
            "载荷数量": int(tray.get("capacity") or 0),
            "启用": bool(tray.get("enabled")),
            "备注": tray.get("remark", ""),
        }
        for tray in trays
    ]
    columns = list(TRAY_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _tray_config(*, include_delete: bool) -> dict[str, Any]:
    """执行 tray_config。"""
    config: dict[str, Any] = {
        "载具码": st.column_config.TextColumn("载具码", required=True, width="medium"),
        "载具名称": st.column_config.TextColumn("载具名称", required=True, width="medium"),
        "载具型号": st.column_config.TextColumn("载具型号", required=True, width="medium"),
        "载荷数量": st.column_config.NumberColumn(
            "载荷数量", min_value=1, step=1, required=True, width="small",
            help="一个托盘可放置的板子数量",
        ),
        "启用": helpers.enabled_column(),
        "备注": st.column_config.TextColumn("备注", width="large"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除", type="tertiary", on_click=_request_tray_delete,
            key=DELETE_CLICK_KEY, width="small",
        )
    return config


def _validate_trays(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """执行 validate_trays。"""
    trays: list[dict[str, Any]] = []
    codes: set[str] = set()
    for row in rows:
        code = _text(row.get("载具码"))
        name = _text(row.get("载具名称"))
        model = _text(row.get("载具型号"))
        remark = _text(row.get("备注"))
        raw_capacity = row.get("载荷数量")
        if not any((code, name, model, _text(raw_capacity), remark)):
            continue
        if not code or not name or not model:
            return None, "载具码、载具名称和载具型号不能为空"
        capacity = _integer(raw_capacity)
        if capacity is None:
            return None, "载荷数量必须是大于 0 的整数"
        if code.casefold() in codes:
            return None, "载具码不能重复"
        codes.add(code.casefold())
        raw_enabled = row.get("启用")
        trays.append({
            "traycode": code,
            "tray_name": name,
            "tray_model": model,
            "capacity": capacity,
            "enabled": (
                helpers.enabled_from_cell(raw_enabled)
            ),
            "remark": remark,
        })
    return trays, None


def _request_tray_delete() -> None:
    """记录待删除载具码。"""
    helpers.request_delete(DELETE_CLICK_KEY, PENDING_DELETE_KEY, "trays", "traycode")


def _clear_pending_delete() -> None:
    """执行 clear_pending_delete。"""
    helpers.clear_pending(PENDING_DELETE_KEY)


@st.dialog("确认删除载具", icon=":material/delete_forever:", on_dismiss=_clear_pending_delete)
def _confirm_delete_tray(tray: dict[str, Any]) -> None:
    """执行 confirm_delete_tray。"""
    st.write(f"确定删除载具 **{tray['traycode']} - {tray.get('tray_name','')}（{tray.get('tray_model','')}）** 吗？")
    st.caption("删除后，历史数据中的载具号引用将保留，但不再显示为已注册载具。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_tray"):
            _clear_pending_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_tray"):
            st.session_state.trays = [
                item for item in st.session_state.trays
                if item["traycode"] != tray["traycode"]
            ]
            _clear_pending_delete()
            st.toast("载具已删除")
            st.rerun()


def render_page() -> None:
    """页面渲染入口。"""
    master.ensure_master_data()
    read_only = not helpers.is_editable()
    trays: list[dict[str, Any]] = st.session_state.get("trays", [])

    # 区块 1：新增载具（折叠表单）
    with st.container(border=True):
        if read_only:
            with st.expander(CREATE_TRAY_SECTION, expanded=False):
                st.info("只读角色不可新增载具。")
        else:
            with st.expander(CREATE_TRAY_SECTION, expanded=False):
                with st.form("tray_create_form", clear_on_submit=False, border=False):
                    # 第一行：载具码 + 载具名称 + 载具型号 + 载荷数量
                    code_col, name_col, template_col, model_col, cap_col = st.columns([1, 1, 1, 1, 1])
                    new_code = code_col.text_input(
                        "载具码", key="new_tray_code", placeholder="例如 T02001",
                    )
                    new_name = name_col.text_input(
                        "载具名称", key="new_tray_name", placeholder="例如 01号载具",
                    )
                    source = template_col.selectbox(
                        "从原有模板中新建",
                        options=[BLANK_TEMPLATE, *[str(t["traycode"]) for t in trays]],
                        key="new_tray_template",
                    )
                    new_model = model_col.text_input(
                        "载具型号", key="new_tray_model", placeholder="例如 TM-A",
                    )
                    new_capacity = cap_col.number_input(
                        "载荷数量", min_value=1, step=1, value=1,
                        key="new_tray_capacity",
                        help="一个载具可放置的工件数量",
                    )
                    # 第二行：备注 + 启用
                    remark_col, enabled_col = st.columns([3, 1])
                    new_remark = remark_col.text_input(
                        "备注", key="new_tray_remark",
                        placeholder="可选，用于填写现场说明",
                    )
                    new_enabled_text = enabled_col.selectbox(
                        "启用", options=list(ENABLED_OPTIONS), key="new_tray_enabled_text",
                    )
                    # 第三行：添加按钮（左侧单独一行）
                    submitted = st.form_submit_button(CREATE_TRAY_BUTTON)

                if submitted:
                    template_values = None
                    if source != BLANK_TEMPLATE:
                        row = next(t for t in trays if str(t["traycode"]) == source)
                        template_values = _tray_frame([row], include_delete=False).to_dict("records")[0]
                    filled = helpers.fill_missing_text_values({
                            "载具码": new_code.strip(),
                            "载具名称": new_name.strip(),
                            "载具型号": new_model.strip(),
                            "载荷数量": int(new_capacity),
                            "启用": helpers.enabled_from_text(new_enabled_text),
                            "备注": new_remark.strip(),
                    }, template_values)
                    proposed_rows = _tray_frame(trays, include_delete=False).to_dict("records") + [filled]
                    success_message = f"已从模板 {source} 新建载具" if template_values else "载具已添加"
                    validated, error = _validate_trays(proposed_rows)
                    if error:
                        st.error(error)
                    else:
                        helpers.save_rows("trays", validated, success_message)

    # 区块 2：载具列表
    with st.container(border=True):
        st.subheader(TRAY_LIST_SECTION)
        edited: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _tray_frame(trays, include_delete=False),
                column_config=_tray_config(include_delete=False),
                hide_index=True, width="stretch", alt="载具列表",
            )
        else:
            edited = st.data_editor(
                _tray_frame(trays, include_delete=True),
                column_config=_tray_config(include_delete=True),
                hide_index=True, num_rows="fixed", width="stretch",
                alt="载具注册编辑器", key="tray_editor",
            )

        save_clicked = False
        if not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                save_clicked = st.button(
                    SAVE_TRAY_BUTTON, icon=":material/save:", key="save_trays",
                )

        if not trays:
            st.info("暂无载具，请新增")

        if save_clicked and edited is not None:
            updated, error = _validate_trays(edited.to_dict("records"))
            if error:
                st.error(error)
            else:
                st.session_state.trays = updated
                master.save_key("trays")
                st.toast("载具已保存")
                st.rerun()

        pending = st.session_state.get(PENDING_DELETE_KEY)
        if pending:
            tray = next((t for t in trays if t["traycode"] == pending), None)
            if tray is None:
                _clear_pending_delete()
            else:
                _confirm_delete_tray(tray)
