"""页面：产线测试工站监控（只读 station_summary 汇总表）。"""

from __future__ import annotations

import json
import time
from datetime import datetime
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
    """设备注册页的 devices 表（供"新增"下拉选择）。"""
    from . import client
    try:
        return [d for d in client.master_list("devices") if d.get("enabled")]
    except Exception:
        return []


def _step_names() -> dict:
    from . import client
    try:
        return {str(d["step_no"]): d.get("step_name") or str(d["step_no"]) for d in client.master_list("steps")}
    except Exception:
        return {}


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
    """监控设备管理（新增/编辑/删除），默认折叠容器。"""
    all_config = list(config_devices)

    with st.expander("⚙️ 监控设备管理", expanded=False):
        step_names = _step_names()

        st.subheader("监控设备管理（可直接修改名称，改完点“保存修改”）")

        # 新增：按工序筛选后选择设备
        registered = _registered_devices()
        shown_ids = [x["device_id"] for x in all_config]
        candidates = [d for d in registered if d["device_id"] not in shown_ids]

        if candidates:
            step_opts = ["全部"] + sorted({str(d.get("step_no")) for d in candidates if d.get("step_no")})
            fs = st.selectbox(
                "工序筛选", step_opts, key="mon_filter_step",
                format_func=lambda x: "全部" if x == "全部" else f"{x} - {step_names.get(x, x)}",
            )
            filtered = [
                d for d in candidates
                if (fs == "全部" or str(d.get("step_no") or "") == str(fs))
            ]
            if filtered:
                with st.form("mon_device_create_form", clear_on_submit=False):
                    picked = st.selectbox(
                        "选择设备",
                        options=[d["device_id"] for d in filtered],
                        format_func=lambda x: (
                            f"{x} - {next((d['device_name'] for d in filtered if d['device_id']==x), x)}"
                            f"（{step_names.get(str(next((d.get('step_no') for d in filtered if d['device_id']==x), '')), '')}）"
                        ),
                        key="mon_add_select",
                    )
                    submitted = st.form_submit_button("添加监控设备")
                if submitted:
                    d = next(x for x in filtered if x["device_id"] == picked)
                    all_config.append({
                        "device_id": d["device_id"],
                        "name": d.get("device_name") or d["device_id"],
                        "step_no": str(d.get("step_no") or ""),
                        "step_name": step_names.get(str(d.get("step_no") or ""), str(d.get("step_no") or "")),
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

    return all_config

DT_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_stat_time(value) -> datetime | None:
    """解析统计时间；支持 datetime/date、YYYY-MM-DD HH:MM:SS 及报告里的斜杠格式。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    value = str(value).strip()
    if not value:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _clear_stat_inputs() -> None:
    st.session_state["stat_time_start"] = None
    st.session_state["stat_time_end"] = None


def _apply_stat_range() -> None:
    """点“查询”时计算生效区间：结束空→当前；开始空→结束当天0点；都空→今天0点到现在。"""
    start = _parse_stat_time(st.session_state.get("stat_time_start", ""))
    end = _parse_stat_time(st.session_state.get("stat_time_end", ""))
    if end is None:
        end = datetime.now()
    if start is None:
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    st.session_state["applied_stat_range"] = (start, end)


def _stats_for_range(device_id: str, start: datetime, end: datetime, step_no: str | None = None) -> dict:
    """按生效时间区间，从统一测试报告库 report_index 统计该设备的数据。"""
    from ..repositories import report_details_store

    records: list[dict] = []
    rows = report_details_store.list_overview(None, step_no=step_no)
    for row in rows:
        if str(row.get("station") or "") == str(device_id):
            pass
        elif step_no and str(row.get("step_no") or "") == str(step_no):
            pass
        else:
            continue
        ts = _parse_stat_time(str(row.get("testexecutetime") or ""))
        if ts is None or not (start <= ts <= end):
            continue
        records.append({
            "barcode": str(row.get("barcode") or ""),
            "ts": ts,
            "failed": bool(str(row.get("failed_step") or "").strip()),
        })

    total = len(records)
    fail = sum(1 for r in records if r["failed"])
    # 复测判定：同一条码在该设备内按时间排序，第一条 PASS 记一次通过，后续记复测通过
    by_barcode: dict[str, list[dict]] = {}
    for r in records:
        by_barcode.setdefault(r["barcode"], []).append(r)
    first_pass = 0
    retest_pass = 0
    for group in by_barcode.values():
        passes = [r for r in sorted(group, key=lambda x: x["ts"]) if not r["failed"]]
        if passes:
            first_pass += 1
            retest_pass += len(passes) - 1
    return {
        "total": total,
        "first_pass": first_pass,
        "retest_pass": retest_pass,
        "fail": fail,
    }


def _device_stats(device_id: str, applied) -> dict:
    """设备页与工序页共用的统计来源：有生效区间则按工序库 report_index 统计，否则读 station_summary。"""
    keys = ("total", "first_pass", "retest_pass", "fail")
    if applied:
        return {k: int(_stats_for_range(device_id, applied[0], applied[1]).get(k) or 0) for k in keys}
    row = _read_summary(device_id)
    if row is None:
        return {k: 0 for k in keys}
    return {k: int(row.get(k) or 0) for k in keys}


def _range_caption() -> str:
    applied = st.session_state.get("applied_stat_range")
    if not applied:
        return "统计区间：未筛选（全部汇总数据）"
    a, b = applied
    return f"统计区间：{a.strftime(DT_FORMAT)} ~ {b.strftime(DT_FORMAT)}"


def _render_display_order(all_config: list[dict]) -> None:
    """设置显示：每行卡片数、卡片顺序、统计时间区间。"""
    with st.expander("🔀 设置显示", expanded=False):
        st.number_input(
            "每行卡片数", min_value=1, max_value=12, value=DEFAULT_COLS, step=1, key="mon_cols"
        )

        # 1) 调整卡片顺序
        if all_config:
            st.caption("拖拽下面的设备卡片调节显示顺序（从左到右、从上到下）。")
            labels = [f"{d['name']} ({d['device_id']})" for d in all_config]
            order_fingerprint = "|".join(d["device_id"] for d in all_config)
            sorted_labels = sort_items(
                labels, direction="horizontal", key=f"device_order_sort_{hash(order_fingerprint)}"
            )
            label_to_dev = {f"{d['name']} ({d['device_id']})": d for d in all_config}
            new_list = [label_to_dev[x] for x in sorted_labels if x in label_to_dev]
            if new_list and len(new_list) == len(all_config) and new_list != all_config:
                _save_config_devices(new_list)
                st.rerun()
        else:
            st.info("当前没有显示的设备，请先在“监控设备管理”中新增")

        # 2) 调整统计时间区间（放在卡片顺序下面）
        st.markdown("**调整统计时间区间**")
        c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        c1.datetime_input(
            "开始时间", value=None, format="YYYY-MM-DD", step=60, required=True,
            key="stat_time_start",
        )
        c2.datetime_input(
            "结束时间", value=None, format="YYYY-MM-DD", step=60, required=True,
            key="stat_time_end",
        )
        c3.button("清空", key="stat_time_clear", on_click=_clear_stat_inputs)
        st.button("查询", key="stat_time_query", on_click=_apply_stat_range, type="primary")

        applied = st.session_state.get("applied_stat_range")
        if applied:
            a, b = applied
            st.caption(
                f"当前生效区间：{a.strftime(DT_FORMAT)} ~ {b.strftime(DT_FORMAT)}"
                "（修改时间后需点“查询”才会生效）"
            )
        else:
            st.caption("可点选日期和时间（精确到分钟）；留空时按默认规则，点“查询”生效。")


@st.fragment(run_every=refresh_interval)
def _render_cards_fragment() -> None:
    """只刷新卡片区域：每 1s 重查 station_summary，不影响设备管理/删除弹窗。"""
    # 每次fragment执行都重新读配置，保证新增/排序/删除后卡片立即同步
    devices = _load_config_devices()
    n_cols = int(st.session_state.get("mon_cols", DEFAULT_COLS))
    if not devices:
        st.info("当前没有显示的设备，请在“监控设备管理”中新增")
        return
    rows = [devices[i : i + n_cols] for i in range(0, len(devices), n_cols)]
    for row in rows:
        row_cols = st.columns(n_cols, gap="small")
        for idx, col in enumerate(row_cols):
            if idx < len(row):
                device = row[idx]
                with col:
                    data = _read_summary(device["device_id"])
                    applied = st.session_state.get("applied_stat_range")
                    if data is not None:
                        data = {**data, **_device_stats(device["device_id"], applied)}
                    _render_card(device, data)


@st.fragment(run_every=refresh_interval)
def _render_step_fragment() -> None:
    """工序页：按工序聚合监控设备列表中的统计数据。"""
    devices = _load_config_devices()
    if not devices:
        st.info("当前没有显示的设备，请先在“监控设备管理”中新增")
        return

    applied = st.session_state.get("applied_stat_range")
    st.caption(_range_caption())
    groups: dict[str, dict] = {}
    for d in devices:
        step_no = str(d.get("step_no") or "")
        step_name = str(d.get("step_name") or f"工序{step_no}")
        if step_no not in groups:
            groups[step_no] = {
                "step_name": step_name, "device_count": 0,
                "total": 0, "first_pass": 0, "retest_pass": 0, "fail": 0,
            }
        g = groups[step_no]
        g["device_count"] += 1

        stats = _device_stats(d["device_id"], applied)
        for k in ("total", "first_pass", "retest_pass", "fail"):
            g[k] += int(stats.get(k) or 0)

    rows = []
    for step_no in sorted(groups, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
        g = groups[step_no]
        total = g["total"]
        pass_cnt = g["first_pass"] + g["retest_pass"]
        rows.append({
            "工序号": step_no,
            "工序名": g["step_name"],
            "监控设备数": g["device_count"],
            "测试总数": total,
            "一次通过": g["first_pass"],
            "复测通过": g["retest_pass"],
            "失败": g["fail"],
            "合格率": f"{(pass_cnt / total * 100):.1f}%" if total else "--",
        })
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, width="stretch", alt="按工序划分的监控设备统计汇总")

    if frame.empty:
        return
    fig = go.Figure()
    for col, name, color in (
        ("测试总数", "测试总数", "#6c757d"),
        ("一次通过", "一次通过", "#28a745"),
        ("复测通过", "复测通过", "#4287f5"),
        ("失败", "失败", "#dc3545"),
    ):
        fig.add_bar(
            x=[f"{r['工序号']} {r['工序名']}" for r in rows],
            y=[r[col] for r in rows], name=name, marker_color=color,
        )
    fig.update_layout(
        barmode="group", height=300, margin=dict(l=4, r=4, t=8, b=4),
        xaxis_title="工序", yaxis_title="数量", bargap=0.25,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, alt="按工序划分的测试统计分组柱状图")


def render() -> None:
    st.html(COMPACT_CSS)
    st.title("产线测试工站监控｜设备主动上报")

    # 两个同级折叠容器：设备管理 / 显示顺序——不在 fragment 内，不会被刷新打断
    devices = _load_config_devices()
    _render_device_manager(devices)
    _render_display_order(devices)

    # 监控内容用 tab 组织：设备页 / 工序页
    with st.container(border=True):
        tab_device, tab_step = st.tabs(["设备页", "工序页"])
        with tab_device:
            _render_cards_fragment()
        with tab_step:
            _render_step_fragment()
