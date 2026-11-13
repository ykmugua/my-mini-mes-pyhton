"""程序下发前端入口：使用 session state 中的占位数据，不连接后端。"""

from __future__ import annotations

import streamlit as st

from app_pages._mock_program_data import initialize_program_state

st.set_page_config(
    page_title="旁路式小型 MES",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_program_state()
st.session_state.setdefault("role", "工程师")

with st.sidebar:
    st.markdown("## 旁路式小型 MES")
    st.caption("轻量 MES 前端预览 · 暂未连接 FastAPI")
    st.divider()
    st.radio(
        "角色",
        ["工程师", "只读"],
        key="role",
        help="只读角色会禁用上传、编辑和保存操作。",
    )
    if st.session_state.role == "工程师":
        st.success("可编辑：可以维护程序、工序、设备、产品和型号关联。")
    else:
        st.info("只读：仅允许查看程序、工序、设备、产品和型号关联。")

page = st.navigation(
    [
        st.Page(
            "app_pages/program.py",
            title="程序下发",
            icon=":material/inventory_2:",
            help="上传压缩包、维护程序工序信息和型号关联。",
            default=True,
        ),
        st.Page(
            "app_pages/step_registration.py",
            title="工序注册",
            icon=":material/route:",
            help="维护全厂工序清单、启停状态和现场备注。",
        ),
        st.Page(
            "app_pages/device_registration.py",
            title="设备注册",
            icon=":material/devices:",
            help="维护设备编号、名称、所属工序、启停状态和现场备注。",
        ),
        st.Page(
            "app_pages/product_management.py",
            title="产品管理",
            icon=":material/inventory:",
            help="维护产品信息、产品工序流程和每道工序可使用的设备范围。",
        ),
    ],
    position="sidebar",
)

page.run()
