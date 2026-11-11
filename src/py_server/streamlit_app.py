"""Streamlit 页面入口（多页面用 st.navigation）。

启动::

    uv run streamlit run src/py_server/streamlit_app.py --server.address 0.0.0.0
"""

from __future__ import annotations

import streamlit as st

from py_server.ui import common
from py_server.ui.page_dashboard import render as render_dashboard
from py_server.ui.page_interlock import render as render_interlock
from py_server.ui.page_program import render as render_program
from py_server.ui.page_variables import render as render_variables

st.set_page_config(
    page_title="旁路 MES · 产线测试数据",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

common.init_session()
common.render_sidebar()

navigation = st.navigation(
    [
        st.Page(render_program, title="程序下发", icon="📦", url_path="program", default=True),
        st.Page(render_interlock, title="工序锁", icon="🔒", url_path="interlock"),
        st.Page(render_dashboard, title="测试数据看板", icon="📊", url_path="dashboard"),
        st.Page(render_variables, title="开放性变量", icon="🔧", url_path="variables"),
    ]
)
navigation.run()
