"""Streamlit 页面入口（st.navigation）。

6 个页面：程序注册 / 工序注册 / 设备注册 / 产品型号注册（app_pages 接入，数据走 HTTP）
+ 测试数据看板 / 开放性变量（原有页面）。
"""

from __future__ import annotations

import streamlit as st

from py_server.ui import common
from py_server.ui.page_dashboard import render as render_dashboard
from py_server.ui.page_variables import render as render_variables
from py_server.ui.page_product_query import render as render_product_query
from py_server.ui.pages import device_registration, tray_registration, product_management, process_config, program, step_registration

st.set_page_config(
    page_title="旁路 MES · 产线测试数据",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

common.init_session()
# app_pages 页面使用 st.session_state.role（工程师/只读）
st.session_state.setdefault("role", "工程师")
common.render_sidebar()

navigation = st.navigation(
    [
        st.Page(render_dashboard, title="测试数据看板", icon="📊", url_path="dashboard", default=True),
        st.Page(render_product_query, title="产品查询", icon="🔎", url_path="product_query"),
        st.Page(program.render_page, title="程序注册", icon="📦", url_path="program"),
        st.Page(step_registration.render_page, title="工序注册", icon="🧱", url_path="steps"),
        st.Page(device_registration.render_page, title="设备注册", icon="🔧", url_path="devices"),
        st.Page(tray_registration.render_page, title="载具注册", icon="📦", url_path="trays"),
        st.Page(product_management.render_page, title="组件注册", icon="🏷️", url_path="products"),
        st.Page(process_config.render_page, title="工艺配置", icon="⚙️", url_path="process_config"),
        st.Page(render_variables, title="开放性变量", icon="🔧", url_path="variables"),
    ]
)
navigation.run()