"""统一注册页面：用标签页承载程序/工序/设备/载具/组件注册。"""

from __future__ import annotations

import streamlit as st

from . import device_registration, needle_bed_registration, product_management, program, step_registration, tray_registration

TAB_KEY = "registration_hub_tabs"
TAB_LABELS = ["程序注册", "工序注册", "设备注册", "载具注册", "针床注册", "组件注册"]
PAGE_TITLE = "注册配置"


def render_page() -> None:
    """统一注册配置入口。"""
    st.title(PAGE_TITLE)
    tabs = st.tabs(TAB_LABELS, key=TAB_KEY, on_change="rerun")
    for tab, label in zip(tabs, TAB_LABELS):
        if not tab.open:
            continue
        with tab:
            if label == "程序注册":
                program.render_page()
            elif label == "工序注册":
                step_registration.render_page()
            elif label == "设备注册":
                device_registration.render_page()
            elif label == "载具注册":
                tray_registration.render_page()
            elif label == "针床注册":
                needle_bed_registration.render_page()
            else:
                product_management.render_page()
