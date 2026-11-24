"""设备注册页面：维护设备主数据。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from . import registry_helpers as helpers
from .constants import ENABLED_OPTIONS, ROLE_EDIT, ROLE_VIEW

DEVICE_COLUMNS = ["设备编号", "设备名称", "设备型号", "启用", "备注"]
DELETE_CLICK_KEY = "device_delete_click"
PENDING_DELETE_KEY = "pending_device_delete"


def _text(value: Any) -> str:
    """统一空值清洗，复用注册页公共实现。"""
    return helpers.clean_text(value)


def _device_frame(devices: list[dict[str, Any]], *, include_delete: bool) -> pd.DataFrame:
    """执行 device_frame。"""
    records = [
        {
            "设备编号": device["device_id"],
            "设备名称": device["device_name"],
            "设备型号": device.get("device_model", ""),
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


def _device_config(*, include_delete: bool) -> dict[str, Any]:
    """执行 device_config。"""
    config: dict[str, Any] = {
        "设备编号": st.column_config.TextColumn("设备编号", required=True, width="medium"),
        "设备名称": st.column_config.TextColumn("设备名称", required=True, width="medium"),
        "设备型号": st.column_config.TextColumn("设备型号", required=True, width="medium"),
        "启用": helpers.enabled_column(),
        "备注": st.column_config.TextColumn("备注", width="large"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除", type="tertiary", on_click=_request_device_delete,
            key=DELETE_CLICK_KEY, width="small",
        )
    return config


def _validate_devices(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """执行 validate_devices。"""
    devices: list[dict[str, Any]] = []
    device_ids: set[str] = set()
    for row in rows:
        device_id = _text(row.get("设备编号"))
        device_name = _text(row.get("设备名称"))
        device_model = _text(row.get("设备型号"))
        remark = _text(row.get("备注"))
        raw_enabled = row.get("启用")
        if not any((device_id, device_name, device_model, remark)):
            continue
        if not device_id or not device_name or not device_model:
            return None, "设备编号、设备名称和设备型号不能为空"
        if device_id.casefold() in device_ids:
            return None, "设备编号不能重复"
        device_ids.add(device_id.casefold())
        devices.append({
            "device_id": device_id,
            "device_name": device_name,
            "device_model": device_model,
            "enabled": (
                helpers.enabled_from_cell(raw_enabled)
            ),
            "remark": remark,
        })
    return devices, None


def _request_device_delete() -> None:
    """把删除按钮点击转换成 pending state。"""
    helpers.request_delete(DELETE_CLICK_KEY, PENDING_DELETE_KEY, "devices", "device_id")


def _clear_pending_delete() -> None:
    """执行 clear_pending_delete。"""
    helpers.clear_pending(PENDING_DELETE_KEY)


@st.dialog("确认删除设备", icon=":material/delete_forever:", on_dismiss=_clear_pending_delete)
def _confirm_delete_device(device: dict[str, Any]) -> None:
    """执行 confirm_delete_device。"""
    st.write(f"确定删除设备 **{device['device_id']} - {device['device_name']}** 吗？")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_device"):
            _clear_pending_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_device"):
            st.session_state.devices = [
                item for item in st.session_state.devices
                if item["device_id"] != device["device_id"]
            ]
            _clear_pending_delete()
            st.toast("设备已删除")
            st.rerun()


def render_page() -> None:
    """页面渲染入口。"""
    master.ensure_master_data()
    read_only = not helpers.is_editable()
    devices: list[dict[str, Any]] = st.session_state.devices

    st.title("🖥️ 设备注册")

    # 区块 1：新增设备
    with st.container(border=True):
        st.subheader("设备管理（可直接修改，改完点“保存设备修改”）")
        if read_only:
            with st.expander("新增设备", expanded=False):
                st.info("只读角色不可新增设备。")
        else:
            with st.expander("新增设备", expanded=False):
                with st.form("device_create_form", clear_on_submit=False, border=False):
                    # 第一行：设备编号 + 设备名称 + 设备型号
                    id_col, name_col, model_col = st.columns(3)
                    new_device_id = id_col.text_input(
                        "设备编号", key="new_device_id", placeholder="例如 TEST-05",
                    )
                    new_device_name = name_col.text_input(
                        "设备名称", key="new_device_name", placeholder="例如 包装检测机",
                    )
                    new_device_model = model_col.text_input(
                        "设备型号", key="new_device_model", placeholder="例如 DM-100",
                    )
                    # 第二行：备注 + 启用
                    remark_col, enabled_col = st.columns([3, 1])
                    new_device_remark = remark_col.text_input(
                        "备注", key="new_device_remark", placeholder="可选，用于填写现场说明",
                    )
                    new_device_enabled_text = enabled_col.selectbox(
                        "启用", options=list(ENABLED_OPTIONS), key="new_device_enabled_text",
                    )
                    submitted = st.form_submit_button("添加设备")

                if submitted:
                    proposed_rows = _device_frame(devices, include_delete=False).to_dict("records")
                    proposed_rows.append({
                        "设备编号": new_device_id.strip(),
                        "设备名称": new_device_name.strip(),
                        "设备型号": new_device_model.strip(),
                        "启用": helpers.enabled_from_text(new_device_enabled_text),
                        "备注": new_device_remark.strip(),
                    })
                    validated, error = _validate_devices(proposed_rows)
                    if error:
                        st.error(error)
                    else:
                        helpers.save_rows("devices", validated, "设备已添加")

    # 区块 2：设备列表
    with st.container(border=True):
        st.subheader("设备列表")
        edited_devices: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _device_frame(devices, include_delete=False),
                column_config=_device_config(include_delete=False),
                hide_index=True, width="stretch", alt="设备列表",
            )
        else:
            edited_devices = st.data_editor(
                _device_frame(devices, include_delete=True),
                column_config=_device_config(include_delete=True),
                hide_index=True, num_rows="fixed", width="stretch",
                alt="设备注册编辑器", key="device_editor",
            )
        save_clicked = False
        if not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                save_clicked = st.button("保存设备修改", icon=":material/save:", key="save_devices")
        if not devices:
            st.info("暂无设备，请新增")
        if save_clicked and edited_devices is not None:
            updated, error = _validate_devices(edited_devices.to_dict("records"))
            if error:
                st.error(error)
            else:
                st.session_state.devices = updated
                master.save_key("devices")
                st.toast("设备已保存")
                st.rerun()
        pending = st.session_state.get(PENDING_DELETE_KEY)
        if pending:
            dev = next((d for d in devices if d["device_id"] == pending), None)
            if dev is None:
                _clear_pending_delete()
            else:
                _confirm_delete_device(dev)
