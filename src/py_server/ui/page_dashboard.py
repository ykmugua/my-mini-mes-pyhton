"""页面：产线测试工站监控（只读 station_summary 汇总表）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_sortables import sort_items

from ..repositories import station_repo

DEFAULT_COLS = 6
refresh_interval = 1000

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEVICE_CONFIG = PROJECT_ROOT / "config" / "device_config.json"

STATUS_LABELS = {"空闲": "空闲", "测试中": "测试中", "通过": "通过", "失败": "失败", "禁用": "禁用"}
STATUS_COLORS = {"空闲": "#888888", "测试中": "#4287f5", "通过": "#28a745", "失败": "#dc3545", "禁用": "#333333"}
STATUS_NO_CHART = {"禁用"}
METRIC_ITEMS = ["测试总数", "一次通过", "复测通过", "失败"]
FIELD_MAP = {"测试总数": "total", "一次通过": "first_pass", "复测通过": "retest_pass", "失败": "fail"}

MON_DEL_CLICK = "mon_device_delete_click"
MON_DEL_PENDING = "mon_device_delete_pending"


def _request_mon_delete() -> None:
    click = st.session_state.get(MON_DEL_CLICK)
    if click is None:
        return
    row = int(click["row"])
    ids = st.session_state.get("_mon_config_ids", [])
    if 0 <= row < len(ids):
        st.session_state[MON_DEL_PENDING] = ids[row]


def _clear_mon_delete() -> None:
    st.session_state.pop(MON_DEL_PENDING, None)


@st.dialog("确认移除监控设备", icon=":material/delete_forever:", on_dismiss=_clear_mon_delete)
def _confirm_mon_delete(dev: dict) -> None:
    st.write(f"确定从监控中移除 **{dev['name']} ({dev['device_id']})** 吗？")
    st.caption("仅从监控列表移除，不会删除设备注册页中的设备。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_mon_del"):
            _clear_mon_delete()
            st.rerun()
        if st.button("确认移除", type="primary", key="confirm_mon_del"):
            current = json.loads(DEVICE_CONFIG.read_text(encoding="utf-8")).get("devices", [])
            new_list = [d for d in current if d["device_id"] != dev["device_id"]]
            _save_config_devices(new_list)
            _clear_mon_delete()
            st.toast("已移除")
            st.rerun()


COMPACT_CSS = """
<style>
  /* 条码输入框：通过 key 生成的 .st-key-* 类定位（skill: 不用 data-testid 私有类） */
  [class*='st-key-barcode_'] input {
      font-size:20px !important; font-weight:bold !important; color:#1a73e8 !important;
      height:32px !important; padding:2px 8px !important;
  }
  [class*='st-key-barcode_'] { margin-bottom:0 !important; }
  .card-title { text-align:center !important; font-size:16px !important; font-weight:700 !important; margin:0 0 10px 0 !important; line-height:1.3 !important; }
  .sortable-component { background:transparent !important; }
  .sortable-item {
      background:#f0f2f6 !important; color:#000 !important; border-radius:6px !important;
      padding:4px 10px !important; font-weight:700 !important; font-size:13px !important; margin:2px !important;
  }
