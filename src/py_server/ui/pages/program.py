"""程序注册页面：维护程序主数据与版本。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from . import _common as master
from .. import client
from .constants import (
    ACTIVE_PROGRAMS_SECTION,
    CREATE_PROGRAM_BUTTON,
    CREATE_PROGRAM_SECTION,
    PROGRAM_HISTORY_MANAGEMENT_SECTION,
    PROGRAM_HISTORY_SECTION,
    PROGRAM_VERSIONS_SECTION,
    SAVE_PROGRAM_BUTTON,
    SAVE_VERSION_DESCRIPTION_BUTTON,
)

from ._mock_program_data import (
    available_program_versions,
    enabled_steps,
    next_program_id,
    program_version_description,
    step_by_no,
    step_label,
)

PULL_LOG_COLUMNS = ["时间", "设备", "产品", "程序版本", "SHA256"]
STATUS_LOG_COLUMNS = ["时间", "设备", "产品", "上报版本", "可信", "原因"]
COLUMN_ORDER_LOCK_SCRIPT = """
<script>
(() => {
  let attempts = 0;

  const attachColumnOrderLock = () => {
    const scope = document.querySelector(".st-key-program_list_panel");
    const scroller = scope?.querySelector(".dvn-scroller");
    if (!scroller) {
      if (attempts++ < 40) {
        window.setTimeout(attachColumnOrderLock, 50);
      }
      return;
    }
    if (scroller.dataset.columnOrderLocked === "true") {
      return;
    }
    scroller.dataset.columnOrderLocked = "true";

    let dragStart = null;
    let dragMoved = false;
    let suppressClick = false;

    scroller.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) {
        return;
      }
      const rect = scroller.getBoundingClientRect();
      const inHeader = event.clientY - rect.top <= 42;
      const isResizeHandle = scroller.style.cursor === "col-resize";
      dragStart = inHeader && !isResizeHandle
        ? { x: event.clientX, y: event.clientY }
        : null;
      dragMoved = false;
    }, true);

    scroller.addEventListener("pointermove", (event) => {
      if (!dragStart) {
        return;
      }
      if (Math.hypot(event.clientX - dragStart.x, event.clientY - dragStart.y) > 4) {
        dragMoved = true;
      }
      if (dragMoved) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);

    const finishPointerInteraction = (event) => {
      if (dragStart && dragMoved) {
        suppressClick = true;
      }
      dragStart = null;
      dragMoved = false;
    };
    scroller.addEventListener("pointerup", finishPointerInteraction, true);
    scroller.addEventListener("pointercancel", finishPointerInteraction, true);
    scroller.addEventListener("click", (event) => {
      if (suppressClick) {
        event.preventDefault();
        event.stopImmediatePropagation();
        suppressClick = false;
      }
    }, true);
  };

  attachColumnOrderLock();
})();
</script>
"""


def _text(value: Any) -> str:
    """执行 text。"""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _integer(value: Any) -> int | None:
    """执行 integer。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None




def _pull_log_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """执行 pull_log_frame。"""
    rows = []
    for item in records:
        sha256 = _text(item.get("sha256"))
        rows.append(
            {
                "时间": _text(item.get("pulled_at")),
                "设备": _text(item.get("device_id")),
                "产品": _text(item.get("product")),
                "程序版本": _text(item.get("program_version")),
                "SHA256": f"{sha256[:16]}…" if sha256 else "",
            }
        )
    return pd.DataFrame(rows, columns=PULL_LOG_COLUMNS)


def _status_log_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """执行 status_log_frame。"""
    rows = []
    for item in records:
        rows.append(
            {
                "时间": _text(item.get("reported_at")),
                "设备": _text(item.get("device_id")),
                "产品": _text(item.get("product")),
                "上报版本": _text(item.get("reported_version")),
                "可信": "是" if item.get("trusted") else "否",
                "原因": _text(item.get("reason")),
            }
        )
    return pd.DataFrame(rows, columns=STATUS_LOG_COLUMNS)


