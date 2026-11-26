"""针床注册页面：维护针床主数据，风格与载具注册一致。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from . import registry_helpers as helpers
from .constants import (
    BLANK_TEMPLATE,
    CREATE_NEEDLE_BED_BUTTON,
    CREATE_NEEDLE_BED_SECTION,
    ENABLED_OPTIONS,
    NEEDLE_BED_LIST_SECTION,
    SAVE_NEEDLE_BED_BUTTON,
)

COLUMNS = ["针床码", "针床名称", "针床编号", "针床型号", "启用", "备注"]
DELETE_CLICK_KEY = "needle_bed_delete_click"
PENDING_DELETE_KEY = "pending_needle_bed_delete"


def _text(value: Any) -> str:
    """统一空值清洗。"""
    return helpers.clean_text(value)


def _frame(rows: list[dict[str, Any]], *, include_delete: bool) -> pd.DataFrame:
    """生成针床列表 DataFrame。"""
    records = [
        {
            "针床码": row.get("needle_bed_code", ""),
            "针床名称": row.get("needle_bed_name", ""),
            "针床编号": row.get("needle_bed_number", ""),
            "针床型号": row.get("needle_bed_model", ""),
            "启用": bool(row.get("enabled", True)),
            "备注": row.get("remark", ""),
        }
        for row in rows
    ]
    columns = list(COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _config(*, include_delete: bool) -> dict[str, Any]:
    """生成针床列表列配置。"""
    config: dict[str, Any] = {
        "针床码": st.column_config.TextColumn("针床码", required=True, width="medium"),
        "针床名称": st.column_config.TextColumn("针床名称", required=True, width="medium"),
        "针床编号": st.column_config.TextColumn("针床编号", width="medium"),
        "针床型号": st.column_config.TextColumn("针床型号", width="medium"),
        "启用": helpers.enabled_column(),
        "备注": st.column_config.TextColumn("备注", width="large"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除", type="tertiary", on_click=_request_delete,
            key=DELETE_CLICK_KEY, width="small",
        )
    return config


def _validate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """校验并清洗针床数据。"""
    validated: list[dict[str, Any]] = []
    codes: set[str] = set()
    for row in rows:
        code = _text(row.get("针床码"))
        name = _text(row.get("针床名称"))
        number = _text(row.get("针床编号"))
        model = _text(row.get("针床型号"))
        remark = _text(row.get("备注"))
        if not any((code, name, number, model, remark)):
            continue
        if not code or not name:
            return None, "针床码和针床名称不能为空"
        if code.casefold() in codes:
            return None, "针床码不能重复"
        codes.add(code.casefold())
        validated.append({
            "needle_bed_code": code,
            "needle_bed_name": name,
            "needle_bed_number": number,
            "needle_bed_model": model,
            "enabled": helpers.enabled_from_cell(row.get("启用")),
            "remark": remark,
        })
    return validated, None


def _request_delete() -> None:
    """记录待删除针床码。"""
    helpers.request_delete(DELETE_CLICK_KEY, PENDING_DELETE_KEY, "needle_beds", "needle_bed_code")


def _clear_pending_delete() -> None:
    """清空待删除针床码。"""
    helpers.clear_pending(PENDING_DELETE_KEY)


@st.dialog("确认删除针床", icon=":material/delete_forever:", on_dismiss=_clear_pending_delete)
def _confirm_delete(row: dict[str, Any]) -> None:
    """确认删除针床。"""
    st.write(f"确定删除针床 **{row['needle_bed_code']} - {row.get('needle_bed_name', '')}** 吗？")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_needle_bed"):
            _clear_pending_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_needle_bed"):
            st.session_state.needle_beds = [
                item for item in st.session_state.needle_beds
                if item["needle_bed_code"] != row["needle_bed_code"]
            ]
            _clear_pending_delete()
            helpers.save_rows("needle_beds", st.session_state.needle_beds, "针床已删除")


def render_page() -> None:
    """页面渲染入口。"""
    master.ensure_master_data()
    read_only = not helpers.is_editable()
    rows: list[dict[str, Any]] = st.session_state.get("needle_beds", [])
    with st.container(border=True):
        if read_only:
            with st.expander(CREATE_NEEDLE_BED_SECTION, expanded=False):
                st.info("只读角色不可新增针床。")
        else:
            with st.expander(CREATE_NEEDLE_BED_SECTION, expanded=False):
                with st.form("needle_bed_create_form", clear_on_submit=False, border=False):
                    # 第一行：针床码 + 针床名称 + 从原有模板中新建 + 针床型号 + 针床编号
                    code_col, name_col, number_col, template_col, model_col = st.columns([1, 1, 1, 1, 1])
                    code = code_col.text_input("针床码", key="new_needle_bed_code", placeholder="例如 NB-001")
                    name = name_col.text_input("针床名称", key="new_needle_bed_name", placeholder="例如 01号针床")
                    source = template_col.selectbox(
                        "从原有模板中新建",
                        options=[BLANK_TEMPLATE, *[str(r["needle_bed_code"]) for r in rows]],
                        key="new_needle_bed_template",
                    )
                    model = model_col.text_input("针床型号", key="new_needle_bed_model", placeholder="例如 NB-MODEL-A")
                    number = number_col.text_input("针床编号", key="new_needle_bed_number", placeholder="例如 NB-NO-001")
                    # 第二行：备注 + 启用
                    remark_col, enabled_col = st.columns([3, 1])
                    remark = remark_col.text_input("备注", key="new_needle_bed_remark", placeholder="可选，用于填写现场说明")
                    enabled_text = enabled_col.selectbox("启用", options=list(ENABLED_OPTIONS), key="new_needle_bed_enabled")
                    # 第三行：添加按钮
                    submitted = st.form_submit_button(CREATE_NEEDLE_BED_BUTTON)

                if submitted:
                    if source != BLANK_TEMPLATE:
                        template = next(r for r in rows if str(r["needle_bed_code"]) == source)
                        template_values = _frame([template], include_delete=False).to_dict("records")[0]
                    else:
                        template_values = None
                    filled = helpers.fill_missing_text_values({
                        "针床码": code.strip(),
                        "针床名称": name.strip(),
                        "针床编号": number.strip(),
                        "针床型号": model.strip(),
                        "启用": helpers.enabled_from_text(enabled_text),
                        "备注": remark.strip(),
                    }, template_values)
                    proposed = _frame(rows, include_delete=False).to_dict("records") + [filled]
                    message = f"已从模板 {source} 新建针床" if template_values else "针床已添加"
                    validated, error = _validate(proposed)
                    if error:
                        st.error(error)
                    else:
                        helpers.save_rows("needle_beds", validated or [], message)

    with st.container(border=True):
        st.subheader(NEEDLE_BED_LIST_SECTION)
        edited: pd.DataFrame | None = None
        if read_only:
            st.dataframe(_frame(rows, include_delete=False), column_config=_config(include_delete=False), hide_index=True, width="stretch", alt="针床列表")
        else:
            edited = st.data_editor(
                _frame(rows, include_delete=True),
                column_config=_config(include_delete=True),
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                alt="针床注册编辑器",
                key="needle_bed_editor",
            )

        if not read_only and st.button(SAVE_NEEDLE_BED_BUTTON, icon=":material/save:", key="save_needle_beds"):
            validated, error = _validate(edited.to_dict("records")) if edited is not None else ([], None)
            if error:
                st.error(error)
            else:
                helpers.save_rows("needle_beds", validated or [], "针床已保存")

        pending = st.session_state.get(PENDING_DELETE_KEY)
        if pending:
            row = next((item for item in rows if str(item["needle_bed_code"]) == pending), None)
            if row is None:
                _clear_pending_delete()
            else:
                _confirm_delete(row)
