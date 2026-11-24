"""页面：产线测试工站监控（设备状态读取汇总表，测试数据统一读取 TestReport.db）。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_sortables import sort_items

from . import client
from .pages.constants import (
    ADD_MONITOR_DEVICE_BUTTON,
    DISPLAY_SETTINGS_SECTION,
    MONITOR_DEVICE_SECTION,
    PAGE_TITLE_DASHBOARD,
    QUERY_BUTTON,
    SELECT_DEVICE_LABEL,
    SELECT_PROCESS_LABEL,
    SELECT_PROCESS_PLACEHOLDER,
    SAVE_MONITOR_DEVICES_BUTTON,
    STEP_FILTER_LABEL,
)

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
    """执行 request_mon_delete。"""
    click = st.session_state.get(MON_DEL_CLICK)
    if click is None:
        return
    row = int(click["row"])
    ids = st.session_state.get("_mon_config_ids", [])
    if 0 <= row < len(ids):
        st.session_state[MON_DEL_PENDING] = ids[row]


def _clear_mon_delete() -> None:
    """执行 clear_mon_delete。"""
    st.session_state.pop(MON_DEL_PENDING, None)


@st.dialog("确认移除监控设备", icon=":material/delete_forever:", on_dismiss=_clear_mon_delete)
def _confirm_mon_delete(dev: dict) -> None:
    """执行 confirm_mon_delete。"""
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
    return list(data.get("devices", []))


def _save_config_devices(devices: list[dict]) -> None:
    """执行 save_config_devices。"""
    data = {"devices": devices}
    DEVICE_CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_device_enabled(device_id: str, enabled: bool) -> None:
    """更新设备开启状态，保留其他配置项。"""
    try:
        data = json.loads(DEVICE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.error(f"读取设备配置失败：{exc}")
        return
    devices = data.get("devices", [])
    for device in devices:
        if str(device.get("device_id") or "") == device_id:
            device["enable"] = bool(enabled)
            break
    _save_config_devices(devices)


def _registered_devices() -> list[dict]:
    """设备注册页的 devices 表（供"新增"下拉选择）。"""
    from . import client
    try:
        return [d for d in client.master_list("devices") if d.get("enabled")]
    except Exception:
        return []


def _step_names() -> dict:
    """执行 step_names。"""
    from . import client
    try:
        return {str(d["step_no"]): d.get("step_name") or str(d["step_no"]) for d in client.master_list("steps")}
    except Exception:
        return {}


def _process_options() -> dict[str, str]:
    """按工艺配置返回工艺 label 到工艺号的映射。"""
    from . import client
    try:
        snapshot = client.master_snapshot()[0] or {}
    except Exception:
        return {}
    options: dict[str, str] = {}
    for process in snapshot.get("processes", []) or []:
        if not process.get("enabled", True):
            continue
        code = str(process.get("process_code") or "")
        if not code:
            continue
        name = str(process.get("process_name") or code)
        options[f"{code} - {name}"] = code
    return dict(sorted(options.items()))


def _process_step_map(process_code: str) -> list[tuple[str, str]]:
    """返回指定工艺的工序列表：(工序号, 工序名)。"""
    from . import client
    try:
        snapshot = client.master_snapshot()[0] or {}
    except Exception:
        return []
    step_names = {
        str(step.get("step_no")): str(step.get("step_name") or step.get("step_no") or "")
        for step in snapshot.get("steps", [])
    }
    steps: list[tuple[str, str]] = []
    seen: set[str] = set()
    for route in snapshot.get("process_routes", []) or []:
        if str(route.get("process_code") or "") != process_code:
            continue
        step_no = str(route.get("step_no") or "")
        if not step_no or step_no in {"END", "LOCK"} or step_no in seen:
            continue
        seen.add(step_no)
        steps.append((step_no, step_names.get(step_no, step_no)))
    return steps


def _split_csv(value: object) -> list[str]:
    """拆分工艺资源中的逗号分隔字段。"""
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _process_device_step_map(process_code: str) -> dict[str, tuple[str, str]]:
    """按工艺资源配置返回设备编号到 (工序号, 工序名) 的映射。"""
    from . import client
    try:
        snapshot = client.master_snapshot()[0] or {}
    except Exception:
        return {}
    step_names = {
        str(step.get("step_no")): str(step.get("step_name") or step.get("step_no") or "")
        for step in snapshot.get("steps", [])
    }
    devices = {
        str(device.get("device_id")): str(device.get("device_model") or "")
        for device in snapshot.get("devices", []) or []
    }
    result: dict[str, tuple[str, str]] = {}
    for resource in snapshot.get("process_step_resources", []) or []:
        if str(resource.get("process_code") or "") != process_code:
            continue
        step_no = str(resource.get("step_no") or "")
        if not step_no or step_no in {"END", "LOCK"}:
            continue
        models = set(_split_csv(resource.get("device_models")))
        if not models:
            continue
        step_name = step_names.get(step_no, step_no)
        for device_id, model in devices.items():
            if model in models:
                result[device_id] = (step_no, step_name)
    return result


def _read_summary(device_id: str) -> dict | None:
    """通过 HTTP 读取单设备汇总。"""
    try:
        return client.station_summary(device_id)
    except Exception as exc:
        st.error(f"读取看板汇总失败：{exc}")
        st.stop()


def _fmt_hms(seconds) -> str:
    """执行 fmt_hms。"""
    s = max(0, int(seconds or 0))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _status_seconds(data: dict) -> int:
    """执行 status_seconds。"""
    status = str(data.get("status") or "空闲")
    if status in ("通过", "失败"):
        return int(data.get("test_duration") or 0)
    since = data.get("status_since")
    return max(0, int(time.time()) - int(since)) if since else 0


def _status_block(status: str, seconds: int = 0) -> str:
    """执行 status_block。"""
    label = STATUS_LABELS.get(status, "空闲")
    color = STATUS_COLORS.get(status, STATUS_COLORS["空闲"])
    t = _fmt_hms(seconds)
    return (
        f'<div style="position:relative;background-color:{color};border-radius:6px;'
        f'height:32px;display:flex;align-items:center;justify-content:center;">'
        f'<span style="color:#ffffff;font-size:16px;font-weight:bold;">{label}</span>'
        f'<span style="position:absolute;right:8px;color:#ffffff;font-size:11px;">{t}</span>'
        f'</div>'
    )


def _chart(data: dict):
    """执行 chart。"""
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
    """执行 render_card。"""
    data = data or {}
    name = device.get("name") or device.get("device_id")
    device_id = device.get("device_id", "")
    # 不设固定高度，避免右侧滚动条
    with st.container(border=True):
        st.html(f'<div class="card-title">{name}</div>')
        barcode = (
            "无条码"
            if (str(data.get("status") or "空闲") == "空闲" or not data.get("barcode"))
            else str(data["barcode"])
        )
        st.text_input("当前条码", value=str(barcode), disabled=True,
                      key=f"barcode_{device_id}", label_visibility="collapsed")

        status = str(data.get("status") or "空闲")
        st.html(_status_block(status, _status_seconds(data)))
        # 每个页签内容用固定高度容器，保证切换页签时卡片大小不变
        TAB_BODY_H = 150
        tab_stats, tab_fail, tab_ctrl = st.tabs(["统计", "失败详计", "设备控制"])
        with tab_stats:
            with st.container(height=TAB_BODY_H, border=False):
                st.plotly_chart(_chart(data), width="stretch", config={"displayModeBar": False}, alt=f"{name} 测试数据统计柱状图")
        with tab_fail:
            with st.container(height=TAB_BODY_H, border=False):
                details = client.station_fail_details(device_id)
                if details:
                    frame = pd.DataFrame([{"条码": d["barcode"], "失败信息": d["test_item"]} for d in details])
                    st.dataframe(frame, hide_index=True, width="stretch", alt=f"{name} 失败项明细列表")
                else:
                    st.caption("暂无失败记录")
        with tab_ctrl:
            with st.container(height=TAB_BODY_H, border=False):
                enabled = bool(device.get("enable", True))
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown("设备开启")
                    st.toggle(
                        "设备开启",
                        value=enabled,
                        key=f"device_enabled_{device_id}",
                        label_visibility="collapsed",
                        on_change=_set_device_enabled,
                        args=(device_id, not enabled),
                    )


def _render_device_manager(config_devices: list[dict]) -> list[dict]:
    """监控设备管理（新增/编辑/删除），默认折叠容器。"""
    all_config = list(config_devices)

    with st.expander("监控设备管理", expanded=False):
        step_names = _step_names()

        st.subheader(MONITOR_DEVICE_SECTION)

        # 新增：按工艺配置决定设备归属工序
        registered = _registered_devices()
        shown_ids = [x["device_id"] for x in all_config]
        candidates = [d for d in registered if d["device_id"] not in shown_ids]

        if candidates:
            process_options = _process_options()
            selected_process_label = st.selectbox(
                SELECT_PROCESS_LABEL,
                list(process_options),
                index=None,
                placeholder=SELECT_PROCESS_PLACEHOLDER,
                key="mon_process_select",
                persist_state="session",
                on_change="rerun",
            )
            selected_process_code = process_options.get(selected_process_label or "")
            process_device_steps = _process_device_step_map(selected_process_code) if selected_process_code else {}
            process_steps = _process_step_map(selected_process_code) if selected_process_code else []
            step_filter_options = ["全部"] + [f"{step_no} - {step_name}" for step_no, step_name in process_steps]
            selected_step_filter = st.selectbox(
                STEP_FILTER_LABEL,
                step_filter_options,
                key="mon_filter_step",
                persist_state="session",
                on_change="rerun",
                disabled=not selected_process_code,
            )
            filtered_device_ids = {
                device_id
                for device_id, (step_no, _) in process_device_steps.items()
                if selected_step_filter == "全部"
                or selected_step_filter.startswith(f"{step_no} - ")
            }
            filtered = [
                d for d in candidates if d["device_id"] in filtered_device_ids
            ]
            if filtered:
                with st.form("mon_device_create_form", clear_on_submit=False):
                    picked = st.selectbox(
                        SELECT_DEVICE_LABEL,
                        options=[d["device_id"] for d in filtered],
                        key="mon_add_select",
                    )
                    submitted = st.form_submit_button(ADD_MONITOR_DEVICE_BUTTON)
                if submitted:
                    d = next(x for x in filtered if x["device_id"] == picked)
                    step_no, step_name = process_device_steps[d["device_id"]]
                    all_config.append({
                        "device_id": d["device_id"],
                        "name": d.get("device_name") or d["device_id"],
                        "step_no": step_no,
                        "step_name": step_name,
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

        if st.button(SAVE_MONITOR_DEVICES_BUTTON, icon=":material/save:", key="mon_save_names"):
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
    """执行 clear_stat_inputs。"""
    st.session_state["stat_time_start"] = None
    st.session_state["stat_time_end"] = None
    st.session_state["applied_stat_range"] = None


def _apply_stat_range() -> None:
    """点“查询”时计算生效区间：都空→今天0点到现在；设置后严格按时间范围筛选。"""
    start = _parse_stat_time(st.session_state.get("stat_time_start", ""))
    end = _parse_stat_time(st.session_state.get("stat_time_end", ""))
    if end is None:
        end = datetime.now()
    if start is None:
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    st.session_state["applied_stat_range"] = (start, end)


def _stats_for_range(
    device_id: str,
    start: datetime | None,
    end: datetime | None,
    step_no: str | None = None,
) -> dict:
    """按生效时间区间，从统一测试报告库 report_index 统计该设备的数据。"""
    records: list[dict] = []
    rows = client.report_index(None, step_no)
    for row in rows:
        if str(row.get("station") or "") == str(device_id):
            pass
        elif step_no and str(row.get("step_no") or "") == str(step_no):
            pass
        else:
            continue
        ts = _parse_stat_time(str(row.get("testexecutetime") or ""))
        if ts is None:
            continue
        if start is not None and ts < start:
            continue
        if end is not None and ts > end:
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
    """卡片测试数据统一来自 TestReport.db 的 report_index；时间区间为空时统计当天。"""
    keys = ("total", "first_pass", "retest_pass", "fail")
    if applied:
        start, end = applied
    else:
        end = datetime.now()
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return {k: int(_stats_for_range(device_id, start, end).get(k) or 0) for k in keys}


def _range_caption() -> str:
    """执行 range_caption。"""
    applied = st.session_state.get("applied_stat_range")
    if not applied:
        return "统计区间：未筛选（默认当日 00:00 至现在）"
    a, b = applied
    return f"统计区间：{a.strftime(DT_FORMAT)} ~ {b.strftime(DT_FORMAT)}"


def _render_display_order(all_config: list[dict]) -> None:
    """设置显示：每行卡片数、卡片顺序、统计时间区间。"""
    with st.expander(DISPLAY_SETTINGS_SECTION, expanded=False):
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
            st.info("当前没有显示的设备，请先在“监控设备列表”中新增")

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
        st.button(QUERY_BUTTON, key="stat_time_query", on_click=_apply_stat_range, type="primary")

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
        st.info("当前没有显示的设备，请在“监控设备列表”中新增")
        return
    rows = [devices[i : i + n_cols] for i in range(0, len(devices), n_cols)]
    for row in rows:
        row_cols = st.columns(n_cols, gap="small")
        for idx, col in enumerate(row_cols):
            if idx < len(row):
                device = row[idx]
                with col:
                    data = _read_summary(device["device_id"]) or {}
                    applied = st.session_state.get("applied_stat_range")
                    data = {**data, **_device_stats(device["device_id"], applied)}
                    _render_card(device, data)


@st.fragment(run_every=refresh_interval)
def _render_step_fragment() -> None:
    """工序页：按工序聚合监控设备列表中的统计数据。"""
    devices = _load_config_devices()
    if not devices:
        st.info("当前没有显示的设备，请先在“监控设备列表”中新增")
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
    """执行 render。"""
    st.html(COMPACT_CSS)
    st.title(PAGE_TITLE_DASHBOARD)

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
