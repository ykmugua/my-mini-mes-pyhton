"""Streamlit 页面公共组件：侧边栏、权限、提示消息。"""

from __future__ import annotations

import streamlit as st

from .. import config
from . import client
ROLE_EDIT = "工程师（可编辑）"
ROLE_VIEW = "只读"


def init_session() -> None:
    """执行 init_session。"""
    st.session_state.setdefault("mes_operator", "engineer")
    st.session_state.setdefault("mes_role", ROLE_EDIT)


def render_sidebar() -> None:
    """渲染sidebar。"""
    st.sidebar.markdown("## 🏭 旁路 MES")
    st.sidebar.caption("设备乙方内部轻量工具 · 不对接甲方 MES")
    st.sidebar.divider()
    st.sidebar.text_input("操作员", key="mes_operator", help="解锁等留痕操作会记录这个名字")
    st.sidebar.radio(
        "当前权限", options=[ROLE_EDIT, ROLE_VIEW], key="mes_role",
        help="初期只区分可编辑 / 只读两类角色，不做登录鉴权",
    )
    if can_edit():
        st.sidebar.success("可编辑：可以修改绑定、解锁、新增变量")
    else:
        st.sidebar.info("只读：仅浏览数据")
    st.sidebar.divider()
    st.sidebar.caption(f"接口服务：{config.ui_api_base()}")
    st.sidebar.caption(f"时区：{config.timezone().key}")


def can_edit() -> bool:
    """执行 can_edit。"""
    editable = st.session_state.get("mes_role", ROLE_EDIT) == ROLE_EDIT
    # 与 app_pages 页面的 role key 同步（工程师/只读）
    st.session_state["role"] = "工程师" if editable else "只读"
    return editable


def operator() -> str:
    """执行 operator。"""
    return str(st.session_state.get("mes_operator", "") or "").strip()


def render_readonly_notice() -> None:
    """渲染readonly_notice。"""
    if not can_edit():
        st.info("当前为只读模式（可在左侧切换为“工程师（可编辑）”）。")


def flash(kind: str, message: str) -> None:
    """执行 flash。"""
    st.session_state["mes_flash"] = (kind, message)


def render_flash() -> None:
    """渲染flash。"""
    item = st.session_state.pop("mes_flash", None)
    if not item:
        return
    kind, message = item
    getattr(st, kind, st.info)(message)


def local_time(value) -> str:
    """把 UTC ISO 时间转成本地展示（纯 Python，不访问数据库）。"""
    from datetime import datetime

    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.astimezone(config.timezone()).strftime("%Y-%m-%d %H:%M:%S")


def now_text() -> str:
    """执行 now_text。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone(config.timezone()).strftime("%Y-%m-%d %H:%M:%S")


def api_base() -> str:
    """执行 api_base。"""
    return config.api_public_base()


def show_error(error: str | None) -> None:
    """统一显示接口降级/失败提示。"""
    if error:
        st.error(f"⚠️ {error}（显示的是上次成功获取的数据）")


def service_error_message(exc: Exception) -> str:
    """执行 service_error_message。"""
    return str(exc)
