"""产品管理页面：维护产品、工序流程与可选设备范围。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app_pages._mock_program_data import enabled_steps, step_label

PRODUCT_COLUMNS = [
    "产品型号",
    "产品名称",
    "测试程序名",
    "测试程序路径",
    "备注",
]
ROUTE_COLUMNS = ["当前工序", "成功下站", "失败下站"]
PRODUCT_DELETE_CLICK_KEY = "product_delete_click"
PENDING_PRODUCT_DELETE_KEY = "pending_product_delete"
ROUTE_DELETE_CLICK_KEY = "product_route_delete_click"
PENDING_ROUTE_DELETE_KEY = "pending_product_route_delete"
ROUTE_WARNING_KEY = "product_route_warning"


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


def _product_frame(
    products: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
    records = [
        {
            "产品型号": product["product_model"],
            "产品名称": product.get("product_name", ""),
            "测试程序名": product.get("test_program_name", ""),
            "测试程序路径": product.get("test_program_path", ""),
            "备注": product.get("remark", ""),
        }
        for product in products
    ]
    columns = list(PRODUCT_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _product_config(*, include_delete: bool) -> dict[str, Any]:
    config: dict[str, Any] = {
        "产品型号": st.column_config.TextColumn(
            "产品型号",
            required=True,
            width="medium",
        ),
        "产品名称": st.column_config.TextColumn("产品名称", width="medium"),
        "测试程序名": st.column_config.TextColumn("测试程序名", width="medium"),
        "测试程序路径": st.column_config.TextColumn(
            "测试程序路径", width="large"
        ),
        "备注": st.column_config.TextColumn("备注", width="medium"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除",
            type="tertiary",
            on_click=_request_product_delete,
            key=PRODUCT_DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _validate_products(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    products: list[dict[str, Any]] = []
    models: set[str] = set()
    for row in rows:
        product_model = _text(row.get("产品型号"))
        product_name = _text(row.get("产品名称"))
        test_program_name = _text(row.get("测试程序名"))
        test_program_path = _text(row.get("测试程序路径"))
        remark = _text(row.get("备注"))
        if not any(
            (
                product_model,
                product_name,
                test_program_name,
                test_program_path,
                remark,
            )
        ):
            continue
        if not product_model:
            return None, "产品型号不能为空"
        if product_model.casefold() in models:
            return None, "产品型号不能重复"
        models.add(product_model.casefold())
        products.append(
            {
                "product_model": product_model,
                "product_name": product_name,
                "test_program_name": test_program_name,
                "test_program_path": test_program_path,
                "remark": remark,
            }
        )
    return products, None


def _request_product_delete() -> None:
    click = st.session_state.get(PRODUCT_DELETE_CLICK_KEY)
    if click is None:
        return
    row_index = int(click["row"])
    products = st.session_state.get("products", [])
    if 0 <= row_index < len(products):
        st.session_state[PENDING_PRODUCT_DELETE_KEY] = str(
            products[row_index]["product_model"]
        )


def _clear_pending_product_delete() -> None:
    st.session_state.pop(PENDING_PRODUCT_DELETE_KEY, None)


@st.dialog(
    "确认删除产品",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_product_delete,
)
def _confirm_delete_product(product: dict[str, Any]) -> None:
    st.write(
        f"确定删除产品 **{product['product_model']} - "
        f"{product.get('product_name', '')}** 吗？"
    )
    st.caption("删除产品将同时删除其工序流程和设备分配。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("取消", key="cancel_delete_product"):
            _clear_pending_product_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_delete_product",
        ):
            model = str(product["product_model"])
            st.session_state.products = [
                item
                for item in st.session_state.products
                if item["product_model"] != model
            ]
            st.session_state.product_routes = [
                item
                for item in st.session_state.product_routes
                if item["product_model"] != model
            ]
            st.session_state.product_step_devices = [
                item
                for item in st.session_state.product_step_devices
                if item["product_model"] != model
            ]
            _clear_pending_product_delete()
            st.toast("产品已删除")
            st.rerun()


def _request_route_delete() -> None:
    click = st.session_state.get(ROUTE_DELETE_CLICK_KEY)
    if click is None:
        return
    selected_product = st.session_state.get("selected_product")
    if selected_product is None:
        return
    current_routes = [
        route
        for route in st.session_state.get("product_routes", [])
        if route["product_model"] == selected_product
    ]
    row_index = int(click["row"])
    if 0 <= row_index < len(current_routes):
        st.session_state[PENDING_ROUTE_DELETE_KEY] = {
            "product_model": str(selected_product),
            "step_no": int(current_routes[row_index]["step_no"]),
        }


def _clear_pending_route_delete() -> None:
    st.session_state.pop(PENDING_ROUTE_DELETE_KEY, None)


@st.dialog(
    "确认删除工序节点",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_route_delete,
)
def _confirm_delete_route(route: dict[str, Any]) -> None:
    product_model = str(route["product_model"])
    step_no = int(route["step_no"])
    st.write(
        f"确定从产品 **{product_model}** 的工序流程中删除 "
        f"**{step_label(st.session_state.steps, step_no)}** 吗？"
    )
    st.caption("如有其他工序仍指向该工序，保存流程时需要重新配置下站。")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("取消", key="cancel_delete_route"):
            _clear_pending_route_delete()
            st.rerun()
        if st.button(
            "确认删除",
            type="primary",
            key="confirm_delete_route",
        ):
            st.session_state.product_routes = [
                item
                for item in st.session_state.product_routes
                if not (
                    item["product_model"] == product_model
                    and int(item["step_no"]) == step_no
                )
            ]
            _clear_pending_route_delete()
            st.toast("工序节点已删除")
            st.rerun()


def _route_frame(
    routes: list[dict[str, Any]], *, include_delete: bool
) -> pd.DataFrame:
    records = [
        {
            "当前工序": route["step_no"],
            "成功下站": str(route["success_next_step"]),
            "失败下站": str(route["fail_next_step"]),
        }
        for route in routes
    ]
    columns = list(ROUTE_COLUMNS)
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _route_next_label(value: Any, steps: list[dict[str, Any]]) -> str:
    if value == "END":
        return "结束"
    if value == "LOCK":
        return "锁定"
    return step_label(steps, value)


def _route_config(
    steps: list[dict[str, Any]], *, include_delete: bool
) -> dict[str, Any]:
    step_nos = [int(step["step_no"]) for step in steps]
    config: dict[str, Any] = {
        "当前工序": st.column_config.SelectboxColumn(
            "当前工序",
            options=step_nos,
            format_func=lambda value: step_label(steps, value),
            required=True,
            width="medium",
        ),
        "成功下站": st.column_config.SelectboxColumn(
            "成功下站",
            options=["END", *(str(step_no) for step_no in step_nos)],
            format_func=lambda value: _route_next_label(value, steps),
            required=True,
            width="medium",
        ),
        "失败下站": st.column_config.SelectboxColumn(
            "失败下站",
            options=[
                "END",
                "LOCK",
                *(str(step_no) for step_no in step_nos),
            ],
            format_func=lambda value: _route_next_label(value, steps),
            required=True,
            width="medium",
        ),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除",
            type="tertiary",
            on_click=_request_route_delete,
            key=ROUTE_DELETE_CLICK_KEY,
            width="small",
        )
    return config


def _validate_routes(
    rows: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    routes: list[dict[str, Any]] = []
    current_steps: set[int] = set()
    active_step_nos = {int(step["step_no"]) for step in steps}

    for line_no, row in enumerate(rows, start=1):
        current = _integer(row.get("当前工序"))
        success = _integer(row.get("成功下站"))
        fail = _integer(row.get("失败下站"))
        success_raw = _text(row.get("成功下站"))
        fail_raw = _text(row.get("失败下站"))

        if current is None and not success_raw and not fail_raw:
            continue
        if current is None:
            return None, f"第 {line_no} 行当前工序不能为空"
        if current not in active_step_nos:
            return None, f"第 {line_no} 行当前工序不属于启用工序"
        if current in current_steps:
            return None, "同一产品下当前工序不能重复"
        current_steps.add(current)

        if success_raw not in {"END"} and success is None:
            return None, f"第 {line_no} 行的成功下站无效"
        if fail_raw not in {"END", "LOCK"} and fail is None:
            return None, f"第 {line_no} 行的失败下站无效"
        routes.append(
            {
                "step_no": current,
                "success_next_step": (
                    "END" if success_raw == "END" else success
                ),
                "fail_next_step": (
                    fail_raw
                    if fail_raw in {"END", "LOCK"}
                    else fail
                ),
            }
        )

    for line_no, route in enumerate(routes, start=1):
        success = route["success_next_step"]
        if isinstance(success, int) and success not in current_steps:
            return (
                None,
                f"第 {line_no} 行的成功下站指向工序 {success}，"
                "但该工序未在当前产品流程中配置",
            )
        fail = route["fail_next_step"]
        if isinstance(fail, int) and fail not in current_steps:
            return (
                None,
                f"第 {line_no} 行的失败下站指向工序 {fail}，"
                "但该工序未在当前产品流程中配置",
            )

    return routes, None


def _success_route_has_cycle(routes: list[dict[str, Any]]) -> bool:
    graph = {
        int(route["step_no"]): route["success_next_step"]
        for route in routes
        if isinstance(route["success_next_step"], int)
    }
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(step_no: int) -> bool:
        if step_no in visiting:
            return True
        if step_no in visited:
            return False
        visiting.add(step_no)
        next_step = graph.get(step_no)
        if isinstance(next_step, int) and visit(next_step):
            return True
        visiting.remove(step_no)
        visited.add(step_no)
        return False

    return any(visit(step_no) for step_no in graph)


read_only = st.session_state.get("role", "工程师") == "只读"
steps: list[dict[str, Any]] = st.session_state.steps
active_steps = enabled_steps(steps)
lines: list[dict[str, Any]] = st.session_state.lines
devices: list[dict[str, Any]] = st.session_state.devices
products: list[dict[str, Any]] = st.session_state.products
product_routes: list[dict[str, Any]] = st.session_state.product_routes
product_step_devices: list[dict[str, Any]] = st.session_state.product_step_devices

st.title("📋 产品管理")


# -----------------------------------------------------------------------------
# 区块 1：新增产品
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("新增产品")
    if read_only:
        with st.expander("新增产品", expanded=False):
            st.info("只读角色不可新增产品。")
    else:
        with st.expander("新增产品", expanded=False):
            with st.form("product_create_form", clear_on_submit=False):
                name_col, model_col = st.columns(2)
                product_name = name_col.text_input(
                    "产品名称",
                    key="new_product_name",
                    placeholder="可选",
                )
                product_model = model_col.text_input(
                    "产品型号",
                    key="new_product_model",
                    placeholder="例如 P-1003",
                )
                test_program_name = st.text_input(
                    "测试程序名",
                    key="new_product_test_program_name",
                    placeholder="可选",
                )
                test_program_path = st.text_input(
                    "测试程序路径",
                    key="new_product_test_program_path",
                    placeholder="可选",
                )
                remark = st.text_input(
                    "备注",
                    key="new_product_remark",
                    placeholder="可选",
                )
                submitted = st.form_submit_button("添加产品")

            if submitted:
                clean_model = product_model.strip()
                if not clean_model:
                    st.error("产品型号不能为空")
                elif any(
                    item["product_model"].casefold() == clean_model.casefold()
                    for item in products
                ):
                    st.error("产品型号不能重复")
                else:
                    products.append(
                        {
                            "product_model": clean_model,
                            "product_name": product_name.strip(),
                            "test_program_name": test_program_name.strip(),
                            "test_program_path": test_program_path.strip(),
                            "remark": remark.strip(),
                        }
                    )
                    st.session_state.products = products
                    st.toast("产品已添加")
                    st.rerun()


# -----------------------------------------------------------------------------
# 区块 2：产品列表
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("产品列表")
    save_products_clicked = False
    if not read_only:
        with st.container(horizontal=True, horizontal_alignment="right"):
            save_products_clicked = st.button(
                "保存产品修改",
                icon=":material/save:",
                key="save_products",
            )

    edited_products: pd.DataFrame | None = None
    if read_only:
        st.dataframe(
            _product_frame(products, include_delete=False),
            column_config=_product_config(include_delete=False),
            hide_index=True,
            width="stretch",
            alt="产品列表",
        )
    else:
        edited_products = st.data_editor(
            _product_frame(products, include_delete=True),
            column_config=_product_config(include_delete=True),
            disabled=["产品型号"],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            alt="产品列表编辑器",
            key="product_editor",
        )

    if not products:
        st.info("暂无产品，请新增")

    if save_products_clicked and edited_products is not None:
        updated_products, error = _validate_products(
            edited_products.to_dict("records")
        )
        if error:
            st.error(error)
        else:
            st.session_state.products = updated_products
            st.toast("产品已保存")
            st.rerun()

    pending_product_model = st.session_state.get(PENDING_PRODUCT_DELETE_KEY)
    if pending_product_model is not None:
        pending_product = next(
            (
                product
                for product in products
                if product["product_model"] == pending_product_model
            ),
            None,
        )
        if pending_product is None:
            _clear_pending_product_delete()
        else:
            _confirm_delete_product(pending_product)


# -----------------------------------------------------------------------------
# 区块 3：产品工序流程
# -----------------------------------------------------------------------------
selected_product: str | None = None
with st.container(border=True):
    st.subheader("产品工序流程")
    route_warning = st.session_state.pop(ROUTE_WARNING_KEY, None)
    if route_warning:
        st.warning(route_warning)

    if not products:
        st.info("暂无产品，请先在区块 1 新增产品")
    else:
        selected_product = st.selectbox(
            "选择产品",
            options=[product["product_model"] for product in products],
            format_func=lambda model: next(
                (
                    f"{product['product_model']} - "
                    f"{product['product_name']}"
                    for product in products
                    if product["product_model"] == model
                ),
                model,
            ),
            key="selected_product",
        )
        current_routes = [
            route
            for route in product_routes
            if route["product_model"] == selected_product
        ]
        edited_routes: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _route_frame(current_routes, include_delete=False),
                column_config=_route_config(
                    active_steps, include_delete=False
                ),
                hide_index=True,
                width="stretch",
                alt="产品工序流程",
            )
        else:
            edited_routes = st.data_editor(
                _route_frame(current_routes, include_delete=True),
                column_config=_route_config(
                    active_steps, include_delete=True
                ),
                hide_index=True,
                num_rows="add",
                width="stretch",
                alt="产品工序流程编辑器",
                key=f"route_editor_{selected_product}",
            )
        if not current_routes:
            st.info("暂无工序流程，请新增")

        st.caption(
            "流程表只定义工件流向；某道工序允许用哪些设备，在下一区块分配。"
        )
        if not read_only and st.button(
            "保存工序流程",
            icon=":material/save:",
            key="save_product_routes",
        ):
            updated_routes, error = _validate_routes(
                edited_routes.to_dict("records"),
                active_steps,
            )
            if error:
                st.error(error)
            else:
                if _success_route_has_cycle(updated_routes):
                    st.session_state[ROUTE_WARNING_KEY] = (
                        "工序流程的成功下站存在环路，请确认是否符合预期"
                    )
                retained = [
                    route
                    for route in product_routes
                    if route["product_model"] != selected_product
                ]
                retained.extend(
                    {"product_model": selected_product, **route}
                    for route in updated_routes
                )
                st.session_state.product_routes = retained
                st.toast("工序流程已保存")
                st.rerun()

        pending_route = st.session_state.get(PENDING_ROUTE_DELETE_KEY)
        if pending_route is not None:
            route = next(
                (
                    item
                    for item in st.session_state.product_routes
                    if item["product_model"]
                    == pending_route["product_model"]
                    and int(item["step_no"])
                    == int(pending_route["step_no"])
                ),
                None,
            )
            if route is None:
                _clear_pending_route_delete()
            else:
                _confirm_delete_route(route)


# -----------------------------------------------------------------------------
# 区块 4：为型号分配设备
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("为型号分配设备")
    if selected_product is None:
        st.info("请先在上一区块选择产品")
    else:
        st.caption(f"当前产品：{selected_product}")
        if not lines:
            st.warning("请先在设备注册页的线体管理区块添加线体")
        else:
            line_col, step_col = st.columns(2)
            with line_col:
                selected_line_id = st.selectbox(
                    "选择线体",
                    options=[str(line["line_id"]) for line in lines],
                    format_func=lambda line_id: next(
                        (
                            f"{line['line_id']} - {line['line_name']}"
                            for line in lines
                            if line["line_id"] == line_id
                        ),
                        line_id,
                    ),
                    key="assign_line",
                )
            with step_col:
                if not active_steps:
                    st.warning("请先在工序注册页添加并启用工序")
                    selected_step_no = None
                else:
                    selected_step_no = st.selectbox(
                        "选择工序",
                        options=[
                            int(step["step_no"]) for step in active_steps
                        ],
                        format_func=lambda step_no: step_label(
                            active_steps, step_no
                        ),
                        key="assign_step",
                    )

        if lines and selected_step_no is not None:
            current_routes = [
                route
                for route in product_routes
                if route["product_model"] == selected_product
            ]
            devices_by_id = {
                str(device["device_id"]): device for device in devices
            }
            assigned_by_step: dict[int, set[str]] = {}
            for item in product_step_devices:
                if item["product_model"] != selected_product:
                    continue
                assigned_by_step.setdefault(int(item["step_no"]), set()).add(
                    str(item["device_id"])
                )
            for route in current_routes:
                step_no = int(route["step_no"])
                assigned_ids = assigned_by_step.get(step_no, set())
                same_line_assigned = {
                    device_id
                    for device_id in assigned_ids
                    if (
                        (device := devices_by_id.get(device_id)) is not None
                        and device.get("line_id") == selected_line_id
                        and int(device["step_no"]) == step_no
                        and bool(device["enabled"])
                    )
                }
                if not same_line_assigned:
                    st.warning(
                        f"工序 {step_label(steps, step_no)} "
                        "在当前线体下尚未分配设备"
                    )

            candidates = [
                device
                for device in devices
                if bool(device["enabled"])
                and int(device["step_no"]) == int(selected_step_no)
                and device.get("line_id") == selected_line_id
            ]
            if not candidates:
                st.info(
                    "当前线体下该工序暂无启用设备，"
                    "请先在设备注册页添加或调整设备"
                )
            else:
                candidate_ids = [
                    str(device["device_id"]) for device in candidates
                ]
                candidate_id_set = set(candidate_ids)
                device_names = {
                    str(device["device_id"]): (
                        f"{device['device_id']} - {device['device_name']}"
                    )
                    for device in candidates
                }
                selected_device_ids = {
                    str(item["device_id"])
                    for item in product_step_devices
                    if item["product_model"] == selected_product
                    and int(item["step_no"]) == int(selected_step_no)
                }
                assignment_key = (
                    f"assign_{selected_product}_{selected_line_id}_"
                    f"{selected_step_no}"
                )
                if assignment_key not in st.session_state:
                    st.session_state[assignment_key] = [
                        device_id
                        for device_id in candidate_ids
                        if device_id in selected_device_ids
                    ]
                selected_devices = st.multiselect(
                    "选择设备",
                    options=candidate_ids,
                    format_func=lambda device_id: device_names[device_id],
                    disabled=read_only,
                    key=assignment_key,
                )

                if not read_only and st.button(
                    "保存设备分配",
                    icon=":material/save:",
                    key="save_product_step_devices",
                ):
                    if any(
                        device_id not in candidate_id_set
                        for device_id in selected_devices
                    ):
                        st.error(
                            "选中的设备必须属于当前线体、当前工序且已启用"
                        )
                        st.stop()
                    retained = [
                        item
                        for item in product_step_devices
                        if not (
                            item["product_model"] == selected_product
                            and int(item["step_no"])
                            == int(selected_step_no)
                        )
                    ]
                    retained.extend(
                        {
                            "product_model": selected_product,
                            "step_no": int(selected_step_no),
                            "device_id": device_id,
                        }
                        for device_id in selected_devices
                    )
                    st.session_state.product_step_devices = retained
                    st.toast("设备分配已保存")
                    st.rerun()
        st.caption(
            "设备分配按“线体 + 工序”过滤候选设备；切换线体或工序后，"
            "已保存的分配不会自动变化，需重新勾选并保存。"
        )
