"""设备注册页面：维护设备及其所属工序。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app_pages._mock_program_data import (
    enabled_steps,
    step_by_no,
    step_label,
)

DEVICE_COLUMNS = ["设备编号", "设备名称", "所属线体", "所属工序", "启用", "备注"]
DELETE_CLICK_KEY = "device_delete_click"
PENDING_DELETE_KEY = "pending_device_delete"
LINE_DELETE_CLICK_KEY = "line_delete_click"
PENDING_LINE_DELETE_KEY = "pending_line_delete"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _integer(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _line_frame(
    lines: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
    records = [
        {
            "线体编号": line["line_id"],
            "线体名称": line["line_name"],
        }
        for line in lines
    ]
    columns = ["线体编号", "线体名称"]
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _line_config(*, include_delete: bool) -> dict[str, Any]:
    config: dict[str, Any] = {
        "线体编号": st.column_config.TextColumn(
            "线体编号",
            required=True,
            width="medium",
        ),
        "线体名称": st.column_config.TextColumn(
            "线体名称",
            required=True,
            width="large",
        ),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除",
            type="tertiary",
            on_click=_request_line_delete,
            key=LINE_DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _validate_lines(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    lines: list[dict[str, Any]] = []
    line_ids: set[str] = set()
    for row in rows:
        line_id = _text(row.get("线体编号"))
        line_name = _text(row.get("线体名称"))
        if not line_id and not line_name:
            continue
        if not line_id or not line_name:
            return None, "线体编号和线体名称不能为空"
        if line_id.casefold() in line_ids:
            return None, "线体编号不能重复"
        line_ids.add(line_id.casefold())
        lines.append({"line_id": line_id, "line_name": line_name})
    return lines, None


def _request_line_delete() -> None:
    click = st.session_state.get(LINE_DELETE_CLICK_KEY)
    if click is None:
        return
    row_index = int(click["row"])
    lines = st.session_state.get("lines", [])
    if 0 <= row_index < len(lines):
        st.session_state[PENDING_LINE_DELETE_KEY] = str(
            lines[row_index]["line_id"]
        )


def _clear_pending_line_delete() -> None:
    st.session_state.pop(PENDING_LINE_DELETE_KEY, None)


@st.dialog(
    "确认删除线体",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_line_delete,
)
def _confirm_delete_line(line: dict[str, Any]) -> None:
    references = [
        device
        for device in st.session_state.devices
        if device.get("line_id") == line["line_id"]
    ]
    st.write(
        f"确定删除线体 **{line['line_id']} - {line['line_name']}** 吗？"
    )
    if references:
        st.caption(
            f"该线体下还有 {len(references)} 台设备，"
            "请先调整这些设备的所属线体。"
        )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("取消", key="cancel_delete_line"):
            _clear_pending_line_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_delete_line",
        ):
            if references:
                st.error(
                    f"该线体下还有 {len(references)} 台设备，"
                    "请先调整这些设备的所属线体"
                )
            else:
                st.session_state.lines = [
                    item
                    for item in st.session_state.lines
                    if item["line_id"] != line["line_id"]
                ]
                _clear_pending_line_delete()
                st.toast("线体已删除")
                st.rerun()


def _device_frame(
    devices: list[dict[str, Any]],
    *,
    include_delete: bool,
) -> pd.DataFrame:
    records = [
        {
            "设备编号": device["device_id"],
            "设备名称": device["device_name"],
            "所属线体": device["line_id"],
            "所属工序": int(device["step_no"]),
            "启用": bool(device["enabled"]),
            "备注": device.get("remark", ""),
        }
        for device in devices
    ]
    columns = list(DEVICE_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _device_config(
    lines: list[dict[str, Any]],
    active_steps: list[dict[str, Any]],
    *,
    include_delete: bool,
) -> dict[str, Any]:
    line_names = {
        str(line["line_id"]): f"{line['line_id']} - {line['line_name']}"
        for line in lines
    }
    config: dict[str, Any] = {
        "设备编号": st.column_config.TextColumn(
            "设备编号",
            required=True,
            width="medium",
        ),
        "设备名称": st.column_config.TextColumn(
            "设备名称",
            required=True,
            width="medium",
        ),
        "所属线体": st.column_config.SelectboxColumn(
            "所属线体",
            options=list(line_names),
            format_func=lambda line_id: line_names.get(line_id, line_id),
            required=True,
            width="medium",
        ),
        "所属工序": st.column_config.SelectboxColumn(
            "所属工序",
            options=[int(step["step_no"]) for step in active_steps],
            format_func=lambda step_no: step_label(active_steps, step_no),
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
            on_click=_request_device_delete,
            key=DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _validate_devices(
    rows: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    active_steps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    devices: list[dict[str, Any]] = []
    device_ids: set[str] = set()
    active_step_nos = {int(step["step_no"]) for step in active_steps}
    valid_line_ids = {str(line["line_id"]) for line in lines}

    for row in rows:
        device_id = _text(row.get("设备编号"))
        device_name = _text(row.get("设备名称"))
        line_id = _text(row.get("所属线体"))
        remark = _text(row.get("备注"))
        raw_enabled = row.get("启用")
        if not any(
            (
                device_id,
                device_name,
                line_id,
                _text(row.get("所属工序")),
                remark,
            )
        ):
            continue
        if not device_id or not device_name:
            return None, "设备编号和设备名称不能为空"
        if line_id not in valid_line_ids:
            return None, "所属线体必须选择已有线体"
        if device_id.casefold() in device_ids:
            return None, "设备编号不能重复"

        step_no = _integer(row.get("所属工序"))
        if step_no not in active_step_nos:
            return None, "所属工序必须选择启用中的工序"

        device_ids.add(device_id.casefold())
        devices.append(
            {
                "device_id": device_id,
                "device_name": device_name,
                "line_id": line_id,
                "step_no": step_no,
                "enabled": (
                    True
                    if raw_enabled is None
                    or (isinstance(raw_enabled, float) and pd.isna(raw_enabled))
                    else bool(raw_enabled)
                ),
                "remark": remark,
            }
        )

    return devices, None


def _request_device_delete() -> None:
    click = st.session_state.get(DELETE_CLICK_KEY)
    if click is None:
        return
    row_index = int(click["row"])
    devices = st.session_state.get("devices", [])
    if 0 <= row_index < len(devices):
        st.session_state[PENDING_DELETE_KEY] = str(
            devices[row_index]["device_id"]
        )


def _clear_pending_delete() -> None:
    st.session_state.pop(PENDING_DELETE_KEY, None)


@st.dialog(
    "确认删除设备",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_delete,
)
def _confirm_delete_device(device: dict[str, Any]) -> None:
    st.write(
        f"确定删除设备 **{device['device_id']} - {device['device_name']}** 吗？"
    )
    st.caption("删除后，引用该设备的产品工序将显示为‘未配置设备’。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("取消", key="cancel_delete_device"):
            _clear_pending_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_delete_device",
        ):
            st.session_state.devices = [
                item
                for item in st.session_state.devices
                if item["device_id"] != device["device_id"]
            ]
            _clear_pending_delete()
            st.toast("设备已删除")
            st.rerun()


read_only = st.session_state.get("role", "工程师") == "只读"
steps: list[dict[str, Any]] = st.session_state.steps
active_steps = enabled_steps(steps)
lines: list[dict[str, Any]] = st.session_state.lines
devices: list[dict[str, Any]] = st.session_state.devices

st.title("🖥️ 设备注册")

if not active_steps:
    st.warning("请先在工序注册页添加并启用工序")
if not lines:
    st.warning("请先在线体管理区块添加线体")


# -----------------------------------------------------------------------------
# 区块 1：线体管理
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("线体管理")
    if read_only:
        with st.expander("新增线体", expanded=False):
            st.info("只读角色不可新增线体。")
    else:
        with st.expander("新增线体", expanded=False):
            with st.form("line_create_form", clear_on_submit=False):
                id_col, name_col = st.columns(2)
                new_line_id = id_col.text_input(
                    "线体编号",
                    key="new_line_id",
                    placeholder="例如 L3",
                )
                new_line_name = name_col.text_input(
                    "线体名称",
                    key="new_line_name",
                    placeholder="例如 三线",
                )
                submitted = st.form_submit_button("添加线体")

            if submitted:
                proposed_rows = _line_frame(
                    lines, include_delete=False
                ).to_dict("records")
                proposed_rows.append(
                    {
                        "线体编号": new_line_id.strip(),
                        "线体名称": new_line_name.strip(),
                    }
                )
                validated, error = _validate_lines(proposed_rows)
                if error:
                    st.error(error)
                else:
                    st.session_state.lines = validated
                    st.toast("线体已添加")
                    st.rerun()

    save_lines_clicked = False
    if not read_only:
        with st.container(horizontal=True, horizontal_alignment="right"):
            save_lines_clicked = st.button(
                "保存线体修改",
                icon=":material/save:",
                key="save_lines",
            )

    edited_lines: pd.DataFrame | None = None
    if read_only:
        st.dataframe(
            _line_frame(lines, include_delete=False),
            column_config=_line_config(include_delete=False),
            hide_index=True,
            width="stretch",
            alt="线体列表",
        )
    else:
        edited_lines = st.data_editor(
            _line_frame(lines, include_delete=True),
            column_config=_line_config(include_delete=True),
            disabled=["线体编号"],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            alt="线体列表编辑器",
            key="line_editor",
        )

    if not lines:
        st.info("暂无线体，请新增")

    if save_lines_clicked and edited_lines is not None:
        updated_lines, error = _validate_lines(
            edited_lines.to_dict("records")
        )
        if error:
            st.error(error)
        else:
            st.session_state.lines = updated_lines
            st.toast("线体已保存")
            st.rerun()

    pending_line_id = st.session_state.get(PENDING_LINE_DELETE_KEY)
    if pending_line_id is not None:
        pending_line = next(
            (
                line
                for line in lines
                if line["line_id"] == pending_line_id
            ),
            None,
        )
        if pending_line is None:
            _clear_pending_line_delete()
        else:
            _confirm_delete_line(pending_line)


# -----------------------------------------------------------------------------
# 区块 2：新增设备
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("新增设备")
    if read_only:
        with st.expander("新增设备", expanded=False):
            st.info("只读角色不可新增设备。")
    else:
        with st.expander("新增设备", expanded=False):
            active_step_nos = [int(step["step_no"]) for step in active_steps]
            with st.form("device_create_form", clear_on_submit=False):
                id_col, name_col = st.columns([1, 2])
                new_device_id = id_col.text_input(
                    "设备编号",
                    key="new_device_id",
                    placeholder="例如 TEST-05",
                )
                new_device_name = name_col.text_input(
                    "设备名称",
                    key="new_device_name",
                    placeholder="例如 包装检测机",
                )
                line_col, step_col = st.columns(2)
                new_line_id = line_col.selectbox(
                    "所属线体",
                    options=[str(line["line_id"]) for line in lines],
                    index=None,
                    format_func=lambda line_id: next(
                        (
                            f"{line['line_id']} - {line['line_name']}"
                            for line in lines
                            if line["line_id"] == line_id
                        ),
                        line_id,
                    ),
                    placeholder="请选择线体",
                    disabled=not lines,
                    key="new_device_line_id",
                )
                new_step_no = step_col.selectbox(
                    "所属工序",
                    options=active_step_nos,
                    index=None,
                    format_func=lambda step_no: step_label(
                        active_steps, step_no
                    ),
                    placeholder="请选择启用中的工序",
                    disabled=not active_steps,
                    key="new_device_step_no",
                )
                if "new_device_enabled" not in st.session_state:
                    st.session_state["new_device_enabled"] = True
                new_device_enabled = st.checkbox(
                    "启用",
                    key="new_device_enabled",
                )
                new_device_remark = st.text_input(
                    "备注",
                    key="new_device_remark",
                    placeholder="可选，用于填写现场说明",
                )
                submitted = st.form_submit_button(
                    "添加设备",
                    disabled=not active_steps or not lines,
                )

            if submitted:
                proposed_rows = _device_frame(
                    devices, include_delete=False
                ).to_dict("records")
                proposed_rows.append(
                    {
                        "设备编号": new_device_id.strip(),
                        "设备名称": new_device_name.strip(),
                        "所属线体": new_line_id,
                        "所属工序": new_step_no,
                        "启用": bool(new_device_enabled),
                        "备注": new_device_remark.strip(),
                    }
                )
                validated, error = _validate_devices(
                    proposed_rows, lines, active_steps
                )
                if error:
                    st.error(error)
                else:
                    st.session_state.devices = validated
                    st.toast("设备已添加")
                    st.rerun()


# -----------------------------------------------------------------------------
# 区块 3：设备列表
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("设备列表")
    save_clicked = False
    if not read_only:
        with st.container(horizontal=True, horizontal_alignment="right"):
            save_clicked = st.button(
                "保存设备修改",
                icon=":material/save:",
                key="save_devices",
            )

    edited_devices: pd.DataFrame | None = None
    if read_only:
        st.dataframe(
            _device_frame(devices, include_delete=False),
            column_config=_device_config(
                lines, active_steps, include_delete=False
            ),
            hide_index=True,
            width="stretch",
            alt="设备列表",
        )
    else:
        edited_devices = st.data_editor(
            _device_frame(devices, include_delete=True),
            column_config=_device_config(
                lines, active_steps, include_delete=True
            ),
            disabled=["设备编号", "设备名称", "备注"],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            alt="设备注册编辑器",
            key="device_editor",
        )

    if not devices:
        st.info("暂无设备，请新增")

    if save_clicked and edited_devices is not None:
        updated_devices, error = _validate_devices(
            edited_devices.to_dict("records"),
            lines,
            active_steps,
        )
        if error:
            st.error(error)
        else:
            st.session_state.devices = updated_devices
            st.toast("设备已保存")
            st.rerun()

    pending_device_id = st.session_state.get(PENDING_DELETE_KEY)
    if pending_device_id is not None:
        pending_device = next(
            (
                device
                for device in devices
                if device["device_id"] == pending_device_id
            ),
            None,
        )
        if pending_device is None:
            _clear_pending_delete()
        else:
            _confirm_delete_device(pending_device)
