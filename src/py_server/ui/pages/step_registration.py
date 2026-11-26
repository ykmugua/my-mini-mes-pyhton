"""工序注册页面：维护全厂可选的工序主数据。"""

from __future__ import annotations

import re

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from . import registry_helpers as helpers
from .constants import (
    BLANK_TEMPLATE,
    CREATE_STEP_BUTTON,
    CREATE_STEP_SECTION,
    ENABLED_OPTIONS,
    SAVE_STEP_BUTTON,
    STEP_LIST_SECTION,
    STEP_NO_PATTERN,
)

STEP_COLUMNS = ["工序号", "工序名", "启用", "备注"]
DELETE_CLICK_KEY = "step_delete_click"
PENDING_DELETE_KEY = "pending_step_delete"


def _text(value: Any) -> str:
    """统一空值清洗。"""
    return helpers.clean_text(value)


def _step_frame(
    steps: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
    """执行 step_frame。"""
    records = [
        {
            "工序号": step["step_no"],
            "工序名": step["step_name"],
            "启用": bool(step["enabled"]),
            "备注": step.get("remark", ""),
        }
        for step in steps
    ]
    columns = list(STEP_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _step_config(*, include_delete: bool) -> dict[str, Any]:
    """执行 step_config。"""
    config: dict[str, Any] = {
        "工序号": st.column_config.TextColumn(
            "工序号",
            help="必填，全厂唯一；只能包含英文字母和数字。",
            required=True,
            width="small",
            validate=rf"^{STEP_NO_PATTERN}$",
        ),
        "工序名": st.column_config.TextColumn(
            "工序名",
            required=True,
            width="medium",
        ),
        "启用": helpers.enabled_column(),
        "备注": st.column_config.TextColumn("备注", width="large"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除",
            type="tertiary",
            on_click=_request_step_delete,
            key=DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _validate_steps(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """执行 validate_steps。"""
    steps: list[dict[str, Any]] = []
    step_nos: set[str] = set()
    step_names: set[str] = set()

    for row in rows:
        raw_step_no = row.get("工序号")
        step_name = _text(row.get("工序名"))
        remark = _text(row.get("备注"))
        raw_enabled = row.get("启用")

        if raw_step_no is None or (
            isinstance(raw_step_no, float) and pd.isna(raw_step_no)
        ):
            if not step_name and not remark:
                continue
            return None, "工序号和工序名不能为空"
        if not _text(raw_step_no):
            return None, "工序号和工序名不能为空"

        step_no = _text(raw_step_no)
        if not re.fullmatch(STEP_NO_PATTERN, step_no):
            return None, "工序号只能包含英文字母和数字"
        if not step_name:
            return None, "工序号和工序名不能为空"
        if step_no in step_nos:
            return None, "工序号不能重复"
        if step_name.casefold() in step_names:
            return None, "工序名不能重复"

        step_nos.add(step_no)
        step_names.add(step_name.casefold())
        steps.append(
            {
                "step_no": step_no,
                "step_name": step_name,
                "enabled": (
                helpers.enabled_from_cell(raw_enabled)
                ),
                "remark": remark,
            }
        )

    return steps, None


def _request_step_delete() -> None:
    """记录待删除工序号。"""
    helpers.request_delete(DELETE_CLICK_KEY, PENDING_DELETE_KEY, "steps", "step_no")


def _clear_pending_delete() -> None:
    """执行 clear_pending_delete。"""
    helpers.clear_pending(PENDING_DELETE_KEY)


@st.dialog(
    "确认删除工序",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_delete,
)
def _confirm_delete_step(step: dict[str, Any]) -> None:
    """执行 confirm_delete_step。"""
    st.write(
        f"确定删除工序 **{step['step_no']} - {step['step_name']}** 吗？"
    )
    st.caption("删除后，历史程序中的该工序引用将显示为“未配置工序”。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_step"):
            _clear_pending_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_delete_step",
        ):
            st.session_state.steps = [
                item
                for item in st.session_state.steps
                if str(item["step_no"]) != str(step["step_no"])
            ]
            master.save_key("steps")
            _clear_pending_delete()
            st.toast("工序已删除")
            st.rerun()




def render_page() -> None:
    """页面渲染入口。"""
    read_only = not helpers.is_editable()
    master.ensure_master_data()
    steps: list[dict[str, Any]] = st.session_state.steps

    # -----------------------------------------------------------------------------
    # 区块 1：新增工序（折叠表单）
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        with st.expander(CREATE_STEP_SECTION, expanded=False):
            submitted = False
            if read_only:
                st.info("只读角色不可新增工序。")
            else:
                with st.form("step_create_form", clear_on_submit=False, border=False):
                    step_col, name_col, template_col = st.columns([1, 2, 1])
                    source = template_col.selectbox(
                        "从原有模板中新建",
                        options=[BLANK_TEMPLATE, *[str(s["step_no"]) for s in steps]],
                        key="new_step_template",
                    )
                    new_step_no = step_col.text_input(
                        "工序号",
                        key="new_step_no",
                        placeholder="例如 5",
                    )
                    new_step_name = name_col.text_input(
                        "工序名",
                        key="new_step_name",
                        placeholder="例如 包装",
                    )
                    remark_col, enabled_col = st.columns([3, 1])
                    new_step_remark = remark_col.text_input(
                        "备注",
                        key="new_step_remark",
                        placeholder="可选，用于填写现场说明",
                    )
                    new_step_enabled_text = enabled_col.selectbox(
                        "启用", options=list(ENABLED_OPTIONS), key="new_step_enabled_text",
                    )
                    submitted = st.form_submit_button(CREATE_STEP_BUTTON)

                if submitted:
                    template_values = None
                    if source != BLANK_TEMPLATE:
                        row = next(s for s in steps if str(s["step_no"]) == source)
                        template_values = _step_frame([row], include_delete=False).to_dict("records")[0]
                    filled = helpers.fill_missing_text_values({
                        "工序号": new_step_no.strip(),
                        "工序名": new_step_name.strip(),
                        "启用": helpers.enabled_from_text(new_step_enabled_text),
                        "备注": new_step_remark.strip(),
                    }, template_values)
                    proposed_rows = _step_frame(steps, include_delete=False).to_dict("records") + [filled]
                    success_message = f"已从模板 {source} 新建工序" if template_values else "工序已新增"
                    validated, error = _validate_steps(proposed_rows)
                    if error:
                        st.error(error)
                    else:
                        helpers.save_rows("steps", validated, success_message)


    # -----------------------------------------------------------------------------
    # 区块 2：工序列表
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader(STEP_LIST_SECTION)
        edited_steps: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _step_frame(steps, include_delete=False),
                column_config=_step_config(include_delete=False),
                hide_index=True,
                width="stretch",
                alt="工序列表",
            )
        else:
            edited_steps = st.data_editor(
                _step_frame(steps, include_delete=True),
                column_config=_step_config(include_delete=True),
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                alt="工序注册编辑器",
                key="step_editor",
            )

        save_clicked = False
        if not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                save_clicked = st.button(
                    SAVE_STEP_BUTTON,
                    icon=":material/save:",
                    key="save_steps",
                )

        if not steps:
            st.info("暂无工序，请新增")

        if save_clicked and edited_steps is not None:
            updated_steps, error = _validate_steps(
                edited_steps.to_dict("records")
            )
            if error:
                st.error(error)
            else:
                st.session_state.steps = updated_steps
                master.save_key("steps")
                st.toast("工序已保存")
                st.rerun()

        pending_step_no = st.session_state.get(PENDING_DELETE_KEY)
        if pending_step_no is not None:
            pending_step = next(
                (
                    step
                    for step in steps
                    if str(step["step_no"]) == str(pending_step_no)
                ),
                None,
            )
            if pending_step is None:
                _clear_pending_delete()
            else:
                _confirm_delete_step(pending_step)