def _validate_program_rows(
    rows: list[dict[str, Any]],
    current: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    version_options: list[str],
    program_versions: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
    str | None,
]:
    """执行 validate_program_rows。"""
    current_by_id = {int(item["program_id"]): item for item in current}
    valid_steps = {str(item["step_no"]) for item in steps}
    updated: list[dict[str, Any]] = []
    updated_versions = [{**item} for item in program_versions]
    used_names: set[str] = set()

    for row in rows:
        program_id = _integer(row.get("program_id"))
        if program_id is None:
            continue
        program = current_by_id.get(program_id)
        if program is None:
            return None, None, "程序记录已变化，请刷新页面后重试"

        name = _text(row.get("程序名"))
        version = _text(row.get("版本"))
        step_no = _text(row.get("所属工序"))
        sha_display = _text(row.get("SHA256"))
        if not name or not version:
            return None, None, "程序名和程序版本不能为空"
        if version not in version_options:
            return None, None, "请选择有效的程序版本"
        if step_no not in valid_steps:
            return None, None, "请选择有效的所属工序"
        if name.casefold() in used_names:
            return None, None, "程序名不能重复"
        used_names.add(name.casefold())

        original_sha = str(program["sha256"])
        sha256 = original_sha if sha_display == original_sha[:16] else sha_display
        if not sha256:
            return None, None, "SHA256 不能为空"

        entered_description = _text(row.get("版本说明"))
        if version != str(program["program_version"]):
            version_description = program_version_description(
                current, program_versions, program_id, version
            ) or entered_description
        else:
            version_description = entered_description

        _upsert_version_description(
            updated_versions, program_id, version, version_description
        )

        updated.append(
            {
                **program,
                "program_name": name,
                "program_version": version,
                "sha256": sha256,
                "step_no": str(step_no),
                "version_description": version_description,
            }
        )

    if not updated:
        return None, None, "至少需要保留一条程序记录"
    return updated, updated_versions, None


def _upsert_version_description(
    program_versions: list[dict[str, Any]],
    program_id: int | str,
    version: str,
    description: str,
    sha256: str = "",
    download_url: str = "",
) -> None:
    """执行 upsert_version_description。"""
    for item in program_versions:
        if (
            str(item["program_id"]) == str(program_id)
            and item["program_version"] == version
        ):
            item["version_description"] = description
            if sha256:
                item["sha256"] = sha256
            if download_url:
                item["download_url"] = download_url
            return
    program_versions.append(
        {
            "program_id": program_id,
            "program_version": version,
            "version_description": description,
            "sha256": sha256,
            "download_url": download_url,
        }
    )


def _read_components(edited: pd.DataFrame) -> list[str]:
    """执行 read_components。"""
    return [
        component_no
        for value in edited.get("component_no", pd.Series(dtype="string")).tolist()
        if (component_no := _text(value))
    ]





def _render_program_history(read_only: bool, programs: list[dict]) -> None:
    """程序历史管理：选择程序名，列表按新→老展示版本，可删除指定版本。"""
    st.subheader(PROGRAM_HISTORY_MANAGEMENT_SECTION)
    pending = st.session_state.get("pending_history_program_delete")
    if pending:
        _confirm_delete_history_version(pending)
        return
    names = sorted({p["program_name"] for p in programs})
    if not names:
        st.info("暂无程序，请先上传程序")
        return
    selected = st.selectbox("选择程序名", names, key="history_program_name")
    history = client.program_history(selected)
    if not history:
        st.info("该程序暂无版本记录")
        return
    frame = pd.DataFrame([
        {
            "版本": item["program_version"],
            "版本说明": item.get("version_description") or "",
            "SHA256": (item.get("sha256") or "")[:16] + "…",
            "所属工序": str(item.get("step_no") or ""),
            "下载地址": item.get("download_url") or "",
        }
        for item in history
    ])
    st.dataframe(frame, hide_index=True, width="stretch", alt="程序历史版本列表")
    if read_only:
        return
    ids = [item["program_id"] for item in history]
    versions = [item["program_version"] for item in history]
    choice = st.selectbox(
        "选择要删除的版本",
        options=ids,
        format_func=lambda pid: next(
            (f"{v}（ID {pid}）" for p, v in zip(ids, versions) if p == pid),
            str(pid),
        ),
        key="history_delete_choice",
    )
    if st.button("删除该版本", type="secondary", icon=":material/delete:", key="history_delete_btn"):
        st.session_state["pending_history_program_delete"] = {
            "program_id": choice,
            "program_name": selected,
            "version": next(
                (v for p, v in zip(ids, versions) if p == choice),
                str(choice),
            ),
        }


