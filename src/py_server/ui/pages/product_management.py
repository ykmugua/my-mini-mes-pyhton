"""组件注册页面：维护组件、工序流程与可选设备范围。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from . import registry_helpers as helpers
from .constants import (
    BLANK_TEMPLATE,
    COMPONENT_LIST_SECTION,
    CREATE_COMPONENT_BUTTON,
    CREATE_COMPONENT_SECTION,
    ENABLED_OPTIONS,
    SAVE_COMPONENT_BUTTON,
)

from ._mock_program_data import enabled_steps, step_label

PRODUCT_COLUMNS = [
    "组件号",
    "组件名称",
    "启用",
    "备注",
]
ROUTE_COLUMNS = ["当前工序", "成功下站", "失败下站"]
PRODUCT_DELETE_CLICK_KEY = "product_delete_click"
PENDING_PRODUCT_DELETE_KEY = "pending_product_delete"
ROUTE_DELETE_CLICK_KEY = "product_route_delete_click"
PENDING_ROUTE_DELETE_KEY = "pending_product_route_delete"
ROUTE_WARNING_KEY = "product_route_warning"


def _text(value: Any) -> str:
    """统一空值清洗。"""
    return helpers.clean_text(value)


def _integer(value: Any) -> int | None:
    """执行 integer。"""
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
    """执行 product_frame。"""
    records = [
        {
            "组件号": product["product_model"],
            "组件名称": product.get("product_name", ""),
            "启用": bool(product.get("enabled", True)),
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
    """执行 product_config。"""
    config: dict[str, Any] = {
        "组件号": st.column_config.TextColumn(
            "组件号", required=True, width="medium"
        ),
        "组件名称": st.column_config.TextColumn("组件名称", required=True, width="medium"),
        "启用": helpers.enabled_column(),
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
    """执行 validate_products。"""
    products: list[dict[str, Any]] = []
    models: set[str] = set()
    for row in rows:
        product_model = _text(row.get("组件号"))
        product_name = _text(row.get("组件名称"))
        remark = _text(row.get("备注"))
        if not any((product_model, product_name, remark)):
            continue
        if not product_model:
            return None, "组件号不能为空"
        if product_model.casefold() in models:
            return None, "组件号不能重复"
        models.add(product_model.casefold())
        products.append(
            {
                "product_model": product_model,
                "product_name": product_name,
                "enabled": (
                helpers.enabled_from_cell(row.get("启用"))
                ),
                "remark": remark,
            }
        )
    return products, None


def _request_product_delete() -> None:
    """记录待删除组件号。"""
    helpers.request_delete(
        PRODUCT_DELETE_CLICK_KEY, PENDING_PRODUCT_DELETE_KEY, "products", "product_model"
    )


def _clear_pending_product_delete() -> None:
    """执行 clear_pending_product_delete。"""
    helpers.clear_pending(PENDING_PRODUCT_DELETE_KEY)


@st.dialog(
    "确认删除组件",
    icon=":material/delete_forever:",
    on_dismiss=_clear_pending_product_delete,
)
def _confirm_delete_product(product: dict[str, Any]) -> None:
    """执行 confirm_delete_product。"""
    st.write(
        f"确定删除组件 **{product['product_model']} - "
        f"{product.get('product_name', '')}** 吗？"
    )
    st.caption("删除组件将同时删除其工序流程和设备分配。")
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
            _clear_pending_product_delete()
            st.toast("组件已删除")
            st.rerun()


def render_page() -> None:
    """页面渲染入口（app_pages 脚本包装）。"""
    master.ensure_master_data()
    read_only = not helpers.is_editable()
    steps: list[dict[str, Any]] = st.session_state.steps
    active_steps = enabled_steps(steps)
    devices: list[dict[str, Any]] = st.session_state.devices
    products: list[dict[str, Any]] = st.session_state.products
    trays: list[dict[str, Any]] = st.session_state.get("trays", [])
    product_trays: list[dict[str, Any]] = st.session_state.get("product_trays", [])

    # -----------------------------------------------------------------------------
    # 区块 1：新增组件
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("组件管理")
        if read_only:
            with st.expander(CREATE_COMPONENT_SECTION, expanded=False):
                st.info("只读角色不可新增组件。")
        else:
            with st.expander(CREATE_COMPONENT_SECTION, expanded=False):
                with st.form("product_create_form", clear_on_submit=False, border=False):
                    # 第一行：组件名称 + 组件号 + 从原有模板中新建
                    name_col, model_col, template_col = st.columns([1, 1, 1])
                    product_name = name_col.text_input(
                        "组件名称",
                        key="new_product_name",
                        placeholder="例如 电源模块",
                    )
                    product_model = model_col.text_input(
                        "组件号",
                        key="new_product_model",
                        placeholder="例如 P-1003",
                    )
                    source = template_col.selectbox(
                        "从原有模板中新建",
                        options=[BLANK_TEMPLATE, *[str(p["product_model"]) for p in products]],
                        key="new_product_template",
                    )
                    # 第二行：备注 + 启用（下拉）
                    remark_col, enabled_col = st.columns([3, 1])
                    remark = remark_col.text_input(
                        "备注",
                        key="new_product_remark",
                        placeholder="可选",
                    )
                    enabled_text = enabled_col.selectbox(
                        "启用", options=list(ENABLED_OPTIONS), key="new_product_enabled_text",
                    )
                    # 第三行：添加按钮
                    submitted = st.form_submit_button(CREATE_COMPONENT_BUTTON)

                if submitted:
                    if source != BLANK_TEMPLATE:
                        row = next(p for p in products if str(p["product_model"]) == source)
                        new_model = helpers.copy_value(source, {str(p["product_model"]) for p in products})
                        new_row = {
                            **row,
                            "product_model": new_model,
                            "product_name": f"{row.get('product_name', '')} 副本",
                        }
                        proposed_products = [*products, new_row]
                        success_message = f"已从模板 {source} 新建组件 {new_model}"
                    else:
                        clean_model = product_model.strip()
                        if not clean_model:
                            st.error("组件不能为空")
                            return
                        if any(
                            item["product_model"].casefold() == clean_model.casefold()
                            for item in products
                        ):
                            st.error("组件号不能重复")
                            return
                        proposed_products = [
                            *products,
                            {
                                "product_model": clean_model,
                                "product_name": product_name.strip(),
                                "enabled": helpers.enabled_from_text(enabled_text),
                                "remark": remark.strip(),
                            },
                        ]
                        success_message = "组件已添加"
                    validated, error = _validate_products(
                        _product_frame(proposed_products, include_delete=False).to_dict("records")
                    )
                    if error:
                        st.error(error)
                    else:
                        helpers.save_rows("products", validated or [], success_message)


    # -----------------------------------------------------------------------------
    # 区块 2：组件列表
    # -----------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader(COMPONENT_LIST_SECTION)
        edited_products: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _product_frame(products, include_delete=False),
                column_config=_product_config(include_delete=False),
                hide_index=True,
                width="stretch",
                alt="组件列表",
            )
        else:
            edited_products = st.data_editor(
                _product_frame(products, include_delete=True),
                column_config=_product_config(include_delete=True),
                disabled=["组件号"],
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                alt="组件列表编辑器",
                key="product_editor",
            )

        save_products_clicked = False
        if not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                save_products_clicked = st.button(
                    SAVE_COMPONENT_BUTTON,
                    icon=":material/save:",
                    key="save_products",
                )

        if not products:
            st.info("暂无组件，请新增")

        if save_products_clicked and edited_products is not None:
            updated_products, error = _validate_products(
                edited_products.to_dict("records")
            )
            if error:
                st.error(error)
            else:
                helpers.save_rows("products", updated_products or [], "组件已保存")

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
