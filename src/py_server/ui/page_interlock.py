"""页面：工序锁。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import services
from ..services import ServiceError
from . import common


def _locked_frame(locked: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "工件码": item["workpiece"],
                "产品": item.get("product") or "",
                "当前设备": item.get("current_device") or "",
                "工件状态": item.get("status") or "",
                "锁定原因": item["lock_reason"],
                "锁定时间": common.local_time(item.get("locked_at")),
            }
            for item in locked
        ]
    )


def _render_locked(locked: list[dict]) -> None:
    st.subheader("当前锁定工件")
    if not locked:
        st.success("当前没有锁定工件。")
        return
    st.dataframe(_locked_frame(locked), hide_index=True, width="stretch")


def _render_unlock(locked: list[dict]) -> None:
    st.subheader("人工解锁")
    st.caption("解锁必须填写原因并勾选确认；解锁后工件放行状态恢复，动作全部留痕。")
    if not locked:
        st.caption("暂无需要解锁的工件。")
        return
    labels = {
        f"{item['workpiece']} · {item.get('current_device') or '-'} · {item['lock_reason']}": item[
            "workpiece"
        ]
        for item in locked
    }
    with st.form("unlock_form"):
        choice = st.selectbox(
            "选择工件", list(labels), key="unlock_choice", disabled=not common.can_edit()
        )
        col1, col2 = st.columns([1, 2])
        unlocker = col1.text_input(
            "解锁人",
            value=common.operator(),
            key="unlock_operator",
            disabled=not common.can_edit(),
        )
        reason = col2.text_input(
            "解锁原因（必填）",
            key="unlock_reason",
            placeholder="例如：返修后复测确认，经产线负责人同意放行",
            disabled=not common.can_edit(),
        )
        confirmed = st.checkbox(
            "我已确认该工件可以放行，本次操作将记录解锁人、原因和时间",
            key="unlock_confirm",
            disabled=not common.can_edit(),
        )
        submitted = st.form_submit_button(
            "执行解锁", type="primary", disabled=not common.can_edit()
        )
    if not submitted:
        return
    try:
        result = services.unlock_workpiece(
            workpiece=labels[choice],
            operator=unlocker,
            reason=reason,
            confirmed=confirmed,
        )
    except ServiceError as exc:
        st.error(str(exc))
    else:
        common.flash("success", f"工件 {result['workpiece']} 已解锁并放行。")
        st.rerun()


def _render_unlock_logs() -> None:
    with st.expander("解锁留痕（最近 50 条）"):
        logs = services.list_unlock_logs(50)
        if not logs:
            st.caption("暂无解锁记录。")
            return
        frame = pd.DataFrame(
            [
                {
                    "时间": common.local_time(item["unlocked_at"]),
                    "工件码": item["workpiece"],
                    "解锁人": item["operator"],
                    "解锁原因": item["reason"],
                    "锁定原因（解锁前）": item.get("lock_reason") or "",
                    "设备": item.get("device_id") or "",
                }
                for item in logs
            ]
        )
        st.dataframe(frame, hide_index=True, width="stretch")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


def _render_upstream_rules() -> None:
    st.subheader("前道关键设备配置")
    st.caption(
        "“前道关键设备”不写死在代码里：在此维护设备的前道依赖，保存后立即生效。"
        "产品型号留空表示对所有产品生效。"
    )
    rules = services.list_upstream_rules()
    frame = pd.DataFrame(
        [
            {
                "产品型号": item.get("product") or "",
                "设备标识": item["device_id"],
                "前道设备标识": item["upstream_device_id"],
            }
            for item in rules
        ],
        columns=["产品型号", "设备标识", "前道设备标识"],
    )
    edited = st.data_editor(
        frame,
        key="upstream_editor",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        disabled=not common.can_edit(),
        column_config={
            "产品型号": st.column_config.TextColumn("产品型号（留空=全部产品）", width="medium"),
            "设备标识": st.column_config.TextColumn("设备标识", required=True, width="small"),
            "前道设备标识": st.column_config.TextColumn(
                "前道设备标识", required=True, width="small"
            ),
        },
    )
    if st.button("保存前道规则", disabled=not common.can_edit()):
        rows = []
        for record in edited.to_dict("records"):
            product = _cell(record.get("产品型号"))
            device = _cell(record.get("设备标识"))
            upstream = _cell(record.get("前道设备标识"))
            if not device and not upstream:
                continue
            rows.append(
                {
                    "product": product,
                    "device_id": device,
                    "upstream_device_id": upstream,
                }
            )
        try:
            count = services.replace_upstream_rules(rows)
        except ServiceError as exc:
            st.error(str(exc))
        else:
            common.flash("success", f"已保存 {count} 条前道设备规则。")
            st.rerun()


def _render_interlock_check() -> None:
    st.subheader("放行状态自检")
    st.caption("现场调试时可直接模拟设备查询，检查规则是否按预期放行。")
    with st.form("interlock_check_form"):
        col1, col2, col3 = st.columns(3)
        workpiece = col1.text_input("工件码", key="check_workpiece")
        device = col2.text_input("设备 ID", key="check_device")
        product = col3.text_input("产品型号（可选）", key="check_product")
        submitted = st.form_submit_button("查询放行状态")
    if not submitted:
        return
    try:
        result = services.interlock_check(
            workpiece=workpiece,
            device_id=device,
            product=product or None,
        )
    except ServiceError as exc:
        st.error(str(exc))
        return
    if result["allowed"]:
        st.success("允许操作" + (f"：{result['reason']}" if result["reason"] else ""))
    else:
        st.error(f"拒绝操作：{result['reason']}")
    st.json(result)


def render() -> None:
    st.title("🔒 工序锁")
    st.caption(
        "规则：① 前道关键设备无 PASS 记录 → 拒绝启动；② FAIL 工件后续设备拦截；"
        "③ 程序版本/校验和不一致 → 结果不可信且禁止放行。"
    )
    common.render_flash()
    common.render_readonly_notice()

    locked = services.list_locked_workpieces()
    rules = services.list_upstream_rules()
    logs = services.list_unlock_logs(1000)
    col1, col2, col3 = st.columns(3)
    col1.metric("当前锁定工件", len(locked))
    col2.metric("前道规则", len(rules))
    col3.metric("解锁记录", len(logs))

    _render_locked(locked)
    st.divider()
    _render_unlock(locked)
    _render_unlock_logs()
    st.divider()
    _render_upstream_rules()
    st.divider()
    _render_interlock_check()