def render_page() -> None:
    """程序注册页：新增 / 当前运行程序 / 历史程序。"""
    master.ensure_master_data()
    read_only = st.session_state.get("role", "工程师") == "只读"
    programs: list[dict[str, Any]] = st.session_state.programs
    program_versions: list[dict[str, Any]] = st.session_state.program_versions
    version_options = available_program_versions(programs, program_versions)

    # -------------------------------------------------------------------------
    # 区块 1：新增程序（折叠表单）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        with st.expander(CREATE_PROGRAM_SECTION, expanded=False):
            submitted = False
            if read_only:
                st.info("只读角色不可新增程序。")
            else:
                with st.form("program_upload_form", clear_on_submit=False, border=False):
                    # 第一行：程序名 + 程序版本
                    name_col, version_col = st.columns(2)
                    program_name = name_col.text_input(
                        "程序名", key="upload_program_name", placeholder="例如 TEST_MAIN",
                    )
                    program_version = version_col.text_input(
                        "程序版本", key="upload_program_version", placeholder="例如 v1.2.0",
                    )
                    # 第二行：版本说明 + 启用
                    desc_col, enabled_col = st.columns([3, 1])
                    version_description = desc_col.text_input(
                        "版本说明", key="upload_version_description",
                        placeholder="例如：修复型号切换后的参数缓存",
                    )
                    enabled_text = enabled_col.selectbox(
                        "启用", options=["是", "否"], key="upload_enabled_text",
                    )
                    # 程序文件
                    uploaded_file = st.file_uploader(
                        "程序文件", type=["zip", "7z"], accept_multiple_files=False,
                        key="upload_program_file",
                    )
                    submitted = st.form_submit_button(CREATE_PROGRAM_BUTTON)

                if submitted:
                    clean_name = program_name.strip()
                    clean_version = program_version.strip()
                    if not clean_name or not clean_version:
                        st.error("程序名和程序版本不能为空")
                    elif uploaded_file is None:
                        st.error("请选择要上传的程序文件")
                    else:
                        suffix = Path(uploaded_file.name).suffix.lower()
                        if suffix not in {".zip", ".7z"}:
                            st.error("仅支持 .zip 或 .7z 文件")
                        elif any(
                            item["program_name"].casefold() == clean_name.casefold()
                            for item in programs
                        ):
                            st.error("程序名已存在，请使用唯一的程序名")
                        else:
                            digest = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
                            program_id = next_program_id(programs)
                            programs.append({
                                "program_id": program_id,
                                "program_name": clean_name,
                                "program_version": clean_version,
                                "version_description": version_description.strip(),
                                "sha256": digest,
                                "download_url": (
                                    "http://192.168.1.50:8000/programs/"
                                    f"{clean_name}_{clean_version}{suffix}"
                                ),
                                "step_no": "",
                                "enabled": enabled_text == "是",
                            })
                            st.session_state.programs = programs
                            master.save_key("programs")
                            _upsert_version_description(
                                program_versions, program_id, clean_version,
                                version_description.strip(), digest,
                                f"http://192.168.1.50:8000/programs/{clean_name}_{clean_version}{suffix}",
                            )
                            st.session_state.program_versions = program_versions
                            master.save_key("program_versions")
                            st.toast("程序已新增")
                            st.rerun()
            st.caption("仅支持 `.zip` 或 `.7z` 压缩包；上传后计算 SHA256 并自动生成下载地址。")

    # -------------------------------------------------------------------------
    # 区块 2：当前运行程序（每行一个程序名，勾选后查看历史/编辑）
    # -------------------------------------------------------------------------
    with st.container(border=True, key="program_list_panel"):
        st.subheader(ACTIVE_PROGRAMS_SECTION)
        latest_by_name: dict[str, dict[str, Any]] = {}
        for program in programs:
            name = program["program_name"]
            existing = latest_by_name.get(name)
            if existing is None or str(program["program_version"]) > str(existing["program_version"]):
                latest_by_name[name] = program
        latest_programs = sorted(latest_by_name.values(), key=lambda p: p["program_name"])
        names = [p["program_name"] for p in latest_programs]
        st.session_state["_program_names"] = names

        def _version_meta(prog: dict[str, Any], version: str) -> tuple[str, str, str]:
            """执行 version_meta。"""
            for v in program_versions:
                if str(v["program_id"]) == str(prog["program_id"]) and v["program_version"] == version:
                    return (
                        v.get("version_description", ""),
                        str(v.get("sha256") or prog.get("sha256", ""))[:16],
                        v.get("download_url") or prog.get("download_url", ""),
                    )
            return (prog.get("version_description", ""), str(prog.get("sha256", ""))[:16], prog.get("download_url", ""))

        frame = pd.DataFrame([{
            "选择": p["program_name"] == st.session_state.get("program_selected_name"),
            "程序名": p["program_name"],
            "版本": p["program_version"],
            "启用": bool(p.get("enabled", True)),
            "版本说明": _version_meta(p, p["program_version"])[0],
            "SHA256": _version_meta(p, p["program_version"])[1],
            "下载地址": _version_meta(p, p["program_version"])[2],
            "删除": "删除",
        } for p in latest_programs], columns=["选择", "程序名", "版本", "启用", "版本说明", "SHA256", "下载地址", "删除"])
        column_config = {
            "选择": st.column_config.CheckboxColumn("选择", default=False, width="small",
                                                   help="勾选后查看该程序历史版本并编辑"),
            "程序名": st.column_config.TextColumn("程序名", required=True, width="medium"),
            "版本": st.column_config.SelectboxColumn("版本", options=version_options, required=True, width="small"),
            "启用": st.column_config.CheckboxColumn("启用", default=True, width="small"),
            "版本说明": st.column_config.TextColumn("版本说明", width="large"),
            "SHA256": st.column_config.TextColumn("SHA256", disabled=True, width="medium"),
            "下载地址": st.column_config.LinkColumn("下载地址", display_text="下载", disabled=True, width="small"),
            "删除": st.column_config.ButtonColumn(
                "删除", type="tertiary", on_click=_request_program_delete,
                key="program_delete_click", width="small",
            ),
        }
        edited_programs: pd.DataFrame | None = None
        if read_only:
            st.dataframe(frame.drop(columns=["删除"]), column_config=column_config,
                         hide_index=True, width="stretch", alt="当前运行程序列表")
        else:
            edited_programs = st.data_editor(
                frame, column_config=column_config, hide_index=True, num_rows="fixed",
                width="stretch", alt="当前运行程序编辑器", key="program_editor",
                on_change=_on_program_editor_change,
            )
            # 只有"选择"列被编辑时才同步选中程序，避免改版本/启用时丢失编辑状态
            editor_state = st.session_state.get("program_editor")
            edits = editor_state.get("edited_rows", {}) if isinstance(editor_state, dict) else {}
            selection_edited = any("选择" in ch for ch in edits.values())
            if selection_edited:
                checked = [str(row["程序名"]) for _, row in edited_programs.iterrows() if bool(row.get("选择"))]
                cur = st.session_state.get("program_selected_name")
                if checked and cur != checked[0]:
                    st.session_state["program_selected_name"] = checked[0]
                    st.rerun()
                elif not checked and cur:
                    st.session_state.pop("program_selected_name", None)
                    st.rerun()
        # 直接保存列表里的编辑
        if edited_programs is not None and not read_only:
            with st.container(horizontal=True, horizontal_alignment="left"):
                if st.button(SAVE_PROGRAM_BUTTON, icon=":material/save:", key="save_program_edits"):
                    updated = []
                    rename_error = ""
                    for index, row in edited_programs.iterrows():
                        original = latest_programs[index]
                        name = str(row["程序名"]).strip()
                        version = str(row["版本"])
                        desc = str(row["版本说明"] or "")
                        enabled = bool(row["启用"])
                        if not name:
                            rename_error = "程序名不能为空"
                            break
                        q = dict(original)
                        q["program_name"] = name
                        if q["program_version"] == version:
                            q["version_description"] = desc
                            meta = next(
                                (v for v in program_versions
                                 if str(v["program_id"]) == str(q["program_id"])
                                 and v["program_version"] == version), None,
                            )
                            if meta:
                                q["sha256"] = meta.get("sha256") or q["sha256"]
                                q["download_url"] = meta.get("download_url") or q["download_url"]
                        q["enabled"] = enabled
                        updated.append(q)
                    if rename_error:
                        st.error(rename_error)
                    else:
                        st.session_state.programs = updated
                        master.save_key("programs")
                        st.toast("程序修改已保存")
                        st.rerun()

        # 删除程序（最后一列按钮触发，弹框确认）
        pending = st.session_state.get("pending_program_delete")
        if pending:
            target = next((q for q in programs if q["program_name"] == pending), None)
            if target is None:
                _clear_pending_program_delete()
            else:
                _confirm_delete_program(target)

        st.html(COLUMN_ORDER_LOCK_SCRIPT, unsafe_allow_javascript=True)
    # -------------------------------------------------------------------------
    # 区块 3：历史程序（勾选当前运行程序后显示其所有历史版本，新→老）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader(PROGRAM_VERSIONS_SECTION)
        selected = st.session_state.get("program_selected_name")
        if not names:
            st.info("暂无程序，请先在上方新增")
        elif not selected or selected not in names:
            st.info("请勾选上方“当前运行程序”左侧的下发勾选框查看历史程序")
        else:
                # 该程序的所有版本（新→老），来自 program_versions（历史版本库）
                prog_ids = {
                    str(p["program_id"]) for p in programs if p["program_name"] == selected
                }
                version_items = [
                    v for v in program_versions if str(v["program_id"]) in prog_ids
                ]
                versions = sorted(
                    version_items,
                    key=lambda v: str(v["program_version"]), reverse=True,
                )
                hist_frame = pd.DataFrame([{
                    "版本": v["program_version"],
                    "版本说明": v.get("version_description", ""),
                    "SHA256": str(v.get("sha256", ""))[:16],
                    "下载地址": v.get("download_url", ""),
                    "删除": "删除",
                } for v in versions], columns=["版本", "版本说明", "SHA256", "下载地址", "删除"])
                hist_config = {
                    "版本": st.column_config.TextColumn("版本", disabled=True),
                    "版本说明": st.column_config.TextColumn("版本说明", width="large"),
                    "SHA256": st.column_config.TextColumn("SHA256", disabled=True),
                    "下载地址": st.column_config.LinkColumn("下载地址", display_text="下载", disabled=True),
                    "删除": st.column_config.ButtonColumn(
                        "删除", type="tertiary", on_click=_request_program_version_delete,
                        key="program_version_delete_click", width="small",
                    ),
                }
                st.session_state["_program_version_names"] = [p["program_version"] for p in versions]
                st.session_state["_program_version_program"] = selected
                if read_only:
                    st.dataframe(
                        hist_frame.drop(columns=["删除"]), hide_index=True,
                        width="stretch", alt="历史程序版本列表",
                    )
                else:
                    edited_hist = st.data_editor(
                        hist_frame, column_config=hist_config, hide_index=True,
                        num_rows="fixed", width="stretch", alt="历史程序版本编辑器",
                        key="program_history_editor",
                    )
                    if st.button(SAVE_VERSION_DESCRIPTION_BUTTON, key="save_program_versions"):
                        descs = dict(zip(edited_hist["版本"], edited_hist["版本说明"]))
                        for p in programs:
                            if p["program_name"] == selected and p["program_version"] in descs:
                                p["version_description"] = descs[p["program_version"]]
                        st.session_state.programs = programs
                        master.save_key("programs")
                        for item in program_versions:
                            pid = next(
                                (q["program_id"] for q in programs
                                 if q["program_name"] == selected and q["program_version"] == item["program_version"]),
                                None,
                            )
                            if pid is not None and item["program_version"] in descs:
                                item["version_description"] = descs[item["program_version"]]
                        st.session_state.program_versions = program_versions
                        master.save_key("program_versions")
                        st.toast("版本说明已保存")
                        st.rerun()
                    pending_ver = st.session_state.get("pending_program_version_delete")
                    if pending_ver:
                        _confirm_delete_program_version(selected, pending_ver)


