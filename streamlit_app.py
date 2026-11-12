"""程序下发前端入口：使用 session state 中的占位数据，不连接后端。"""

from __future__ import annotations

import streamlit as st

from app_pages._mock_program_data import initialize_program_state

st.set_page_config(
    page_title="旁路式小型 MES · 程序下发",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize_program_state()
st.session_state.setdefault("role", "工程师")

with st.sidebar:
    st.markdown("## 旁路式小型 MES")
    st.caption("程序下发前端预览 · 暂未连接 FastAPI")
    st.divider()
    st.radio(
        "角色",
        ["工程师", "只读"],
        key="role",
        help="只读角色会禁用上传、编辑和保存操作。",
    )
    if st.session_state.role == "工程师":
        st.success("可编辑：可以上传程序并维护型号关联。")
    else:
        st.info("只读：仅允许查看程序和型号关联。")

page = st.navigation(
    [
        st.Page(
            "app_pages/program.py",
            title="程序下发",
            icon=":material/inventory_2:",
            help="上传压缩包、维护程序工序信息和型号关联。",
            default=True,
        )
    ],
    position="sidebar",
)

page.run()
