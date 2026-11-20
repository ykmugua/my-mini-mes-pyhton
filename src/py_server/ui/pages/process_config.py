"""产品组件注册页面：维护产品型号、工序流程与可选设备范围。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master

from ._mock_program_data import enabled_steps, step_label

PRODUCT_COLUMNS = [
    "产品型号",
    "产品型号名称",
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
            "产品型号名称": product.get("product_name", ""),
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
        "产品型号名称": st.column_config.TextColumn("产品型号名称", width="medium"),
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
        product_name = _text(row.get("产品型号名称"))
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
    "确认删除产品型号",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_product_delete,
)
def _confirm_delete_product(product: dict[str, Any]) -> None:
    st.write(
        f"确定删除产品型号 **{product['product_model']} - "
        f"{product.get('product_name', '')}** 吗？"
    )
    st.caption("删除产品型号将同时删除其工序流程和设备分配。")
    with st.container(horizontal=True, horizontal_alignment="left"):
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
            st.toast("产品型号已删除")
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
        f"确定从产品型号 **{product_model}** 的工序流程中删除 "
        f"**{step_label(st.session_state.steps, step_no)}** 吗？"
    )
    st.caption("如有其他工序仍指向该工序，保存流程时需要重新配置下站。")
    with st.container(horizontal=True, horizontal_alignment="left"):
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
            return None, "同一产品型号下当前工序不能重复"
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
                "但该工序未在当前产品型号流程中配置",
            )
        fail = route["fail_next_step"]
        if isinstance(fail, int) and fail not in current_steps:
            return (
                None,
                f"第 {line_no} 行的失败下站指向工序 {fail}，"
                "但该工序未在当前产品型号流程中配置",
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




def render_page() -> None:
    """页面渲染入口（app_pages 脚本包装）。"""
    master.ensure_master_data()
    read_only = st.session_state.get("role", "工程师") == "只读"
    steps: list[dict[str, Any]] = st.session_state.steps
    active_steps = enabled_steps(steps)
    devices: list[dict[str, Any]] = st.session_state.devices
    products: list[dict[str, Any]] = st.session_state.products
    product_routes: list[dict[str, Any]] = st.session_state.product_routes
    product_step_devices: list[dict[str, Any]] = st.session_state.product_step_devices
    trays: list[dict[str, Any]] = st.session_state.get("trays", [])
    product_trays: list[dict[str, Any]] = st.session_state.get("product_trays", [])

    st.title("⚙️ 工艺配置")


    # -----------------------------------------------------------------------------
    # 区块 3：产品型号工序流程
    # -----------------------------------------------------------------------------
    selected_product: str | None = None
    with st.container(border=True):
        st.subheader("产品型号工序流程")
        route_warning = st.session_state.pop(ROUTE_WARNING_KEY, None)
        if route_warning:
            st.warning(route_warning)

        if not products:
            st.info("暂无产品型号，请先在组件注册页新增产品型号")
        else:
            selected_product = st.selectbox(
                "选择产品型号",
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
                    alt="产品型号工序流程",
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
                    alt="产品型号工序流程编辑器",
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
                    master.save_key("product_routes")
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
    # 区块 4：为型号分配设备（单线：候选为全部启用设备）
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("为型号分配设备")
        if selected_product is None:
            st.info("请先在上一区块选择产品型号")
        elif not active_steps:
            st.warning("请先在工序注册页添加并启用工序")
        else:
            st.caption(f"当前产品型号：{selected_product}")
            selected_step_no = st.selectbox(
                "选择工序",
                options=[str(step["step_no"]) for step in active_steps],
                format_func=lambda step_no: step_label(active_steps, step_no),
                key="assign_step",
            )
            enabled_devices = [d for d in devices if bool(d.get("enabled"))]
            candidate_ids = [str(d["device_id"]) for d in enabled_devices]
            device_names = {
                str(d["device_id"]): f"{d['device_id']} - {d['device_name']}"
                for d in enabled_devices
            }
            selected_device_ids = {
                str(item["device_id"])
                for item in product_step_devices
                if item["product_model"] == selected_product
                and str(item["step_no"]) == str(selected_step_no)
            }
            assignment_key = f"assign_{selected_product}_{selected_step_no}"
            if assignment_key not in st.session_state:
                st.session_state[assignment_key] = [
                    did for did in candidate_ids if did in selected_device_ids
                ]
            selected_devices = st.multiselect(
                "选择设备", options=candidate_ids,
                format_func=lambda did: device_names[did],
                disabled=read_only, key=assignment_key,
            )
            if not read_only and st.button(
                "保存设备分配", icon=":material/save:", key="save_product_step_devices",
            ):
                retained = [
                    item for item in product_step_devices
                    if not (
                        item["product_model"] == selected_product
                        and str(item["step_no"]) == str(selected_step_no)
                    )
                ]
                retained.extend(
                    {"product_model": selected_product, "step_no": str(selected_step_no), "device_id": did}
                    for did in selected_devices
                )
                st.session_state.product_step_devices = retained
                master.save_key("product_step_devices")
                st.toast("设备分配已保存")
                st.rerun()
            st.caption("单线运行：候选设备为全部启用设备；切换工序后需重新勾选并保存。")

    # -----------------------------------------------------------------------------
    # 区块 5：为型号分配载具
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("为型号分配载具")
        if selected_product is None:
            st.info("请先在上方选择产品型号")
        else:
            st.caption(f"当前产品型号：{selected_product}")
            enabled_trays = [t for t in trays if bool(t.get("enabled"))]
            if not enabled_trays:
                st.warning("请先在载具注册页添加并启用载具")
            else:
                tray_names = {
                    str(t["traycode"]): (
                        f"{t['traycode']} - {t.get('tray_name','')}"
                        f"（{t.get('tray_model','')}）"
                    )
                    for t in enabled_trays
                }
                candidate_codes = list(tray_names)
                selected_codes = {
                    str(item["traycode"])
                    for item in product_trays
                    if item["product_model"] == selected_product
                }
                assign_key = f"assign_trays_{selected_product}"
                if assign_key not in st.session_state:
                    st.session_state[assign_key] = [
                        code for code in candidate_codes if code in selected_codes
                    ]
                chosen = st.multiselect(
                    "选择载具",
                    options=candidate_codes,
                    format_func=lambda code: tray_names[code],
                    disabled=read_only,
                    key=assign_key,
                )
                if not read_only and st.button(
                    "保存载具分配", icon=":material/save:", key="save_product_trays",
                ):
                    candidate_set = set(candidate_codes)
                    if any(code not in candidate_set for code in chosen):
                        st.error("选中的载具必须是启用中的载具")
                    else:
                        retained = [
                            item for item in product_trays
                            if item["product_model"] != selected_product
                        ]
                        retained.extend(
                            {"product_model": selected_product, "traycode": code}
                            for code in chosen
                        )
                        st.session_state.product_trays = retained
                        master.save_key("product_trays")
                        st.toast("载具分配已保存")
                        st.rerun()

    # -------------------------------------------------------------------------
    # 区块 6：型号关联
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("型号关联")
        program_names = sorted({p["program_name"] for p in st.session_state.get("programs", [])})
        if not program_names:
            st.info("暂无程序，请先在程序注册页新增程序")
        else:
            selected_prog = st.selectbox("选择程序", program_names, key="pc_component_program")
            prog_ids = {
                str(p["program_id"]) for p in st.session_state.get("programs", [])
                if p["program_name"] == selected_prog
            }
            current_components = [
                c["component_no"] for c in st.session_state.get("program_components", [])
                if str(c["program_id"]) in prog_ids
            ]
            if st.session_state.get("role", "工程师") != "只读":
                with st.expander("新增型号", expanded=False):
                    with st.form("pc_component_create_form", clear_on_submit=True, border=False):
                        new_comp = st.text_input("型号 / 组件号", key="pc_new_component")
                        if st.form_submit_button("添加型号"):
                            clean = str(new_comp or "").strip()
                            if not clean:
                                st.error("型号不能为空")
                            elif clean in current_components:
                                st.error("该型号已关联")
                            else:
                                items = list(st.session_state.get("program_components", []))
                                for pid in prog_ids:
                                    items.append({"program_id": int(pid), "component_no": clean})
                                    break
                                st.session_state.program_components = items
                                _pc_save("program_components", items)
                                st.toast("已添加型号")
                                st.rerun()
            frame = pd.DataFrame({
                "型号 / 组件号": current_components,
                "删除": ["删除"] * len(current_components),
            }, columns=["型号 / 组件号", "删除"])
            _pc_component_names = current_components
            if st.session_state.get("role", "工程师") == "只读":
                st.dataframe(frame.drop(columns=["删除"]), hide_index=True, width="stretch", alt="型号关联列表")
            else:
                st.data_editor(
                    frame,
                    column_config={
                        "型号 / 组件号": st.column_config.TextColumn("型号 / 组件号", disabled=True),
                        "删除": st.column_config.ButtonColumn(
                            "删除", type="tertiary", on_click=_pc_request_component_delete,
                            key="pc_component_delete_click", width="small",
                        ),
                    },
                    hide_index=True, num_rows="fixed", width="stretch", alt="型号关联编辑器",
                    key="pc_component_editor",
                )
                pending = st.session_state.pop("pc_pending_component_delete", None)
                if pending:
                    items = [
                        c for c in st.session_state.get("program_components", [])
                        if not (str(c["program_id"]) in prog_ids and c["component_no"] == pending)
                    ]
                    st.session_state.program_components = items
                    _pc_save("program_components", items)
                    st.toast("已删除型号关联")
                    st.rerun()

    # -------------------------------------------------------------------------
    # 区块 7：设备读写记录
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("设备读写记录")
        tab_pull, tab_report = st.tabs(["设备拉取（拉取程序）", "设备上报（状态记录）"])
        with tab_pull:
            pulls = st.session_state.get("program_pulls", [])[:30]
            if pulls:
                st.dataframe(pd.DataFrame([{
                    "时间": str(p.get("pulled_at") or ""),
                    "设备": str(p.get("device_id") or ""),
                    "产品": str(p.get("product") or ""),
                    "程序版本": str(p.get("program_version") or ""),
                    "SHA256": (str(p.get("sha256") or ""))[:16],
                } for p in pulls]), hide_index=True, width="stretch", alt="设备拉取记录")
            else:
                st.caption("暂无拉取记录。")
        with tab_report:
            logs = st.session_state.get("program_status_logs", [])[:30]
            if logs:
                st.dataframe(pd.DataFrame([{
                    "时间": str(g.get("reported_at") or ""),
                    "设备": str(g.get("device_id") or ""),
                    "产品": str(g.get("product") or ""),
                    "上报版本": str(g.get("reported_version") or ""),
                    "可信": "是" if g.get("trusted") else "否",
                    "原因": str(g.get("reason") or ""),
                } for g in logs]), hide_index=True, width="stretch", alt="设备状态上报记录")
            else:
                st.caption("暂无上报记录。")


def _pc_save(key: str, rows: list) -> None:
    """生产版保存主数据；app_pages 版为 no-op。"""
    master.save_key(key)


def _pc_request_component_delete() -> None:
    click = st.session_state.get("pc_component_delete_click")
    if click is None:
        return
    row = int(click["row"])
    names = st.session_state.get("_pc_component_names", [])
    if 0 <= row < len(names):
        st.session_state["pc_pending_component_delete"] = names[row]