def _sync_program_selection(edited: pd.DataFrame | None, names: list[str]) -> None:
    """根据 data_editor 当前“下发”列值同步 program_selected_name。"""
    if edited is None or "下发" not in edited.columns:
        return
    checked = [
        str(row["程序名"]) for _, row in edited.iterrows() if bool(row.get("下发"))
    ]
    current = st.session_state.get("program_selected_name")
    if checked:
        if current != checked[0]:
            st.session_state["program_selected_name"] = checked[0]
            st.rerun()
    elif current:
        st.session_state.pop("program_selected_name", None)
        st.rerun()


def _on_program_editor_change() -> None:
    """“选择”列单选：勾一行时自动取消其他行的勾选。"""
    edited = st.session_state.get("program_editor")
    if not isinstance(edited, dict):
        return
    edits = edited.get("edited_rows", {})
    names = st.session_state.get("_program_names", [])
    picked = None
    for row_idx, ch in edits.items():
        if ch.get("选择") is True and 0 <= int(row_idx) < len(names):
            picked = int(row_idx)
    if picked is None:
        return
    # 取消其他行的选择（保留其他字段的编辑）
    for i in range(len(names)):
        if i != picked and "选择" not in edits.get(i, {}):
            edits.setdefault(i, {})["选择"] = False
    st.session_state["program_selected_name"] = names[picked]