</style>
"""


def _load_config_devices() -> list[dict]:
    """从 config/device_config.json 读取要显示的设备。"""
    try:
        data = json.loads(DEVICE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.error(f"读取设备配置失败：{exc}")
        return []
    return [d for d in data.get("devices", []) if d.get("enable") is True]


def _save_config_devices(devices: list[dict]) -> None:
    data = {"devices": devices}
    DEVICE_CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _registered_devices() -> list[dict]:
    """设备注册页的 devices 表（供"新增"下拉选择，保留 line_id/step_no 供筛选）。"""
    from . import client
    try:
        return [d for d in client.master_list("devices") if d.get("enabled")]
    except Exception:
        return []


def _line_step_names() -> tuple[dict, dict]:
    from . import client
    try:
        lines = {d["line_id"]: d.get("line_name") or d["line_id"] for d in client.master_list("lines")}
        steps = {int(d["step_no"]): d.get("step_name") or str(d["step_no"]) for d in client.master_list("steps")}
    except Exception:
        lines, steps = {}, {}
    return lines, steps


def _read_summary(device_id: str) -> dict | None:
    try:
        return station_repo.get_by_device(device_id)
    except Exception as exc:
        st.error(f"数据库读取失败：{exc}")
        st.stop()


def _fmt_hms(seconds) -> str:
    s = max(0, int(seconds or 0))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _status_seconds(data: dict) -> int:
    status = str(data.get("status", "禁用"))
    if status in ("通过", "失败"):
        return int(data.get("test_duration") or 0)
    since = data.get("status_since")
    return max(0, int(time.time()) - int(since)) if since else 0


def _status_block(status: str, seconds: int = 0) -> str:
    label = STATUS_LABELS.get(status, "禁用")
    color = STATUS_COLORS.get(status, STATUS_COLORS["禁用"])
    t = _fmt_hms(seconds)
    return (
        f'<div style="position:relative;background-color:{color};border-radius:6px;'
        f'height:32px;display:flex;align-items:center;justify-content:center;">'
        f'<span style="color:#ffffff;font-size:16px;font-weight:bold;">{label}</span>'
        f'<span style="position:absolute;right:8px;color:#ffffff;font-size:11px;">{t}</span>'
        f'</div>'
    )


def _chart(data: dict):
    total = int(data.get("total", 0) or 0)
    values, texts = [], []
    for item in METRIC_ITEMS:
        val = int(data.get(FIELD_MAP[item], 0) or 0)
        values.append(val)
        texts.append(f"{val} ({val / total * 100:.1f}%)" if total > 0 else f"{val} (--)")
    fig = go.Figure(go.Bar(
        x=values, y=METRIC_ITEMS, orientation="h",
        marker_color=["#6c757d", "#28a745", "#4287f5", "#dc3545"],
        text=texts, textposition="auto", hovertemplate="%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        height=140, margin=dict(l=4, r=4, t=2, b=2),
        xaxis=dict(visible=False), yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False, bargap=0.3,
    )
    return fig


def _render_card(device: dict, data: dict | None) -> None:
    name = device.get("name") or device.get("device_id")
    device_id = device.get("device_id", "")
    # 不设固定高度，避免右侧滚动条
    with st.container(border=True):
        st.html(f'<div class="card-title">{name}</div>')
        barcode = "无数据" if data is None else (
            "无条码" if (str(data.get("status", "")) == "空闲" or not data.get("barcode"))
            else data["barcode"]
        )
        st.text_input("当前条码", value=str(barcode), disabled=True,
                      key=f"barcode_{device_id}", label_visibility="collapsed")

        if data is None:
            st.html(_status_block("禁用", 0))
            st.caption("汇总表无该设备记录，未渲染统计")
            return
        status = str(data.get("status", "禁用"))
        st.html(_status_block(status, _status_seconds(data)))

        if status in STATUS_NO_CHART:
            st.caption(f"状态为“{STATUS_LABELS.get(status, status)}”，未渲染统计")
            return
        # 每个页签内容用固定高度容器，保证切换页签时卡片大小不变
        TAB_BODY_H = 150
        tab_stats, tab_fail, tab_ctrl = st.tabs(["统计", "失败详计", "设备控制"])
        with tab_stats:
            with st.container(height=TAB_BODY_H, border=False):
                st.plotly_chart(_chart(data), width="stretch", config={"displayModeBar": False}, alt=f"{name} 测试数据统计柱状图")
        with tab_fail:
            with st.container(height=TAB_BODY_H, border=False):
                details = station_repo.list_fail_details(device_id)
                if details:
                    frame = pd.DataFrame([{"条码": d["barcode"], "失败信息": d["test_item"]} for d in details])
                    st.dataframe(frame, hide_index=True, width="stretch", alt=f"{name} 失败项明细列表")
                else:
                    st.caption("暂无失败记录")
        with tab_ctrl:
            with st.container(height=TAB_BODY_H, border=False):
                st.caption("设备控制功能预留")


def _render_device_manager(config_devices: list[dict]) -> list[dict]:
    """监控设备管理 + 顺序调节，统一放在一个默认折叠的容器里。"""
    all_config = list(config_devices)

    with st.expander("⚙️ 监控设备管理与显示设置", expanded=False):
        line_names, step_names = _line_step_names()

        st.subheader("监控设备管理（可直接修改名称，改完点“保存修改”）")

        # 新增：按产线/工序筛选后选择设备
        with st.expander("新增监控设备", expanded=False):
            registered = _registered_devices()
            shown_ids = [x["device_id"] for x in all_config]
            candidates = [d for d in registered if d["device_id"] not in shown_ids]

            if candidates:
                f1, f2 = st.columns(2)
                line_opts = ["全部"] + sorted({str(d.get("line_id") or "") for d in candidates if d.get("line_id")})
                step_opts = ["全部"] + sorted({int(d.get("step_no")) for d in candidates if d.get("step_no")})
                fl = f1.selectbox("产线筛选", line_opts, key="mon_filter_line")
                fs = f2.selectbox(
                    "工序筛选", step_opts, key="mon_filter_step",
                    format_func=lambda x: "全部" if x == "全部" else f"{x} - {step_names.get(x, x)}",
                )
                filtered = [
                    d for d in candidates
                    if (fl == "全部" or str(d.get("line_id") or "") == fl)
                    and (fs == "全部" or int(d.get("step_no") or 0) == int(fs))
                ]
                if filtered:
                    with st.form("mon_device_create_form", clear_on_submit=False):
                        picked = st.selectbox(
                            "选择设备",
                            options=[d["device_id"] for d in filtered],
                            format_func=lambda x: (
                                f"{x} - {next((d['device_name'] for d in filtered if d['device_id']==x), x)}"
                                f"（{line_names.get(str(next((d.get('line_id') for d in filtered if d['device_id']==x), '')), '')} / "
                                f"{step_names.get(int(next((d.get('step_no') for d in filtered if d['device_id']==x), 0)), '')}）"
                            ),
                            key="mon_add_select",
                        )
                        submitted = st.form_submit_button("添加监控设备")
                    if submitted:
                        d = next(x for x in filtered if x["device_id"] == picked)
                        all_config.append({
                            "device_id": d["device_id"],
                            "name": d.get("device_name") or d["device_id"],
                            "line_id": str(d.get("line_id") or ""),
                            "line_name": line_names.get(str(d.get("line_id") or ""), str(d.get("line_id") or "")),
                            "step_no": int(d.get("step_no") or 0),
                            "step_name": step_names.get(int(d.get("step_no") or 0), str(d.get("step_no") or "")),
                            "ip": d.get("ip", "127.0.0.1"), "port": d.get("port", 6379), "enable": True,
                        })
                        _save_config_devices(all_config)
                        st.toast(f"已添加 {d['device_id']}")
                        st.rerun()
                else:
                    st.info("当前筛选条件下没有可添加的设备。")
            else:
                st.info("设备注册页中没有可添加的启用设备。")

        # 列表（data_editor + 删除列）
        st.session_state["_mon_config_ids"] = [d["device_id"] for d in all_config]
        frame = pd.DataFrame([
            {
                "设备编号": d["device_id"],
                "设备名称": d["name"],
                "所属线体": (d.get("line_name") or d.get("line_id") or ""),
                "所属工序": (d.get("step_name") or (f"工序{d['step_no']}" if d.get("step_no") else "")),
                "删除": "删除",
            }
            for d in all_config
        ])
        edited = None
        if all_config:
            edited = st.data_editor(
                frame,
                column_config={
                    "设备编号": st.column_config.TextColumn("设备编号", disabled=True, width="medium"),
                    "设备名称": st.column_config.TextColumn("设备名称", required=True, width="medium"),
                    "所属线体": st.column_config.TextColumn("所属线体", disabled=True, width="medium"),
                    "所属工序": st.column_config.TextColumn("所属工序", disabled=True, width="medium"),
                    "删除": st.column_config.ButtonColumn(
                        "删除", type="tertiary", on_click=_request_mon_delete,
                        key=MON_DEL_CLICK, width="small",
                    ),
                },
                hide_index=True, num_rows="fixed", width="stretch", alt="监控设备列表",
            )
        else:
            st.info("暂无监控设备，请在上方新增")

        if st.button("保存修改", icon=":material/save:", key="mon_save_names"):
            if edited is not None:
                name_map = dict(zip(edited["设备编号"], edited["设备名称"]))
                new_list = []
                for d in all_config:
                    nd = dict(d)
                    if nd["device_id"] in name_map:
                        nd["name"] = name_map[nd["device_id"]]
                    new_list.append(nd)
                _save_config_devices(new_list)
                st.toast("监控设备已保存")
                st.rerun()

        pending = st.session_state.get(MON_DEL_PENDING)
        if pending:
            dev = next((d for d in all_config if d["device_id"] == pending), None)
            if dev is None:
                _clear_mon_delete()
            else:
                _confirm_mon_delete(dev)

        st.divider()
        st.subheader("调整显示顺序")

        n_cols = st.number_input(
            "每行卡片数", min_value=1, max_value=12, value=DEFAULT_COLS, step=1, key="mon_cols"
        )
        if all_config:
            st.caption("拖拽下面的设备卡片调节显示顺序（从左到右、从上到下）。")
            labels = [f"{d['name']} ({d['device_id']})" for d in all_config]
            # key 含设备列表指纹：增删设备后组件重新挂载，避免旧拖拽状态导致顺序区不刷新
            order_fingerprint = "|".join(d["device_id"] for d in all_config)
            sorted_labels = sort_items(
                labels, direction="horizontal", key=f"device_order_sort_{hash(order_fingerprint)}"
            )
            label_to_dev = {f"{d['name']} ({d['device_id']})": d for d in all_config}
            new_list = [label_to_dev[x] for x in sorted_labels if x in label_to_dev]
            if new_list and len(new_list) == len(all_config) and new_list != all_config:
                _save_config_devices(new_list)
                st.rerun()
    return all_config

@st.fragment(run_every=refresh_interval)
def _render_cards_fragment() -> None:
    """只刷新卡片区域：每 1s 重查 station_summary，不影响设备管理/删除弹窗。"""
    # 每次fragment执行都重新读配置，保证新增/排序/删除后卡片立即同步
    devices = _load_config_devices()
    n_cols = int(st.session_state.get("mon_cols", DEFAULT_COLS))
    if not devices:
        st.info("当前没有显示的设备，请在“监控设备管理与显示设置”中新增")
        return
    rows = [devices[i : i + n_cols] for i in range(0, len(devices), n_cols)]
    for row in rows:
        row_cols = st.columns(n_cols, gap="small")
        for idx, col in enumerate(row_cols):
            if idx < len(row):
                device = row[idx]
                with col:
                    data = _read_summary(device["device_id"])
                    _render_card(device, data)


def render() -> None:
    st.html(COMPACT_CSS)
    st.title("产线测试工站监控｜设备主动上报")

    # 设备管理（含顺序/行数设置，默认折叠）——不在 fragment 内，不会被刷新打断
    _render_device_manager(_load_config_devices())

    # 监控内容用 tab 组织，后续可直接在此增加其他页签
    with st.container(border=True):
        tab_device, = st.tabs(["设备页"])
        with tab_device:
            _render_cards_fragment()
