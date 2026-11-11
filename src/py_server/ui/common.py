"""Streamlit 页面公共组件：侧边栏、权限、提示消息。"""

from __future__ import annotations

import streamlit as st

from .. import config, db

ROLE_EDIT = "工程师（可编辑）"
ROLE_VIEW = "只读"


def init_session() -> None:
    st.session_state.setdefault("mes_operator", "engineer")
    st.session_state.setdefault("mes_role", ROLE_EDIT)


def render_sidebar() -> None:
    st.sidebar.markdown("## 🏭 旁路 MES")
    st.sidebar.caption("设备乙方内部轻量工具 · 不对接甲方 MES")
    st.sidebar.divider()
    st.sidebar.text_input(
        "操作员",
        key="mes_operator",
        help="解锁等留痕操作会记录这个名字",
    )
    st.sidebar.radio(
        "当前权限",
        options=[ROLE_EDIT, ROLE_VIEW],
        key="mes_role",
        help="初期只区分可编辑 / 只读两类角色，不做登录鉴权",
    )
    if can_edit():
        st.sidebar.success("可编辑：可以修改绑定、解锁、新增变量")
    else:
        st.sidebar.info("只读：仅浏览数据")
    st.sidebar.divider()
    st.sidebar.caption(f"接口服务：{config.api_public_base()}")
    st.sidebar.caption(f"时区：{config.timezone().key}")
    st.sidebar.caption(f"数据库：{config.db_path()}")


def can_edit() -> bool:
    return st.session_state.get("mes_role", ROLE_EDIT) == ROLE_EDIT


def operator() -> str:
    return str(st.session_state.get("mes_operator", "") or "").strip()


def render_readonly_notice() -> None:
    if not can_edit():
        st.info("当前为只读模式（可在左侧切换为“工程师（可编辑）”）。")


def flash(kind: str, message: str) -> None:
    """保存后跳转仍然可见的成功/错误提示。"""
    st.session_state["mes_flash"] = (kind, message)


def render_flash() -> None:
    item = st.session_state.pop("mes_flash", None)
    if not item:
        return
    kind, message = item
    getattr(st, kind, st.info)(message)


def local_time(value) -> str:
    return db.to_local_display(value)


def now_text() -> str:
    return db.utc_now().astimezone(config.timezone()).strftime("%Y-%m-%d %H:%M:%S")


def api_base() -> str:
    return config.api_public_base()