def _request_program_delete() -> None:
    """执行 request_program_delete。"""
    click = st.session_state.get("program_delete_click")
    if click is None:
        return
    row = int(click["row"])
    names = st.session_state.get("_program_names", [])
    if 0 <= row < len(names):
        st.session_state["pending_program_delete"] = names[row]


def _request_program_version_delete() -> None:
    """执行 request_program_version_delete。"""
    click = st.session_state.get("program_version_delete_click")
    if click is None:
        return
    row = int(click["row"])
    versions = st.session_state.get("_program_version_names", [])
    if 0 <= row < len(versions):
        st.session_state["pending_program_version_delete"] = versions[row]


def _clear_pending_program_delete() -> None:
    """执行 clear_pending_program_delete。"""
    st.session_state.pop("pending_program_delete", None)


@st.dialog("确认删除程序", icon=":material/delete_forever:", on_dismiss=_clear_pending_program_delete)
def _confirm_delete_program(prog: dict[str, Any]) -> None:
    """执行 confirm_delete_program。"""
    name = prog["program_name"]
    st.write(f"确定删除程序 **{name}** 及其所有版本吗？")
    st.caption("删除后该程序的版本记录将一并移除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_program"):
            _clear_pending_program_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_program"):
            st.session_state.programs = [q for q in st.session_state.programs if q["program_name"] != name]
            master.save_key("programs")
            st.session_state.program_versions = [
                v for v in st.session_state.get("program_versions", [])
                if str(v["program_id"]) != str(prog["program_id"])
            ]
            master.save_key("program_versions")
            st.session_state.pop("program_selected_name", None)
            _clear_pending_program_delete()
            st.toast(f"已删除程序 {name}")
            st.rerun()


