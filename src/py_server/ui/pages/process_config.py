"""工艺配置页面：新增（可派生）/ 工艺列表 / 工艺详情（路线 + 工序资源）。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from ._mock_program_data import enabled_steps, step_label


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    t = str(value).strip()
    return "" if t.lower() in {"nan", "none", "nat"} else t


def _split(value: Any) -> list[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def _join(items: Any) -> str:
    if items is None:
        return ""
    if isinstance(items, str):
        return items
    return ",".join(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))


def _save(key: str, rows: list[dict[str, Any]]) -> None:
    st.session_state[key] = rows
    master.save_key(key)


def render_page() -> None:
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

    st.title("⚙️ 工艺配置")

    # -------------------------------------------------------------------------
    # 区块 1：新增工艺（空白 / 从已有工艺派生，深拷贝）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("新增工艺")
        if read_only:
            st.info("只读角色不可新增工艺。")
        else:
            with st.form("process_create_form", clear_on_submit=False, border=False):
                c1, c2, c3 = st.columns(3)
                new_code = c1.text_input("工艺号", key="new_process_code", placeholder="例如 PROC-003")
                new_name = c2.text_input("工艺名称", key="new_process_name", placeholder="例如 电源板工艺B")
                source = c3.selectbox(
                    "派生自", options=["空白新增"] + [p["process_code"] for p in processes],
                    key="new_process_source",
                )
                c4, c5 = st.columns([3, 1])
                new_remark = c4.text_input("备注", key="new_process_remark", placeholder="可选")
                enabled_text = c5.selectbox("启用", options=["是", "否"], key="new_process_enabled")
                submitted = st.form_submit_button("添加工艺")
            if submitted:
                code = new_code.strip()
                if not code:
                    st.error("工艺号不能为空")
                elif any(p["process_code"] == code for p in processes):
                    st.error("工艺号已存在")
                else:
                    new_processes = list(processes) + [{
                        "process_code": code,
                        "process_name": new_name.strip() or code,
                        "enabled": enabled_text == "是",
                        "remark": new_remark.strip(),
                        "source_process_code": "" if source == "空白新增" else source,
                    }]
                    new_routes = list(routes)
                    new_resources = list(resources)
                    if source != "空白新增":
                        # 深拷贝：路线与资源完全独立
                        new_routes += [
                            {**r, "process_code": code}
                            for r in routes if r["process_code"] == source
                        ]
                        new_resources += [
                            {**r, "process_code": code}
                            for r in resources if r["process_code"] == source
                        ]
                    _save("processes", new_processes)
                    _save("process_routes", new_routes)
                    _save("process_step_resources", new_resources)
                    st.toast(f"工艺 {code} 已新增" + (f"（派生自 {source}）" if source != "空白新增" else ""))
                    st.rerun()

    # -------------------------------------------------------------------------
    # 区块 2：工艺列表（行选择，勾选后展开详情）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("工艺列表")
        codes = [p["process_code"] for p in processes]
        frame = pd.DataFrame([{
            "工艺号": p["process_code"],
            "工艺名称": p.get("process_name", ""),
            "启用": "是" if p.get("enabled", True) else "否",
            "来源工艺": p.get("source_process_code", "") or "—",
            "引用组件数": sum(1 for q in products if q.get("process_code") == p["process_code"]),
            "备注": p.get("remark", ""),
        } for p in processes], columns=["工艺号", "工艺名称", "启用", "来源工艺", "引用组件数", "备注"])
        event = st.dataframe(
            frame, hide_index=True, width="stretch", height=220,
            alt="工艺列表（点击行查看详情）",
            on_select="rerun", selection_mode="single-row", key="process_list_select",
        )
        sel_rows = event.selection.rows if hasattr(event, "selection") else []
        if sel_rows:
            selected = codes[sel_rows[0]]
            if st.session_state.get("process_selected") != selected:
                st.session_state["process_selected"] = selected
                st.rerun()
        elif st.session_state.get("process_selected"):
            st.session_state.pop("process_selected", None)
            st.rerun()

    # -------------------------------------------------------------------------
    # 区块 3：工艺详情（工序路线 + 工序资源）
    # -------------------------------------------------------------------------
    selected = st.session_state.get("process_selected")
    if selected and selected in codes:
        with st.container(border=True):
            st.subheader(f"工艺详情：{selected}")
            cur_routes = [r for r in routes if r["process_code"] == selected]

            # 3.1 工序路线
            st.markdown("**工序路线**")
            route_frame = pd.DataFrame([{
                "工序号": r["step_no"],
                "成功下站": r["success_next_step"],
                "失败下站": r["fail_next_step"],
                "删除": "删除",
            } for r in cur_routes], columns=["工序号", "成功下站", "失败下站", "删除"])
            next_opts = step_nos + ["END", "LOCK"]
            edited_routes = st.data_editor(
                route_frame, hide_index=True, num_rows="dynamic", width="stretch",
                alt="工序路线编辑器", key=f"route_editor_{selected}",
                column_config={
                    "工序号": st.column_config.SelectboxColumn("工序号", options=step_nos, required=True),
                    "成功下站": st.column_config.SelectboxColumn("成功下站", options=next_opts, required=True),
                    "失败下站": st.column_config.SelectboxColumn("失败下站", options=next_opts, required=True),
                    "删除": st.column_config.ButtonColumn("删除", type="tertiary", width="small"),
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

            # 3.2 工序资源（程序 / 设备型号多选 / 载具型号多选）
            st.markdown("**工序资源**")
            res_by_step = {str(r["step_no"]): r for r in resources if r["process_code"] == selected}
            resource_frame = pd.DataFrame([{
                "工序": str(r["step_no"]),
                "程序": res_by_step.get(str(r["step_no"]), {}).get("program_name", ""),
                "可执行设备型号": _split(res_by_step.get(str(r["step_no"]), {}).get("device_models", "")),
                "转运载具型号": _split(res_by_step.get(str(r["step_no"]), {}).get("tray_models", "")),
                "删除": "删除",
            } for r in cur_routes], columns=["工序", "程序", "可执行设备型号", "转运载具型号", "删除"])
            edited_res = st.data_editor(
                resource_frame, hide_index=True, num_rows="fixed", width="stretch",
                alt="工序资源编辑器", key=f"res_editor_{selected}",
                column_config={
                    "工序": st.column_config.TextColumn("工序", disabled=True),
                    "程序": st.column_config.SelectboxColumn("程序", options=program_names),
                    "可执行设备型号": st.column_config.MultiselectColumn("可执行设备型号", options=device_models),
                    "转运载具型号": st.column_config.MultiselectColumn("转运载具型号", options=tray_models),
                    "删除": st.column_config.ButtonColumn("删除", type="tertiary", width="small"),
                },
            )
            if not read_only and st.button("保存工序资源", key="save_process_resources"):
                new_res = [
                    {"process_code": selected, "step_no": str(row["工序"]),
                     "program_name": str(row["程序"] or ""),
                     "device_models": _join(row["可执行设备型号"]),
                     "tray_models": _join(row["转运载具型号"])}
                    for _, row in edited_res.iterrows() if _text(row["工序"])
                ]
                others = [r for r in resources if r["process_code"] != selected]
                _save("process_step_resources", others + new_res)
                st.toast("工序资源已保存")
                st.rerun()

            # 3.3 删除工艺（被组件引用则禁止）
            if not read_only and st.button("删除该工艺", icon=":material/delete:", key="delete_process_btn"):
                refs = [q["product_model"] for q in products if q.get("process_code") == selected]
                if refs:
                    st.error(f"该工艺被组件 {', '.join(refs)} 引用，不能删除")
                else:
                    _save("processes", [p for p in processes if p["process_code"] != selected])
                    _save("process_routes", [r for r in routes if r["process_code"] != selected])
                    _save("process_step_resources", [r for r in resources if r["process_code"] != selected])
                    st.session_state.pop("process_selected", None)
                    st.toast("工艺已删除")
                    st.rerun()
    elif codes:
        st.info("请勾选上方工艺列表中的一行查看工艺详情")
