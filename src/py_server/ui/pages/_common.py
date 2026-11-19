"""app_pages 适配层：把 session_state 主数据读写代理到 HTTP 接口。

页面文件仍使用 st.session_state.steps / devices / ... 的写法，
但首次加载时从 FastAPI 拉取，保存时通过 client.master_save 写回。
"""

from __future__ import annotations

import streamlit as st

from .. import client

MASTER_KEYS = (
    "steps", "lines", "devices", "trays", "programs", "program_versions",
    "program_components", "products", "product_routes", "product_step_devices",
)
# 每个页面只需要自己关心的 key，但 init 时一次性拉全量，避免多次请求
_INIT_FLAG = "_master_data_loaded"


def ensure_master_data() -> bool:
    """首次进入页面时从 HTTP 加载主数据到 session_state。

    返回是否加载成功；失败时保留已有 session_state（降级）。
    """
    if st.session_state.get(_INIT_FLAG):
        return True
    data, error = client.master_snapshot()
    if error or data is None:
        # 降级：使用页面内已有的占位初始化（若页面自己调用了 initialize_program_state）
        if error:
            st.error(f"⚠️ {error}（主数据可能不是最新）")
        return False
    for key in MASTER_KEYS:
        if key in data:
            st.session_state[key] = data[key]
    # 程序页面的日志列表走已有接口
    pulls, _ = client.list_program_pulls(30)
    logs, _ = client.list_program_status_logs(30)
    st.session_state["program_pulls"] = pulls or []
    st.session_state["program_status_logs"] = logs or []
    st.session_state[_INIT_FLAG] = True
    return True


def save_key(key: str) -> bool:
    """把 st.session_state[key] 保存到后端。成功返回 True。"""
    rows = st.session_state.get(key, [])
    try:
        client.master_save(key, rows)
    except client.ApiError as exc:
        st.error(f"保存失败：{exc}")
        return False
    return True


def reload_key(key: str) -> None:
    """从后端重新拉取某个 key，覆盖 session_state。"""
    try:
        st.session_state[key] = client.master_list(key)
    except client.ApiError as exc:
        st.error(f"刷新失败：{exc}")