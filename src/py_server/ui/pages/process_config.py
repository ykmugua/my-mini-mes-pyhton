"""工艺配置页面：新增（可从模板新建）/ 工艺列表 / 工艺详情。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from ._mock_program_data import enabled_steps
from .constants import (
    CREATE_PROCESS_BUTTON,
    CREATE_PROCESS_SECTION,
    PAGE_TITLE_PROCESS_CONFIG,
    PROCESS_LIST_SECTION,
    SAVE_PROCESS_BUTTON,
)


def _text(value: Any) -> str:
    """执行 text。"""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    t = str(value).strip()
    return "" if t.lower() in {"nan", "none", "nat"} else t


def _split(value: Any) -> list[str]:
    """执行 split。"""
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def _join(items: Any) -> str:
    """执行 join。"""
    if items is None:
        return ""
    if isinstance(items, str):
        return items
    return ",".join(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))


def _save(key: str, rows: list[dict[str, Any]]) -> None:
    """执行 save。"""
    st.session_state[key] = rows
    master.save_key(key)


def _request_process_delete() -> None:
    """执行 request_process_delete。"""
    click = st.session_state.get("process_delete_click")
    if click is None:
        return
    row = int(click["row"])
    codes = st.session_state.get("_process_codes", [])
    if 0 <= row < len(codes):
        st.session_state["pending_process_delete"] = codes[row]


def _request_route_delete() -> None:
    """执行 request_route_delete。"""
    click = st.session_state.get("route_delete_click")
    if click is None:
        return
    row = int(click["row"])
    selected = st.session_state.get("process_selected")
    if not selected:
        return
    cur = [r for r in st.session_state.get("process_routes", []) if r["process_code"] == selected]
    if 0 <= row < len(cur):
        st.session_state["pending_route_delete"] = {
            "process_code": selected,
            "step_no": str(cur[row]["step_no"]),
        }


def _request_resource_delete() -> None:
    """执行 request_resource_delete。"""
    click = st.session_state.get("res_delete_click")
    if click is None:
        return
    row = int(click["row"])
    selected = st.session_state.get("process_selected")
    if not selected:
        return
    cur = [r for r in st.session_state.get("process_step_resources", []) if r["process_code"] == selected]
    if 0 <= row < len(cur):
        st.session_state["pending_resource_delete"] = {
            "process_code": selected,
            "step_no": str(cur[row]["step_no"]),
        }


def render_page() -> None:
    """渲染page。"""
    master.ensure_master_data()
    read_only = st.session_state.get("role", "工程师") == "只读"
    processes: list[dict[str, Any]] = st.session_state.get("processes", [])
    routes: list[dict[str, Any]] = st.session_state.get("process_routes", [])
    resources: list[dict[str, Any]] = st.session_state.get("process_step_resources", [])
    products: list[dict[str, Any]] = st.session_state.get("products", [])
    steps: list[dict[str, Any]] = st.session_state.steps
    active_steps = enabled_steps(steps)
    programs: list[dict[str, Any]] = st.session_state.get("programs", [])
    devices: list[dict[str, Any]] = st.session_state.get("devices", [])
    trays: list[dict[str, Any]] = st.session_state.get("trays", [])

    program_names = sorted({str(p["program_name"]) for p in programs})
    device_models = sorted({str(d.get("device_model", "")) for d in devices if d.get("device_model")})
    tray_models = sorted({str(t.get("tray_model", "")) for t in trays if t.get("tray_model")})
    step_nos = [str(s["step_no"]) for s in active_steps]
    component_options = [""] + [str(q["product_model"]) for q in products]

    st.title(PAGE_TITLE_PROCESS_CONFIG)

    # -------------------------------------------------------------------------
    # 区块 1：新增工艺（空白 / 从原有模板中新建）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader(CREATE_PROCESS_SECTION)
        if read_only:
            st.info("只读角色不可新增工艺。")
        else:
            with st.form("process_create_form", clear_on_submit=False, border=False):
                c1, c2, c3 = st.columns(3)
                new_code = c1.text_input("工艺号", key="new_process_code", placeholder="例如 PROC-003")
                new_name = c2.text_input("工艺名称", key="new_process_name", placeholder="例如 电源板工艺B")
                source = c3.selectbox(
                    "从原有模板中新建", options=["空白新增"] + [p["process_code"] for p in processes],
                    key="new_process_source",
                )
                c4, c5, c6 = st.columns([2, 2, 1])
                new_remark = c4.text_input("备注", key="new_process_remark", placeholder="可选")
                new_component = c5.selectbox("绑定组件", options=component_options, key="new_process_component")
                enabled_text = c6.selectbox("启用", options=["是", "否"], key="new_process_enabled")
                submitted = st.form_submit_button(CREATE_PROCESS_BUTTON)
            if submitted:
                code = new_code.strip()
                if not code:
                    st.error("工艺号不能为空")
                elif any(p["process_code"] == code for p in processes):
                    st.error("工艺号已存在")
                else:
                    template_process = next((p for p in processes if p["process_code"] == source), None) if source != "空白新增" else None
                    filled = {
                        "工艺号": code,
                        "工艺名称": new_name.strip(),
                        "启用": enabled_text == "是",
                        "备注": new_remark.strip(),
                        "绑定组件": new_component,
                    }
                    if template_process:
                        template_values = {
                            "工艺号": "",
                            "工艺名称": template_process.get("process_name", ""),
                            "启用": bool(template_process.get("enabled", True)),
                            "备注": template_process.get("remark", ""),
                            "绑定组件": template_process.get("component_no", ""),
                        }
                        from . import registry_helpers as helpers

                        filled = helpers.fill_missing_text_values(filled, template_values)
                    new_processes = list(processes) + [{
                        "process_code": filled["工艺号"],
                        "process_name": filled["工艺名称"] or filled["工艺号"],
                        "enabled": bool(filled["启用"]),
                        "remark": filled["备注"],
                        "component_no": filled["绑定组件"],
                    }]
                    new_routes = list(routes)
                    new_resources = list(resources)
                    if source != "空白新增":
                        new_routes += [{**r, "process_code": code} for r in routes if r["process_code"] == source]
                        new_resources += [{**r, "process_code": code} for r in resources if r["process_code"] == source]
                    _save("processes", new_processes)
                    _save("process_routes", new_routes)
                    _save("process_step_resources", new_resources)
                    st.toast(f"工艺 {code} 已新增" + (f"（从原有模板 {source} 新建）" if source != "空白新增" else ""))
                    st.rerun()

    # -------------------------------------------------------------------------
    # 区块 2：工艺列表（前面勾选框 + 可直接改 + 启用勾选框 + 删除按钮）
    # -------------------------------------------------------------------------
    with st.container(border=True, key="process_list_panel"):
        st.subheader(PROCESS_LIST_SECTION)
        codes = [p["process_code"] for p in processes]
        st.session_state["_process_codes"] = codes
        frame = pd.DataFrame([{
            "选择": p["process_code"] == st.session_state.get("process_selected"),
            "工艺号": p["process_code"],
            "工艺名称": p.get("process_name", ""),
            "启用": bool(p.get("enabled", True)),
            "绑定组件": p.get("component_no", ""),
            "备注": p.get("remark", ""),
            "删除": "删除",
        } for p in processes], columns=["选择", "工艺号", "工艺名称", "绑定组件", "启用", "备注", "删除"])
        config = {
            "选择": st.column_config.CheckboxColumn("选择", default=False, width="small",
                                                   help="勾选后在下方查看该工艺详情"),
            "工艺号": st.column_config.TextColumn("工艺号", required=True, width="medium"),
            "工艺名称": st.column_config.TextColumn("工艺名称", required=True, width="medium"),
            "启用": st.column_config.CheckboxColumn("启用", default=True, width="small"),
            "绑定组件": st.column_config.SelectboxColumn("绑定组件", options=component_options, width="medium"),
            "备注": st.column_config.TextColumn("备注", width="large"),
            "删除": st.column_config.ButtonColumn(
                "删除", type="tertiary", on_click=_request_process_delete,
                key="process_delete_click", width="small",
            ),
        }
        edited: pd.DataFrame | None = None
        if read_only:
            st.dataframe(frame.drop(columns=["删除"]), column_config=config, hide_index=True,
                         width="stretch", alt="工艺列表")
        else:
            edited = st.data_editor(
                frame, column_config=config, hide_index=True, num_rows="fixed",
                width="stretch", alt="工艺列表编辑器", key="process_editor",
                on_change=_on_process_editor_change,
            )
            # 前面的勾选框驱动详情
            checked = [str(row["工艺号"]) for _, row in edited.iterrows() if bool(row.get("选择"))]
            cur = st.session_state.get("process_selected")
            if checked and cur != checked[0]:
                st.session_state["process_selected"] = checked[0]
                st.rerun()
            elif not checked and cur:
                st.session_state.pop("process_selected", None)
                st.rerun()

        save_clicked = False
        if not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                save_clicked = st.button(SAVE_PROCESS_BUTTON, icon=":material/save:", key="save_processes")
        if not processes:
            st.info("暂无工艺，请新增")
        if save_clicked and edited is not None:
            new_processes, err = [], None
            seen = set()
            for index, row in edited.iterrows():
                code = _text(row["工艺号"])
                if not code:
                    continue
                if code in seen:
                    err = "工艺号不能重复"
                    break
                seen.add(code)
                original = processes[index]
                new_processes.append({
                    "process_code": code, "process_name": _text(row["工艺名称"]),
                    "enabled": bool(row["启用"]), "remark": _text(row["备注"]),
                    "component_no": _text(row["绑定组件"]),
                })
            if err:
                st.error(err)
            else:
                _save("processes", new_processes)
                st.toast("工艺已保存")
                st.rerun()
        pending = st.session_state.get("pending_process_delete")
        if pending:
            target = next((x for x in processes if x["process_code"] == pending), None)
            if target is None:
                _clear_pending_process_delete()
            else:
                _confirm_delete_process(target)

    # -------------------------------------------------------------------------
    # 区块 3：工艺详情（勾选工艺列表后显示）
    # -------------------------------------------------------------------------
    selected = st.session_state.get("process_selected")
    if selected and selected in codes:
        with st.container(border=True):
            st.subheader(f"工艺详情：{selected}")
            cur_routes = [r for r in routes if r["process_code"] == selected]

            # 3.1 工序路线（删除按钮）
            st.markdown("**工序路线**")
            route_frame = pd.DataFrame([{
                "工序号": r["step_no"], "成功下站": r["success_next_step"],
                "失败下站": r["fail_next_step"], "删除": "删除",
            } for r in cur_routes], columns=["工序号", "成功下站", "失败下站", "删除"])
            next_opts = step_nos + ["END", "LOCK"]
            edited_routes = st.data_editor(
                route_frame, hide_index=True, num_rows="dynamic", width="stretch",
                alt="工序路线编辑器", key=f"route_editor_{selected}",
                column_config={
                    "工序号": st.column_config.SelectboxColumn("工序号", options=step_nos, required=True),
                    "成功下站": st.column_config.SelectboxColumn("成功下站", options=next_opts, required=True),
                    "失败下站": st.column_config.SelectboxColumn("失败下站", options=next_opts, required=True),
                    "删除": st.column_config.ButtonColumn(
                        "删除", type="tertiary", on_click=_request_route_delete,
                        key="route_delete_click", width="small",
                    ),
                },
            )
            if not read_only and st.button("保存工序路线", key="save_process_routes"):
                new_r = [
                    {"process_code": selected, "step_no": str(row["工序号"]),
                     "success_next_step": str(row["成功下站"]), "fail_next_step": str(row["失败下站"])}
                    for _, row in edited_routes.iterrows() if _text(row["工序号"])
                ]
                others = [r for r in routes if r["process_code"] != selected]
                _save("process_routes", others + new_r)
                st.toast("工序路线已保存")
                st.rerun()

            # 3.2 工序资源（删除按钮）
            st.markdown("**工序资源**")
            res_by_step = {str(r["step_no"]): r for r in resources if r["process_code"] == selected}
            needle_bed_models = sorted({
                str(r.get("needle_bed_model") or "")
                for r in st.session_state.get("needle_beds", [])
                if str(r.get("needle_bed_model") or "")
            })
            resource_frame = pd.DataFrame([{
                "工序": str(r["step_no"]),
                "程序": res_by_step.get(str(r["step_no"]), {}).get("program_name", ""),
                "可执行设备型号": _split(res_by_step.get(str(r["step_no"]), {}).get("device_models", "")),
                "测试针床型号": _split(res_by_step.get(str(r["step_no"]), {}).get("needle_bed_models", "")),
                "转运载具型号": _split(res_by_step.get(str(r["step_no"]), {}).get("tray_models", "")),
                "删除": "删除",
            } for r in cur_routes], columns=["工序", "程序", "可执行设备型号", "测试针床型号", "转运载具型号", "删除"])
            edited_res = st.data_editor(
                resource_frame, hide_index=True, num_rows="fixed", width="stretch",
                alt="工序资源编辑器", key=f"res_editor_{selected}",
                column_config={
                    "工序": st.column_config.TextColumn("工序", disabled=True),
                    "程序": st.column_config.SelectboxColumn("程序", options=program_names),
                    "可执行设备型号": st.column_config.MultiselectColumn("可执行设备型号", options=device_models),
                    "测试针床型号": st.column_config.MultiselectColumn("测试针床型号", options=needle_bed_models),
                    "转运载具型号": st.column_config.MultiselectColumn("转运载具型号", options=tray_models),
                    "删除": st.column_config.ButtonColumn(
                        "删除", type="tertiary", on_click=_request_resource_delete,
                        key="res_delete_click", width="small",
                    ),
                },
            )
            if not read_only and st.button("保存工序资源", key="save_process_resources"):
                new_res = [
                    {"process_code": selected, "step_no": str(row["工序"]),
                     "program_name": str(row["程序"] or ""),
                     "device_models": _join(row["可执行设备型号"]),
                     "needle_bed_models": _join(row["测试针床型号"]),
                     "tray_models": _join(row["转运载具型号"])}
                    for _, row in edited_res.iterrows() if _text(row["工序"])
                ]
                others = [r for r in resources if r["process_code"] != selected]
                _save("process_step_resources", others + new_res)
                st.toast("工序资源已保存")
                st.rerun()
    elif codes:
        st.info("请勾选上方工艺列表前面的勾选框查看工艺详情")

    pending_route = st.session_state.get("pending_route_delete")
    if pending_route and pending_route.get("process_code") in codes:
        _confirm_delete_route(pending_route)
    pending_res = st.session_state.get("pending_resource_delete")
    if pending_res and pending_res.get("process_code") in codes:
        _confirm_delete_resource(pending_res)


def _clear_pending_process_delete() -> None:
    """执行 clear_pending_process_delete。"""
    st.session_state.pop("pending_process_delete", None)


@st.dialog("确认删除工艺", icon=":material/delete_forever:", on_dismiss=_clear_pending_process_delete)
def _confirm_delete_process(proc: dict[str, Any]) -> None:
    """执行 confirm_delete_process。"""
    code = proc["process_code"]
    st.write(f"确定删除工艺 **{code} - {proc.get('process_name','')}** 吗？")
    st.caption("删除后其工序路线与工序资源会一并删除，绑定的组件将不再有工艺配置。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_process"):
            _clear_pending_process_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_process"):
            _save("processes", [p for p in st.session_state.processes if p["process_code"] != code])
            _save("process_routes", [r for r in st.session_state.process_routes if r["process_code"] != code])
            _save("process_step_resources", [r for r in st.session_state.process_step_resources if r["process_code"] != code])
            if st.session_state.get("process_selected") == code:
                st.session_state.pop("process_selected", None)
            _clear_pending_process_delete()
            st.toast(f"工艺 {code} 已删除")
            st.rerun()


def _clear_pending_route_delete() -> None:
    """执行 clear_pending_route_delete。"""
    st.session_state.pop("pending_route_delete", None)


def _clear_pending_resource_delete() -> None:
    """执行 clear_pending_resource_delete。"""
    st.session_state.pop("pending_resource_delete", None)


@st.dialog("确认删除工序路线", icon=":material/delete_forever:", on_dismiss=_clear_pending_route_delete)
def _confirm_delete_route(target: dict[str, Any]) -> None:
    """执行 confirm_delete_route。"""
    code = target["process_code"]
    step = target["step_no"]
    st.write(f"确定删除工艺 **{code}** 中工序 **{step}** 的路线配置吗？")
    st.caption("删除后该工序的成功/失败下站配置将被移除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_route"):
            _clear_pending_route_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_route"):
            remaining = [
                r for r in st.session_state.process_routes
                if not (r["process_code"] == code and str(r["step_no"]) == step)
            ]
            _save("process_routes", remaining)
            _clear_pending_route_delete()
            st.toast("工序路线已删除")
            st.rerun()


@st.dialog("确认删除工序资源", icon=":material/delete_forever:", on_dismiss=_clear_pending_resource_delete)
def _confirm_delete_resource(target: dict[str, Any]) -> None:
    """执行 confirm_delete_resource。"""
    code = target["process_code"]
    step = target["step_no"]
    st.write(f"确定删除工艺 **{code}** 中工序 **{step}** 的资源配置吗？")
    st.caption("删除后该工序绑定的程序、可执行设备型号和转运载具型号将被移除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_resource"):
            _clear_pending_resource_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_resource"):
            remaining = [
                r for r in st.session_state.process_step_resources
                if not (r["process_code"] == code and str(r["step_no"]) == step)
            ]
            _save("process_step_resources", remaining)
            _clear_pending_resource_delete()
            st.toast("工序资源已删除")
            st.rerun()


def _on_process_editor_change() -> None:
    """“选择”列单选：勾一行时自动取消其他行的勾选。"""
    edited = st.session_state.get("process_editor")
    if not isinstance(edited, dict):
        return
    edits = edited.get("edited_rows", {})
    codes = st.session_state.get("_process_codes", [])
    picked = None
    for row_idx, ch in edits.items():
        if ch.get("选择") is True and 0 <= int(row_idx) < len(codes):
            picked = int(row_idx)
    if picked is None:
        return
    for i in range(len(codes)):
        if i != picked and "选择" not in edits.get(i, {}):
            edits.setdefault(i, {})["选择"] = False
    st.session_state["process_selected"] = codes[picked]
