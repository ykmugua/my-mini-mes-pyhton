"""页面：程序下发。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import services
from ..services import ServiceError
from . import common

EDIT_MAP = {
    "设备标识": "device_id",
    "产品型号": "product",
    "程序版本": "program_version",
    "下载 URL": "download_url",
    "SHA256": "sha256",
}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


def _production_status(binding: dict) -> str:
    if not binding.get("reported_version"):
        return "未上报"
    if binding["reported_version"] != binding["program_version"]:
        return "版本漂移"
    reported_sha = (binding.get("reported_sha256") or "").lower()
    if not reported_sha:
        return "未上报校验和"
    if reported_sha != (binding["sha256"] or "").lower():
        return "校验不一致"
    if binding.get("program_ok") == 0:
        return "自检失败"
    return "可生产"


def _sha_status(binding: dict) -> str:
    reported = (binding.get("reported_sha256") or "").lower()
    if not reported:
        return "未上报"
    return "一致" if reported == (binding["sha256"] or "").lower() else "不一致"


def _display_frame(bindings: list[dict]) -> pd.DataFrame:
    records = []
    for binding in bindings:
        records.append(
            {
                "设备标识": binding["device_id"],
                "产品型号": binding["product"],
                "程序版本": binding["program_version"],
                "下载 URL": binding["download_url"],
                "SHA256": binding["sha256"],
                "设备上报版本": binding.get("reported_version") or "",
                "上报校验和": _sha_status(binding),
                "生产状态": _production_status(binding),
                "最后拉取时间": common.local_time(binding.get("last_pull_at")),
                "更新时间": common.local_time(binding.get("updated_at")),
            }
        )
    columns = list(EDIT_MAP) + [
        "设备上报版本",
        "上报校验和",
        "生产状态",
        "最后拉取时间",
        "更新时间",
    ]
    return pd.DataFrame(records, columns=columns)


def _render_drift_alerts() -> None:
    drifts = services.program_drift()
    if not drifts:
        return
    st.error(f"⚠️ 发现 {len(drifts)} 台设备程序版本漂移 / 校验异常，请确认设备当前程序：")
    frame = pd.DataFrame(
        [
            {
                "设备": item["device_id"],
                "产品": item["product"],
                "绑定版本": item["program_version"],
                "设备上报版本": item.get("reported_version") or "",
                "告警原因": item["drift_reason"],
                "上报时间": common.local_time(item.get("reported_at")),
            }
            for item in drifts
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch")


def _render_editor() -> None:
    bindings = services.list_bindings()
    frame = _display_frame(bindings)
    readonly_columns = [
        "设备上报版本",
        "上报校验和",
        "生产状态",
        "最后拉取时间",
        "更新时间",
    ]
    editor = st.data_editor(
        frame,
        key="program_editor",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        disabled=readonly_columns if common.can_edit() else list(frame.columns),
        column_config={
            "设备标识": st.column_config.TextColumn("设备标识", required=True, width="small"),
            "产品型号": st.column_config.TextColumn("产品型号", required=True, width="small"),
            "程序版本": st.column_config.TextColumn("程序版本", required=True, width="small"),
            "下载 URL": st.column_config.TextColumn("下载 URL", width="large"),
            "SHA256": st.column_config.TextColumn("SHA256（64 位十六进制）", width="medium"),
            "设备上报版本": st.column_config.TextColumn("设备上报版本", width="small"),
            "上报校验和": st.column_config.TextColumn("上报校验和", width="small"),
            "生产状态": st.column_config.TextColumn("生产状态", width="small"),
            "最后拉取时间": st.column_config.TextColumn("最后拉取", width="medium"),
            "更新时间": st.column_config.TextColumn("更新时间", width="medium"),
        },
    )

    left, right = st.columns([1, 3])
    if left.button(
        "💾 保存绑定关系",
        type="primary",
        disabled=not common.can_edit(),
        help="保存后设备下次 GET /api/program 即拿到新版本",
    ):
        rows = []
        for record in editor.to_dict("records"):
            values = {key: _cell(record.get(column)) for column, key in EDIT_MAP.items()}
            if not any(values.values()):
                continue
            rows.append(values)
        try:
            count = services.replace_bindings(rows)
        except ServiceError as exc:
            st.error(str(exc))
        else:
            common.flash("success", f"已保存 {count} 条绑定关系，设备下次拉取时生效。")
            st.rerun()
    right.caption("删除行后保存即解除绑定；修改后无需重启服务，设备下次拉取即生效。")


def _render_publish_form() -> None:
    st.subheader("发布程序文件（可选）")
    st.caption(
        "上传后自动保存到静态目录、计算 SHA256 并更新绑定；"
        "若程序已存放在对象存储，可直接在上表填写下载 URL 和 SHA256。"
    )
    with st.form("program_publish", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        device = col1.text_input("设备标识", key="publish_device", disabled=not common.can_edit())
        product = col2.text_input("产品型号", key="publish_product", disabled=not common.can_edit())
        version = col3.text_input("程序版本", key="publish_version", disabled=not common.can_edit())
        upload = st.file_uploader(
            "程序文件", key="publish_file", disabled=not common.can_edit()
        )
        submitted = st.form_submit_button(
            "发布并更新绑定", type="primary", disabled=not common.can_edit()
        )
    if not submitted:
        return
    if upload is None:
        st.error("请选择要上传的程序文件")
        return
    try:
        result = services.publish_program_file(
            device_id=device,
            product=product,
            program_version=version,
            filename=upload.name,
            content=upload.getvalue(),
        )
    except ServiceError as exc:
        st.error(str(exc))
    else:
        common.flash(
            "success",
            f"已发布 {device}/{product} {version}，SHA256={result['sha256'][:16]}…",
        )
        st.rerun()


def _render_logs() -> None:
    with st.expander("设备拉取记录（最近 30 条）"):
        pulls = services.list_program_pulls(30)
        if pulls:
            frame = pd.DataFrame(
                [
                    {
                        "时间": common.local_time(item["pulled_at"]),
                        "设备": item["device_id"],
                        "产品": item["product"],
                        "程序版本": item["program_version"],
                        "SHA256": (item["sha256"] or "")[:16] + "…",
                    }
                    for item in pulls
                ]
            )
            st.dataframe(frame, hide_index=True, width="stretch")
        else:
            st.caption("暂无拉取记录。")

    with st.expander("设备状态上报记录（最近 30 条）"):
        reports = services.list_program_status_logs(30)
        if reports:
            frame = pd.DataFrame(
                [
                    {
                        "时间": common.local_time(item["reported_at"]),
                        "设备": item["device_id"],
                        "产品": item["product"] or "",
                        "上报版本": item["reported_version"] or "",
                        "可信": "是" if item["trusted"] else "否",
                        "原因": item["reason"] or "",
                    }
                    for item in reports
                ]
            )
            st.dataframe(frame, hide_index=True, width="stretch")
        else:
            st.caption("暂无上报记录。")


def _render_api_help() -> None:
    base = common.api_base()
    with st.expander("设备侧接口调用示例"):
        st.code(
            f"""# 1) 拉取程序元数据（同时写入拉取记录）
curl "{base}/api/program?device_id=TEST-01&product=P-1001"

# 2) 上报已加载版本与校验结果
curl -X POST "{base}/api/program/status" \\
  -H "Content-Type: application/json" \\
  -d '{{"device_id":"TEST-01","product":"P-1001","program_version":"v1.2.0","sha256":"<64位sha256>","sha256_ok":true}}'
""",
            language="bash",
        )


def render() -> None:
    st.title("📦 程序下发")
    st.caption("设备-产品-程序版本绑定；设备拉取记录与版本漂移告警。保存后设备下次拉取即生效。")
    common.render_flash()
    common.render_readonly_notice()
    _render_drift_alerts()

    bindings = services.list_bindings()
    drifts = services.program_drift()
    col1, col2, col3 = st.columns(3)
    col1.metric("绑定关系", len(bindings))
    col2.metric("版本漂移告警", len(drifts))
    col3.metric(
        "可生产设备", sum(1 for item in bindings if _production_status(item) == "可生产")
    )

    st.subheader("绑定关系")
    _render_editor()
    st.divider()
    _render_publish_form()
    st.divider()
    _render_logs()
    _render_api_help()
