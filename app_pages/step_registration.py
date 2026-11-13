"""工序注册页面：维护全厂可选的工序主数据。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

STEP_COLUMNS = ["工序号", "工序名", "启用", "备注"]
DELETE_CLICK_KEY = "step_delete_click"
PENDING_DELETE_KEY = "pending_step_delete"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _step_frame(
    steps: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
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
    config: dict[str, Any] = {
        "工序号": st.column_config.NumberColumn(
            "工序号",
            help="必填，全厂唯一。",
            min_value=1,
            step=1,
            format="%d",
            required=True,
            width="small",
        ),
        "工序名": st.column_config.TextColumn(
            "工序名",
            required=True,
            width="medium",
        ),
        "启用": st.column_config.CheckboxColumn(
            "启用",
            default=True,
            width="small",
        ),
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
    steps: list[dict[str, Any]] = []
    step_nos: set[int] = set()
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

        try:
            step_no = int(float(raw_step_no))
        except (TypeError, ValueError):
            return None, "工序号必须是正整数"
        if step_no < 1:
            return None, "工序号必须是正整数"
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
                    True
                    if raw_enabled is None
                    or (isinstance(raw_enabled, float) and pd.isna(raw_enabled))
                    else bool(raw_enabled)
                ),
                "remark": remark,
            }
        )

    return steps, None


def _request_step_delete() -> None:
    click = st.session_state.get(DELETE_CLICK_KEY)
    if click is None:
        return
    row_index = int(click["row"])
    steps = st.session_state.get("steps", [])
    if 0 <= row_index < len(steps):
        st.session_state[PENDING_DELETE_KEY] = int(steps[row_index]["step_no"])


def _clear_pending_delete() -> None:
    st.session_state.pop(PENDING_DELETE_KEY, None)


@st.dialog(
    "确认删除工序",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_delete,
)
def _confirm_delete_step(step: dict[str, Any]) -> None:
    st.write(
        f"确定删除工序 **{step['step_no']} - {step['step_name']}** 吗？"
    )
    st.caption("删除后，历史程序中的该工序引用将显示为“未配置工序”。")
    with st.container(horizontal=True, horizontal_alignment="right"):
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
                if int(item["step_no"]) != int(step["step_no"])
            ]
            _clear_pending_delete()
            st.toast("工序已删除")
            st.rerun()


read_only = st.session_state.get("role", "工程师") == "只读"
steps: list[dict[str, Any]] = st.session_state.steps

st.title("🧱 工序注册")


# -----------------------------------------------------------------------------
# 区块 1：新增工序
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("新增工序")
    if read_only:
        with st.expander("新增工序", expanded=False):
            st.info("只读角色不可新增工序。")
    else:
        with st.expander("新增工序", expanded=False):
            with st.form("step_create_form", clear_on_submit=False):
                step_col, name_col = st.columns([1, 2])
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
                if "new_step_enabled" not in st.session_state:
                    st.session_state["new_step_enabled"] = True
                new_step_enabled = st.checkbox(
                    "启用",
                    key="new_step_enabled",
                )
                new_step_remark = st.text_input(
                    "备注",
                    key="new_step_remark",
                    placeholder="可选，用于填写现场说明",
                )
                submitted = st.form_submit_button("新增工序")

            if submitted:
                proposed_rows = _step_frame(
                    steps, include_delete=False
                ).to_dict("records")
                proposed_rows.append(
                    {
                        "工序号": new_step_no.strip(),
                        "工序名": new_step_name.strip(),
                        "启用": bool(new_step_enabled),
                        "备注": new_step_remark.strip(),
                    }
                )
                validated, error = _validate_steps(proposed_rows)
                if error:
                    st.error(error)
                else:
                    st.session_state.steps = validated
                    st.toast("工序已新增")
                    st.rerun()


# -----------------------------------------------------------------------------
# 区块 2：工序列表
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("工序列表")
    save_clicked = False
    if not read_only:
        with st.container(horizontal=True, horizontal_alignment="right"):
            save_clicked = st.button(
                "保存工序",
                icon=":material/save:",
                key="save_steps",
            )

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
            disabled=["工序号", "工序名", "备注"],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            alt="工序注册编辑器",
            key="step_editor",
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
            st.toast("工序已保存")
            st.rerun()

    pending_step_no = st.session_state.get(PENDING_DELETE_KEY)
    if pending_step_no is not None:
        pending_step = next(
            (
                step
                for step in steps
                if int(step["step_no"]) == int(pending_step_no)
            ),
            None,
        )
        if pending_step is None:
            _clear_pending_delete()
        else:
            _confirm_delete_step(pending_step)
