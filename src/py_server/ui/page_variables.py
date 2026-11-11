"""页面：开放性变量区域。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import services
from ..services import ServiceError
from . import common

VARIABLE_TYPES = ["str", "int", "bool"]


def _variable_frame(variables: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "变量名": item["name"],
                "类型": item["type"],
                "当前值": "" if item["value"] is None else str(item["value"]),
                "最后写入设备": item.get("last_device") or "",
                "更新时间": common.local_time(item.get("updated_at")),
            }
            for item in variables
        ],
        columns=["变量名", "类型", "当前值", "最后写入设备", "更新时间"],
    )


def _render_add_form() -> None:
    st.subheader("新增变量")
    st.caption(
        "变量名不能为空、不能重复，只能包含英文字母、数字、下划线、点和短横线"
        "（因为设备通过 URL 路径读写变量）；类型支持 int / str / bool。"
    )
    with st.form("add_variable", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input(
            "变量名",
            key="new_var_name",
            placeholder="例如 line_2_ready",
            help="以字母或下划线开头，例如 line_mode / station2.ready",
            disabled=not common.can_edit(),
        )
        type_name = col2.selectbox(
            "类型", VARIABLE_TYPES, key="new_var_type", disabled=not common.can_edit()
        )
        value = col3.text_input(
            "初始值",
            key="new_var_value",
            help="int 填整数（如 100）；bool 填 true/false；str 直接填文本",
            disabled=not common.can_edit(),
        )
        submitted = st.form_submit_button(
            "新增变量", type="primary", disabled=not common.can_edit()
        )
    if not submitted:
        return
    try:
        created = services.add_variable(name, type_name, value)
    except ServiceError as exc:
        st.error(str(exc))
    else:
        common.flash(
            "success",
            f"变量 {created['name']} 已创建，当前值 {created['value']!r}。设备可立即通过接口读取。",
        )
        st.rerun()


def _render_api_help() -> None:
    base = common.api_base()
    with st.expander("变量读写接口示例"):
        st.code(
            f"""# 读取变量
curl "{base}/api/variable/line_mode"

# 写入变量（记录写入设备和时间）
curl -X POST "{base}/api/variable/line_mode" \\
  -H "Content-Type: application/json" \\
  -d '{{"value": "MANUAL", "device_id": "TEST-02"}}'
""",
            language="bash",
        )
        st.caption(
            "典型用法：设备 A 写入结果变量，设备 B 读取该变量决定是否启动；"
            "增线时只新增变量，不需要修改已有设备程序。"
        )


def render() -> None:
    st.title("🔧 开放性变量")
    st.caption("机台间数据交换与增线控制：变量定义、读写接口、当前值查看。每 30 秒自动刷新。")
    common.render_flash()
    common.render_readonly_notice()

    prefix = st.text_input(
        "变量名前缀筛选",
        key="var_prefix",
        placeholder="例如 line_",
        help="按变量名开头匹配，留空显示全部",
    )

    @st.fragment(run_every=30)
    def live() -> None:
        variables = services.list_variables(prefix)
        if variables:
            st.dataframe(_variable_frame(variables), hide_index=True, width="stretch")
        else:
            st.info("没有匹配的变量。")
        st.caption(f"共 {len(variables)} 个变量 · 每 30 秒自动刷新 · 数据截至 {common.now_text()}")

    live()
    st.divider()
    _render_add_form()
    st.divider()
    _render_api_help()