def _clear_pending_history_program_delete() -> None:
    """执行 clear_pending_history_program_delete。"""
    st.session_state.pop("pending_history_program_delete", None)


@st.dialog("确认删除程序版本", icon=":material/delete_forever:", on_dismiss=_clear_pending_history_program_delete)
def _confirm_delete_history_version(pending: dict[str, Any]) -> None:
    """执行 confirm_delete_history_version。"""
    st.write(f"确定删除程序 **{pending['program_name']}** 的版本 **{pending['version']}** 吗？")
    st.caption("删除后该历史版本记录将被移除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_history_version"):
            _clear_pending_history_program_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_history_version"):
            try:
                client.delete_program_version(pending["program_id"])
            except Exception as exc:
                st.error(f"删除失败：{exc}")
                return
            _clear_pending_history_program_delete()
            st.toast("已删除该版本程序")
            st.rerun()


def _clear_pending_program_version_delete() -> None:
    """执行 clear_pending_program_version_delete。"""
    st.session_state.pop("pending_program_version_delete", None)


@st.dialog("确认删除程序版本", icon=":material/delete_forever:", on_dismiss=_clear_pending_program_version_delete)
def _confirm_delete_program_version(program_name: str, version: str) -> None:
    """执行 confirm_delete_program_version。"""
    st.write(f"确定删除程序 **{program_name}** 的版本 **{version}** 吗？")
    st.caption("删除后该版本记录将从程序和版本库中一并移除。")
    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("取消", key="cancel_delete_program_version"):
            _clear_pending_program_version_delete()
            st.rerun()
        if st.button("确认删除", type="primary", key="confirm_delete_program_version"):
            program_ids = {
                str(p["program_id"]) for p in st.session_state.programs
                if p["program_name"] == program_name
            }
            st.session_state.programs = [
                p for p in st.session_state.programs
                if not (p["program_name"] == program_name and p["program_version"] == version)
            ]
            st.session_state.program_versions = [
                v for v in st.session_state.program_versions
                if not (
                    str(v["program_id"]) in program_ids
                    and v["program_version"] == version
                )
            ]
            master.save_key("programs")
            master.save_key("program_versions")
            _clear_pending_program_version_delete()
            st.toast(f"已删除版本 {version}")
            st.rerun()
