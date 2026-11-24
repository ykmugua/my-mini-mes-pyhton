"""页面：开放性变量（三层结构；风格与前四个主数据页面一致）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import client, common
from .client import ApiError as ServiceError

VARIABLE_TYPES = ["int", "float", "str", "bool"]
DELETE_CLICK_KEY = "var_delete_click"
PENDING_DELETE_KEY = "pending_var_delete"


def _variable_frame(variables: list[dict], *, include_delete: bool) -> pd.DataFrame:
    """执行 variable_frame。"""
    records = []
    for item in variables:
        records.append({
            "变量名": item["name"],
            "类型": item["type"],
            "当前值": "" if item["value"] is None else str(item["value"]),
            "更新时间": common.local_time(item.get("updated_at")),
        })
    columns = ["变量名", "类型", "当前值", "更新时间"]
    if include_delete:
        for record in records:
            record["删除"] = "删除"
        columns.append("删除")
    return pd.DataFrame(records, columns=columns)


def _variable_config(*, include_delete: bool) -> dict:
    """执行 variable_config。"""
    config = {
        "变量名": st.column_config.TextColumn("变量名", required=True, width="large"),
        "类型": st.column_config.SelectboxColumn("类型", options=VARIABLE_TYPES, required=True, width="small"),
        "当前值": st.column_config.TextColumn("当前值", width="medium"),
        "更新时间": st.column_config.TextColumn("更新时间", width="medium"),
    }
    if include_delete:
        config["删除"] = st.column_config.ButtonColumn(
            "删除", type="tertiary", on_click=_request_delete,
            key=DELETE_CLICK_KEY, width="small",
        )
    return config


def _request_delete() -> None:
    """执行 request_delete。"""
    click = st.session_state.get(DELETE_CLICK_KEY)
    if click is None:
        return
    names = st.session_state.get("_var_names", [])
    row = int(click["row"])
    if 0 <= row < len(names):
        st.session_state[PENDING_DELETE_KEY] = names[row]


def _clear_pending_delete() -> None:
    """执行 clear_pending_delete。"""
    st.session_state.pop(PENDING_DELETE_KEY, None)


@st.dialog("确认删除变量", icon=":material/delete_forever:", on_dismiss=_clear_pending_delete)
def _confirm_delete(name: str) -> None:
    """执行 confirm_delete。"""
    st.write(f"确定删除变量 **{name}** 吗？")
    st.caption("删除后设备将无法再读写该变量，操作不可撤销。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_var"):
            _clear_pending_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_var"):
            try:
                client.delete_variable(name)
            except ServiceError as exc:
                st.error(str(exc))
            else:
                st.toast("变量已删除")
                _clear_pending_delete()
                st.rerun()


def _level_inputs(prefix: str, editable: bool, l1="", l2="", l3=""):
    """执行 level_inputs。"""
    a, b, c = st.columns(3)
    return (
        a.text_input("第一层（组名）", value=l1, key=f"{prefix}_l1",
                     placeholder="例如 line1 / zoneA", disabled=not editable),
        b.text_input("第二层（子组）", value=l2, key=f"{prefix}_l2",
                     placeholder="例如 status", disabled=not editable),
        c.text_input("第三层（键）", value=l3, key=f"{prefix}_l3",
                     placeholder="例如 ready", disabled=not editable),
    )


def _build_name(l1, l2, l3) -> str:
    """执行 build_name。"""
    return ".".join(part.strip() for part in (l1, l2, l3) if part and part.strip())


def _render_add_form(editable: bool) -> None:
    """执行 render_add_form。"""
    if not editable:
        st.info("只读角色不可新增变量。")
        return
    with st.form("var_create_form", clear_on_submit=False, border=False):
        l1, l2, l3 = _level_inputs("new_var", True)
        c1, c2 = st.columns(2)
        type_name = c1.selectbox("类型", VARIABLE_TYPES, key="new_var_type")
        value = c2.text_input("初始值", key="new_var_value",
                              help="int 填整数；float 填小数；bool 填 true/false；str 填文本")
        submitted = st.form_submit_button("新增变量", type="primary")
    name = _build_name(l1, l2, l3)
    if name:
        st.caption(f"将创建：`{name}`")
    if submitted:
        if not name:
            st.error("至少填写第一层组名")
        else:
            try:
                client.add_variable(name, type_name, value)
            except ServiceError as exc:
                st.error(str(exc))
            else:
                st.toast("变量已新增")
                st.rerun()


def _apply_edits(edited: pd.DataFrame, originals: list[dict]) -> None:
    """把 data_editor 的改动写回后端：改名/改类型/改值。"""
    changed = 0
    for i, row in enumerate(edited.to_dict("records")):
        if i >= len(originals):
            continue
        old = originals[i]
        old_name = old["name"]
        new_name = str(row.get("变量名") or "").strip()
        new_type = str(row.get("类型") or "str").strip()
        new_value = row.get("当前值")
        if not new_name:
            st.error(f"第 {i + 1} 行变量名为空，已跳过")
            continue
        # 比较是否需要更新（值统一按字符串比较）
        old_value = "" if old["value"] is None else str(old["value"])
        value_changed = ("" if new_value is None else str(new_value)) != old_value
        if new_name == old_name and new_type == old["type"] and not value_changed:
            continue
        try:
            if new_name != old_name:
                client.rename_variable(old_name, new_name)
            if new_type != old["type"] or value_changed:
                client.update_variable_def(
                    new_name, type_name=new_type,
                    value=new_value if str(new_value).strip() != "" else None,
                )
            changed += 1
        except ServiceError as exc:
            st.error(f"{old_name} 保存失败：{exc}")
    if changed:
        st.toast(f"已保存 {changed} 个变量的修改")
        st.rerun()


def _render_list(editable: bool) -> None:
    """执行 render_list。"""
    variables, error = client.list_variables()
    common.show_error(error)
    variables = variables or []
    st.session_state["_var_names"] = [v["name"] for v in variables]
    if not variables:
        st.info("暂无变量，请在上方新增")
        return

    if editable:
        edited = st.data_editor(
            _variable_frame(variables, include_delete=True),
            column_config=_variable_config(include_delete=True),
            disabled=["更新时间"],
            hide_index=True, num_rows="fixed", width="stretch",
            alt="变量列表", key="var_editor",
        )
        if st.button("保存修改", icon=":material/save:", type="primary", key="save_vars"):
            _apply_edits(edited, variables)
    else:
        st.dataframe(
            _variable_frame(variables, include_delete=False),
            column_config=_variable_config(include_delete=False),
            hide_index=True, width="stretch", alt="变量列表",
        )

    pending = st.session_state.get(PENDING_DELETE_KEY)
    if pending:
        _confirm_delete(pending)



def _log_frame(records: list[dict], action: str) -> pd.DataFrame:
    """执行 log_frame。"""
    rows = []
    for item in records:
        rows.append({
            "时间": common.local_time(item.get("logged_at")),
            "设备": item.get("device_id") or "",
            "变量名": item.get("name") or "",
            ("写入值" if action == "WRITE" else "读取值"): (
                "" if item.get("value") is None else str(item["value"])
            ),
        })
    return pd.DataFrame(rows, columns=["时间", "设备", "变量名", "写入值" if action == "WRITE" else "读取值"])


def _render_device_logs() -> None:
    """执行 render_device_logs。"""
    st.subheader("设备读写记录")
    tab_r, tab_w = st.tabs(["设备读取（拉取）", "设备写入（上报）"])
    with tab_r:
        logs = client.variable_logs("read", 30)
        if logs:
            st.dataframe(_log_frame(logs, "READ"), hide_index=True, width="stretch", alt="设备读取记录")
        else:
            st.caption("暂无读取记录。")
    with tab_w:
        logs = client.variable_logs("write", 30)
        if logs:
            st.dataframe(_log_frame(logs, "WRITE"), hide_index=True, width="stretch", alt="设备写入记录")
        else:
            st.caption("暂无写入记录。")


def render() -> None:
    """执行 render。"""
    st.title("🔧 开放性变量")
    st.caption("最多三层的组/子组/键结构；支持在列表中直接编辑；设备按完整路径读写。")
    common.render_flash()
    common.render_readonly_notice()
    editable = common.can_edit()

    with st.container(border=True):
        st.subheader("新增变量")
        _render_add_form(editable)

    with st.container(border=True):
        st.subheader("变量列表（可直接修改变量名/类型/当前值，改完点“保存修改”）")
        _render_list(editable)

    with st.container(border=True):
        tab_tree, tab_api = st.tabs(["变量层级视图（JSON）", "接口示例"])
        with tab_tree:
            tree, terr = client.variables_tree()
            common.show_error(terr)
            st.json(tree or {})
        with tab_api:
            base = common.api_base()
            st.code(
                "# Read nested variable\n"
                f'curl "{base}/api/variable/line1.status.ready?device_id=TEST-01"\n\n'
                "# Write variable\n"
                f'curl -X POST "{base}/api/variable/line1.status.ready" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                '  -d \'{"value": "true"}\'\n',
                language="bash",
            )

    with st.container(border=True):
        _render_device_logs()
