"""页面：工位操作台（扫码入站、入线状态、托盘解绑、扫码解锁）。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import client, common, tag_page
from .client import ApiError as ServiceError

INBOUND_TRAY_KEY = "workbench_inbound_active_tray"
INBOUND_CAPACITY_KEY = "workbench_inbound_capacity"
INBOUND_ERROR_KEY = "workbench_inbound_error"
INBOUND_TOKEN_KEY = "workbench_inbound_token"
INBOUND_SUBMITTED_KEY = "workbench_inbound_submitted"
INBOUND_MESSAGE_KEY = "workbench_inbound_message"
INBOUND_FOCUS_KEY = "workbench_inbound_focus_key"
INBOUND_STEP_KEY = "workbench_process_step"
INBOUND_STEP_NO_KEY = "workbench_inbound_step_no"
TRAY_INPUT_KEY = "workbench_inbound_tray_input"
BARCODE_COLUMNS_KEY = "workbench_barcode_columns"
UNLOCK_ERROR_KEY = "workbench_unlock_error"
UNLOCK_TOKEN_KEY = "workbench_unlock_token"


def _text(value: Any) -> str:
    """执行 text。"""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _eligible_products(
    products: list[dict],
    processes: list[dict],
) -> list[str]:
    """执行 eligible_products。"""
    enabled_process_components = {
        str(process.get("component_no") or "")
        for process in processes
        if bool(process.get("enabled"))
    }
    return [
        str(product["product_model"])
        for product in products
        if bool(product.get("enabled"))
        and str(product.get("product_model")) in enabled_process_components
    ]


def _bound_product_frame(rows: list[dict]) -> pd.DataFrame:
    """执行 bound_product_frame。"""
    return pd.DataFrame(
        [
            {
                "条码": row.get("barcode") or "",
                "当前工序": row.get("current_step") or "",
            }
            for row in rows
        ],
        columns=["条码", "当前工序"],
    )


def _focus_scan_input(
    scan_key: str,
    marker: str,
    *,
    select_existing: bool = False,
) -> None:
    """Focus a scanner field once after an explicit scan-flow transition."""
    st.html(
        f"""
        <div data-scan-focus-marker="{marker}"></div>
        <script>
        (() => {{
          const marker = "{marker}";
          let attempts = 0;
          const timer = setInterval(() => {{
            attempts += 1;
            const root = document.querySelector('.st-key-{scan_key}');
            const input = root?.querySelector('input');
            if (input && !input.disabled) {{
              input.focus({{ preventScroll: true }});
              if ({str(select_existing).lower()}) input.select();
              clearInterval(timer);
              return;
            }}
            if (attempts >= 30) clearInterval(timer);
          }}, 100);
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _reset_inbound_batch() -> None:
    """执行 reset_inbound_batch。"""
    st.session_state[TRAY_INPUT_KEY] = ""
    st.session_state.pop(INBOUND_TRAY_KEY, None)
    st.session_state.pop(INBOUND_CAPACITY_KEY, None)
    st.session_state.pop(INBOUND_ERROR_KEY, None)
    st.session_state.pop(INBOUND_MESSAGE_KEY, None)
    st.session_state[INBOUND_SUBMITTED_KEY] = False
    st.session_state[INBOUND_TOKEN_KEY] = (
        int(st.session_state.get(INBOUND_TOKEN_KEY, 0)) + 1
    )


def _reset_inbound_for_product_change() -> None:
    """执行 reset_inbound_for_product_change。"""
    st.session_state.pop(INBOUND_STEP_KEY, None)
    st.session_state.pop(INBOUND_STEP_NO_KEY, None)
    _reset_inbound_batch()


def _reset_inbound_for_step_change() -> None:
    """执行 reset_inbound_for_step_change。"""
    _reset_inbound_batch()


def _barcode_keys(token: int, capacity: int) -> list[tuple[int, str, str]]:
    """执行 barcode_keys。"""
    return [
        (
            index,
            f"workbench_barcode_{token}_{index}",
            f"workbench_barcode_enabled_{token}_{index}",
        )
        for index in range(1, capacity + 1)
    ]


def _barcode_widget_key(
    token: int,
    index: int,
    *,
    enabled: bool,
    submitted: bool,
) -> str:
    """执行 barcode_widget_key。"""
    if submitted:
        return f"workbench_barcode_locked_{token}_{index}"
    prefix = "workbench_barcode_input" if enabled else "workbench_barcode_disabled"
    return f"{prefix}_{token}_{index}"


def _preview_capacity(trays: list[dict], allowed_models: list[str]) -> int:
    """执行 preview_capacity。"""
    allowed = {model.casefold() for model in allowed_models}
    capacities = [
        int(tray.get("capacity") or 0)
        for tray in trays
        if bool(tray.get("enabled"))
        and _text(tray.get("tray_model")).casefold() in allowed
        and int(tray.get("capacity") or 0) > 0
    ]
    return max(capacities, default=0)


def _handle_tray_change(
    tray_input_key: str,
    trays: list[dict],
    allowed_models: list[str],
) -> None:
    """执行 handle_tray_change。"""
    value = str(st.session_state.get(tray_input_key) or "").strip()
    if not value:
        return
    tray = next(
        (
            item
            for item in trays
            if str(item.get("traycode") or "").casefold() == value.casefold()
        ),
        None,
    )
    if tray is None:
        st.session_state[INBOUND_ERROR_KEY] = f"载具 {value} 未注册"
        st.session_state[tray_input_key] = ""
        return
    if not bool(tray.get("enabled")):
        st.session_state[INBOUND_ERROR_KEY] = f"载具 {tray['traycode']} 已停用"
        st.session_state[tray_input_key] = ""
        return
    if _text(tray.get("tray_model")).casefold() not in {
        model.casefold() for model in allowed_models
    }:
        st.session_state[INBOUND_ERROR_KEY] = "该载具型号不在当前工艺允许范围内"
        st.session_state[tray_input_key] = ""
        return
    capacity = int(tray.get("capacity") or 0)
    if capacity <= 0:
        st.session_state[INBOUND_ERROR_KEY] = (
            f"载具 {tray['traycode']} 未配置有效载荷"
        )
        st.session_state[tray_input_key] = ""
        return
    actual_traycode = str(tray["traycode"])
    if st.session_state.get(INBOUND_TRAY_KEY) == actual_traycode:
        st.session_state.pop(INBOUND_ERROR_KEY, None)
        return
    try:
        bound_rows = client.product_flow_overview(traycode=actual_traycode)
    except ServiceError as exc:
        st.session_state[INBOUND_ERROR_KEY] = f"检查载具占用失败：{exc}"
        st.session_state[tray_input_key] = ""
        return
    if bound_rows:
        st.session_state[INBOUND_ERROR_KEY] = (
            f"载具 {actual_traycode} 已绑定 {len(bound_rows)} 个产品"
        )
        st.session_state[tray_input_key] = ""
        return

    token = int(st.session_state.get(INBOUND_TOKEN_KEY, 0)) + 1
    st.session_state[INBOUND_TOKEN_KEY] = token
    st.session_state[INBOUND_TRAY_KEY] = actual_traycode
    st.session_state[INBOUND_CAPACITY_KEY] = capacity
    st.session_state[INBOUND_SUBMITTED_KEY] = False
    st.session_state.pop(INBOUND_ERROR_KEY, None)
    st.session_state.pop(INBOUND_MESSAGE_KEY, None)
    st.session_state[INBOUND_FOCUS_KEY] = (
        f"workbench_barcode_input_{token}_1"
    )


def _clear_inbound_inputs() -> None:
    """执行 clear_inbound_inputs。"""
    st.session_state[TRAY_INPUT_KEY] = ""
    st.session_state[INBOUND_SUBMITTED_KEY] = False
    st.session_state.pop(INBOUND_TRAY_KEY, None)
    st.session_state.pop(INBOUND_CAPACITY_KEY, None)
    st.session_state.pop(INBOUND_ERROR_KEY, None)
    st.session_state.pop(INBOUND_MESSAGE_KEY, None)
    st.session_state[INBOUND_TOKEN_KEY] = (
        int(st.session_state.get(INBOUND_TOKEN_KEY, 0)) + 1
    )
    st.session_state[INBOUND_FOCUS_KEY] = TRAY_INPUT_KEY


def _submit_or_focus_next_barcode(
    *,
    token: int,
    capacity: int,
    current_index: int,
    product_model: str,
    traycode: str,
    operator: str,
) -> None:
    """执行 submit_or_focus_next_barcode。"""
    slots = _barcode_keys(token, capacity)
    enabled_slots = [
        (index, text_key)
        for index, text_key, enabled_key in slots
        if st.session_state.get(enabled_key, True)
    ]
    completed = [
        (index, text_key)
        for index, text_key in enabled_slots
        if str(st.session_state.get(text_key) or "").strip()
    ]
    if enabled_slots and len(completed) == len(enabled_slots):
        barcodes = [
            str(st.session_state.get(text_key) or "").strip()
            for _, text_key in enabled_slots
        ]
        if len({barcode.casefold() for barcode in barcodes}) != len(barcodes):
            st.session_state[INBOUND_ERROR_KEY] = "启用的条码不能重复"
            return
        step_no = str(st.session_state.get(INBOUND_STEP_NO_KEY) or "")
        if not step_no:
            st.session_state[INBOUND_ERROR_KEY] = "请选择工序"
            return
        try:
            result = client.manual_inbound(
                product=product_model,
                step_no=step_no,
                traycode=traycode,
                barcodes=barcodes,
                operator=operator,
            )
        except ServiceError as exc:
            st.session_state[INBOUND_ERROR_KEY] = f"入站失败：{exc}"
            return
        st.session_state[INBOUND_SUBMITTED_KEY] = True
        st.session_state[INBOUND_MESSAGE_KEY] = (
            f"载具 {result['traycode']} 的 {result['count']} 个产品已入站"
        )
        st.session_state.pop(INBOUND_ERROR_KEY, None)
        st.session_state[INBOUND_FOCUS_KEY] = TRAY_INPUT_KEY
        return

    enabled_indexes = [index for index, _ in enabled_slots]
    if not enabled_indexes:
        st.session_state[INBOUND_FOCUS_KEY] = TRAY_INPUT_KEY
        return
    next_index = next(
        (index for index in enabled_indexes if index > current_index),
        enabled_indexes[0],
    )
    st.session_state[INBOUND_FOCUS_KEY] = (
        f"workbench_barcode_input_{token}_{next_index}"
    )


def _handle_barcode_change(
    *,
    widget_key: str,
    value_key: str,
    token: int,
    capacity: int,
    index: int,
    product_model: str,
    operator: str,
) -> None:
    """执行 handle_barcode_change。"""
    if st.session_state.get(INBOUND_SUBMITTED_KEY):
        return
    st.session_state[value_key] = str(
        st.session_state.get(widget_key) or ""
    ).strip()
    _submit_or_focus_next_barcode(
        token=token,
        capacity=capacity,
        current_index=index,
        product_model=product_model,
        traycode=str(st.session_state.get(INBOUND_TRAY_KEY) or ""),
        operator=operator,
    )


def _handle_enabled_change(
    *,
    token: int,
    capacity: int,
    index: int,
    product_model: str,
    operator: str,
) -> None:
    """执行 handle_enabled_change。"""
    if st.session_state.get(INBOUND_SUBMITTED_KEY):
        return
    _submit_or_focus_next_barcode(
        token=token,
        capacity=capacity,
        current_index=index,
        product_model=product_model,
        traycode=str(st.session_state.get(INBOUND_TRAY_KEY) or ""),
        operator=operator,
    )


def _handle_unlock_scan(
    scan_key: str,
    step_labels: dict[str, str],
    operator: str,
) -> None:
    """执行 handle_unlock_scan。"""
    barcode = str(st.session_state.get(scan_key) or "").strip()
    st.session_state[scan_key] = ""
    if not barcode:
        return
    st.session_state.pop(UNLOCK_ERROR_KEY, None)
    if not operator:
        st.session_state[UNLOCK_ERROR_KEY] = "侧边栏操作员不能为空"
        return

    locked, _ = client.list_locked_workpieces()
    workpiece_locked = any(
        str(item.get("workpiece")) == barcode for item in (locked or [])
    )
    if not workpiece_locked:
        try:
            flow_rows = client.product_flow_overview(barcode=barcode)
        except ServiceError as exc:
            st.session_state[UNLOCK_ERROR_KEY] = f"检查产品锁定状态失败：{exc}"
            return
        flow_locked = any(
            str(row.get("barcode")) == barcode
            and row.get("board_status") == "lock"
            for row in flow_rows
        )
        if not flow_locked:
            st.session_state[UNLOCK_ERROR_KEY] = f"产品 {barcode} 当前未锁定"
            return

    step_label = str(
        st.session_state.get("workbench_unlock_next_step") or "保持当前工序"
    )
    try:
        client.unlock_workpiece(
            workpiece=barcode,
            operator=operator,
            reason="工位操作台扫码解锁",
            confirmed=True,
            target_step=step_labels.get(step_label),
        )
    except ServiceError as exc:
        st.session_state[UNLOCK_ERROR_KEY] = f"产品解锁失败：{exc}"
        return
    common.flash("success", f"产品 {barcode} 已解锁并放行。")
    st.session_state[UNLOCK_TOKEN_KEY] = (
        int(st.session_state.get(UNLOCK_TOKEN_KEY, 0)) + 1
    )


def _render_inbound(
    *,
    product_options: list[str],
    trays: list[dict],
    read_only: bool,
) -> None:
    """执行 render_inbound。"""
    if not product_options:
        st.warning("没有已启用且绑定工艺的产品型号，请先维护组件与工艺配置。")
        return

    st.session_state.setdefault(TRAY_INPUT_KEY, "")
    st.session_state.setdefault(INBOUND_SUBMITTED_KEY, False)
    st.session_state.setdefault(BARCODE_COLUMNS_KEY, 2)
    model_column, step_column, columns_column = st.columns(
        [3, 2, 1],
        vertical_alignment="bottom",
    )
    with model_column:
        product_model = st.selectbox(
            "产品型号",
            product_options,
            index=None,
            placeholder="请选择产品型号",
            key="workbench_product_model",
            persist_state="session",
            on_change=_reset_inbound_for_product_change,
        )
    recipe = None
    route_options: dict[str, dict] = {}
    if product_model:
        try:
            recipe = client.workbench_recipe(product_model)
        except ServiceError as exc:
            st.error(f"读取产品工艺失败：{exc}")
        if recipe is not None:
            route_options = {
                f"{route['step_no']} · {route.get('step_name') or '未命名工序'}": route
                for route in recipe["steps"]
                if route.get("tray_models")
            }
    with step_column:
        step_label = st.selectbox(
            "工序",
            list(route_options),
            index=None,
            placeholder="请选择工序" if product_model else "请先选择产品型号",
            key=INBOUND_STEP_KEY,
            persist_state="session",
            on_change=_reset_inbound_for_step_change,
            disabled=not product_model or not route_options,
        )
        if product_model and recipe is not None and not route_options:
            st.warning("当前工艺没有配置允许载具型号的工序")
    with columns_column:
        columns_per_row = int(st.number_input(
            "每行条码输入框数量",
            min_value=1,
            max_value=4,
            step=1,
            key=BARCODE_COLUMNS_KEY,
            persist_state="session",
        ))
    if not product_model or recipe is None:
        return
    if not route_options:
        return
    if not step_label:
        st.session_state.pop(INBOUND_STEP_NO_KEY, None)
        return
    route = route_options[step_label]
    st.session_state[INBOUND_STEP_NO_KEY] = str(route["step_no"])
    allowed_models = list(route["tray_models"])

    error = st.session_state.pop(INBOUND_ERROR_KEY, "")
    if error:
        st.error(error)
    active_traycode = str(st.session_state.get(INBOUND_TRAY_KEY) or "")
    capacity = (
        int(st.session_state.get(INBOUND_CAPACITY_KEY) or 0)
        if active_traycode
        else _preview_capacity(trays, allowed_models)
    )
    token = int(st.session_state.get(INBOUND_TOKEN_KEY, 0))
    operator = common.operator()

    st.text_input(
        "扫描载具号",
        key=TRAY_INPUT_KEY,
        placeholder="扫描新载具后回车",
        on_change=_handle_tray_change,
        args=(TRAY_INPUT_KEY, trays, allowed_models),
        disabled=read_only,
        persist_state="session",
    )

    if capacity:
        enabled_count = 0
        completed_count = 0
        barcode_slots = _barcode_keys(token, capacity)
        submitted = bool(st.session_state.get(INBOUND_SUBMITTED_KEY))
        for row_start in range(0, len(barcode_slots), columns_per_row):
            row_slots = barcode_slots[row_start:row_start + columns_per_row]
            columns = st.columns(columns_per_row)
            for column, (index, value_key, enabled_key) in zip(columns, row_slots):
                with column:
                    with st.container(border=True):
                        st.session_state.setdefault(value_key, "")
                        st.session_state.setdefault(enabled_key, True)
                        enabled = bool(st.session_state.get(enabled_key, True))
                        widget_key = _barcode_widget_key(
                            token,
                            index,
                            enabled=enabled,
                            submitted=submitted,
                        )
                        checkbox_key = (
                            f"workbench_barcode_enabled_locked_{token}_{index}"
                            if submitted
                            else enabled_key
                        )
                        if widget_key not in st.session_state:
                            st.session_state[widget_key] = st.session_state.get(
                                value_key, ""
                            )
                        if submitted and checkbox_key not in st.session_state:
                            st.session_state[checkbox_key] = enabled
                        input_column, enabled_column = st.columns(
                            [4, 1],
                            vertical_alignment="bottom",
                        )
                        with input_column:
                            st.text_input(
                                f"条码 {index}",
                                key=widget_key,
                                placeholder="扫描条码后回车",
                                on_change=_handle_barcode_change,
                                kwargs={
                                    "widget_key": widget_key,
                                    "value_key": value_key,
                                    "token": token,
                                    "capacity": capacity,
                                    "index": index,
                                    "product_model": product_model,
                                    "operator": operator,
                                },
                                disabled=(
                                    read_only
                                    or submitted
                                    or not enabled
                                    or not active_traycode
                                ),
                                persist_state="session",
                            )
                        with enabled_column:
                            st.checkbox(
                                "启用",
                                key=checkbox_key,
                                on_change=_handle_enabled_change,
                                kwargs={
                                    "token": token,
                                    "capacity": capacity,
                                    "index": index,
                                    "product_model": product_model,
                                    "operator": operator,
                                },
                                disabled=read_only or submitted,
                                persist_state="session",
                            )
                        if enabled:
                            enabled_count += 1
                            if str(st.session_state.get(value_key) or "").strip():
                                completed_count += 1

        progress = completed_count / enabled_count if enabled_count else 0.0
        st.progress(progress)
        st.caption(f"已输入 {completed_count}/{enabled_count}")
        st.button(
            "清空输入",
            type="tertiary",
            icon=":material/backspace:",
            key="workbench_inbound_clear",
            on_click=_clear_inbound_inputs,
            disabled=read_only,
        )

    message = st.session_state.get(INBOUND_MESSAGE_KEY)
    if message:
        st.success(message)

    focus_key = st.session_state.pop(INBOUND_FOCUS_KEY, None)
    if focus_key and not read_only:
        _focus_scan_input(
            focus_key,
            marker=f"{token}-{capacity}-{completed_count if capacity else 0}",
            select_existing=focus_key == TRAY_INPUT_KEY,
        )


def _render_tray_unbind(*, trays: list[dict], read_only: bool) -> None:
    """执行 render_tray_unbind。"""
    tray_options = [str(tray["traycode"]) for tray in trays]
    if not tray_options:
        st.info("暂无已注册载具。")
        return
    traycode = st.selectbox(
        "载具号",
        tray_options,
        key="workbench_unbind_traycode",
    )
    try:
        bound_rows = client.product_flow_overview(traycode=traycode)
    except ServiceError as exc:
        st.error(f"读取托盘绑定失败：{exc}")
        return
    if not bound_rows:
        st.info(f"载具 {traycode} 当前未绑定产品。")
        return
    st.caption(
        f"当前绑定 {len(bound_rows)} 个产品 · "
        f"操作员 {common.operator() or '未填写'}"
    )
    with st.expander("查看绑定产品", expanded=False):
        st.dataframe(
            _bound_product_frame(bound_rows),
            hide_index=True,
            alt="待解绑托盘产品列表",
        )
    confirmed = st.checkbox(
        "确认解除该托盘与全部产品的绑定",
        key="workbench_unbind_confirm",
        disabled=read_only,
    )
    if st.button(
        "确认解绑托盘",
        type="secondary",
        icon=":material/link_off:",
        key="workbench_unbind_submit",
        disabled=read_only,
    ):
        try:
            result = client.unbind_tray(
                traycode=traycode,
                operator=common.operator(),
                confirmed=confirmed,
            )
        except ServiceError as exc:
            st.error(f"托盘解绑失败：{exc}")
            return
        common.flash(
            "success",
            f"载具 {result['traycode']} 已解绑 {result['count']} 个产品。",
        )
        st.rerun()


def _render_product_unlock(*, steps: list[dict], read_only: bool) -> None:
    """执行 render_product_unlock。"""
    step_labels = {
        f"{step['step_no']} · {step.get('step_name') or ''}": str(step["step_no"])
        for step in steps
        if bool(step.get("enabled", True))
    }
    st.selectbox(
        "解锁后所在工序",
        ["保持当前工序", *step_labels],
        key="workbench_unlock_next_step",
        disabled=read_only,
    )
    error = st.session_state.pop(UNLOCK_ERROR_KEY, "")
    if error:
        st.error(error)
    token = int(st.session_state.get(UNLOCK_TOKEN_KEY, 0))
    scan_key = f"workbench_unlock_scan_{token}"
    st.text_input(
        "扫描产品条码",
        key=scan_key,
        placeholder="扫描已锁定产品条码后回车",
        on_change=_handle_unlock_scan,
        args=(scan_key, step_labels, common.operator()),
        disabled=read_only,
    )
    if not read_only:
        _focus_scan_input(scan_key, f"unlock-{token}")
    st.caption("解锁原因自动记录为“工位操作台扫码解锁”，操作员取自左侧边栏。")


def render() -> None:
    """执行 render。"""
    common.init_session()
    st.title("🛠️ 工位操作台")
    st.caption("现场工位的一站式操作：扫码入站、查看入线状态、托盘解绑、扫码解锁。")
    common.render_flash()
    common.render_readonly_notice()
    read_only = not common.can_edit()

    snapshot, error = client.master_snapshot()
    common.show_error(error)
    if not snapshot:
        st.error("无法读取主数据，工位操作台暂不可用。")
        return
    products = snapshot.get("products", [])
    processes = snapshot.get("processes", [])
    steps = snapshot.get("steps", [])
    trays = snapshot.get("trays", [])
    product_options = _eligible_products(products, processes)

    inbound_tab, status_tab, unbind_tab, unlock_tab = st.tabs(
        ["手动入站", "入线状态", "托盘解绑", "产品解锁"],
        key="workbench_tabs",
        on_change="rerun",
    )
    if inbound_tab.open:
        with inbound_tab:
            _render_inbound(
                product_options=product_options,
                trays=trays,
                read_only=read_only,
            )
    if status_tab.open:
        with status_tab:
            tag_page.render_content(read_only=read_only)
    if unbind_tab.open:
        with unbind_tab:
            _render_tray_unbind(trays=trays, read_only=read_only)
    if unlock_tab.open:
        with unlock_tab:
            _render_product_unlock(steps=steps, read_only=read_only)
