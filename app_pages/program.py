"""程序注册页面：维护程序主数据与版本。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app_pages._mock_program_data import (
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
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _integer(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None




def _component_frame(component_nos: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"component_no": pd.Series(component_nos, dtype="string")})


def _pull_log_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
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
    return [
        component_no
        for value in edited.get("component_no", pd.Series(dtype="string")).tolist()
        if (component_no := _text(value))
    ]


read_only = st.session_state.get("role", "工程师") == "只读"
steps: list[dict[str, Any]] = st.session_state.steps
active_steps = enabled_steps(steps)
programs: list[dict[str, Any]] = st.session_state.programs
program_versions: list[dict[str, Any]] = st.session_state.program_versions
program_pulls: list[dict[str, Any]] = st.session_state.program_pulls[:30]
program_status_logs: list[dict[str, Any]] = st.session_state.program_status_logs[:30]
version_options = available_program_versions(programs, program_versions)


def render_page() -> None:
    """程序注册页：新增 / 当前运行程序 / 历史程序。"""
    read_only = st.session_state.get("role", "工程师") == "只读"
    programs: list[dict[str, Any]] = st.session_state.programs
    program_versions: list[dict[str, Any]] = st.session_state.program_versions
    version_options = available_program_versions(programs, program_versions)

    st.title("📦 程序注册")


    # -------------------------------------------------------------------------
    # 区块 1：新增（风格与组件注册一致）
    # -------------------------------------------------------------------------
    st.subheader("新增")
    if read_only:
        with st.expander("新增", expanded=False):
            st.info("只读角色不可上传程序。")
    else:
        with st.expander("新增", expanded=False):
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
                # 添加按钮
                submitted = st.form_submit_button("添加程序")

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
                        pass
                        _upsert_version_description(
                            program_versions, program_id, clean_version,
                            version_description.strip(), digest,
                            f"http://192.168.1.50:8000/programs/{clean_name}_{clean_version}{suffix}",
                        )
                        st.session_state.program_versions = program_versions
                        pass
                        st.toast("程序已添加")
                        st.rerun()
        st.caption("仅支持 `.zip` 或 `.7z` 压缩包；上传后计算 SHA256 并自动生成下载地址。")

    # -------------------------------------------------------------------------
    # 区块 2：当前运行程序（每行一个程序名，勾选后查看历史/编辑）
    # -------------------------------------------------------------------------
    with st.container(border=True, key="program_list_panel"):
        st.subheader("当前运行程序")
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
            for v in program_versions:
                if str(v["program_id"]) == str(prog["program_id"]) and v["program_version"] == version:
                    return (
                        v.get("version_description", ""),
                        str(v.get("sha256") or prog.get("sha256", ""))[:16],
                        v.get("download_url") or prog.get("download_url", ""),
                    )
            return (prog.get("version_description", ""), str(prog.get("sha256", ""))[:16], prog.get("download_url", ""))

        frame = pd.DataFrame([{
            "程序名": p["program_name"],
            "版本": p["program_version"],
            "版本说明": _version_meta(p, p["program_version"])[0],
            "SHA256": _version_meta(p, p["program_version"])[1],
            "下载地址": _version_meta(p, p["program_version"])[2],
            "启用": "是" if p.get("enabled", True) else "否",
        } for p in latest_programs], columns=["程序名", "版本", "版本说明", "SHA256", "下载地址", "启用"])
        event = st.dataframe(
            frame, hide_index=True, width="stretch", height=260,
            alt="当前运行程序列表（点击行查看历史并编辑）",
            on_select="rerun", selection_mode="single-row",
            key="program_list_select",
        )
        rows = event.selection.rows if hasattr(event, "selection") else []
        if rows:
            selected = names[rows[0]]
            if st.session_state.get("program_selected_name") != selected:
                st.session_state["program_selected_name"] = selected
                st.rerun()
        elif st.session_state.get("program_selected_name"):
            st.session_state.pop("program_selected_name", None)
            st.rerun()

        # 选中程序的编辑区
        selected_prog_name = st.session_state.get("program_selected_name")
        if selected_prog_name and selected_prog_name in names:
            prog = latest_by_name[selected_prog_name]
            st.caption(f"编辑当前运行程序：**{selected_prog_name}**")
            edit_col1, edit_col2 = st.columns(2)
            with edit_col1:
                current_ver = str(prog["program_version"])
                ver_list = [
                    v["program_version"] for v in program_versions
                    if str(v["program_id"]) == str(prog["program_id"])
                ]
                if current_ver not in ver_list:
                    ver_list.insert(0, current_ver)
                chosen_ver = st.selectbox(
                    "版本", options=ver_list,
                    index=ver_list.index(current_ver) if current_ver in ver_list else 0,
                    key="edit_program_version",
                )
            with edit_col2:
                meta_desc, meta_sha, meta_url = _version_meta(prog, chosen_ver)
                st.text_input("SHA256（当前版本）", value=meta_sha, disabled=True, key="edit_program_sha")
            edited_desc = st.text_input(
                "版本说明", value=meta_desc, key="edit_program_desc",
            )
            st.markdown(f"**下载地址：** {meta_url}")
            edit_enabled = st.selectbox(
                "启用", options=["是", "否"],
                index=0 if prog.get("enabled", True) else 1,
                key="edit_program_enabled",
            )
            if not read_only:
                ecol1, ecol2 = st.columns(2)
                with ecol1:
                    if st.button("保存程序修改", icon=":material/save:", key="save_program_edits"):
                        updated = []
                        for p in programs:
                            q = dict(p)
                            if p["program_name"] == selected_prog_name:
                                q["program_version"] = chosen_ver
                                q["version_description"] = edited_desc
                                q["enabled"] = edit_enabled == "是"
                                meta = next(
                                    (v for v in program_versions
                                     if str(v["program_id"]) == str(q["program_id"])
                                     and v["program_version"] == chosen_ver), None,
                                )
                                if meta:
                                    q["sha256"] = meta.get("sha256") or q["sha256"]
                                    q["download_url"] = meta.get("download_url") or q["download_url"]
                            updated.append(q)
                        st.session_state.programs = updated
                        pass
                        st.toast("程序已保存")
                        st.rerun()
                with ecol2:
                    if st.button("删除该程序", icon=":material/delete:", key="delete_program_btn"):
                        st.session_state["pending_program_delete"] = selected_prog_name
                        st.rerun()
            pending = st.session_state.pop("pending_program_delete", None)
            if pending:
                remaining = [p for p in st.session_state.programs if p["program_name"] != pending]
                remaining_ids = {str(p["program_id"]) for p in remaining}
                st.session_state.programs = remaining
                pass
                pass
                st.session_state.pop("program_selected_name", None)
                st.toast(f"已删除程序 {pending}")
                st.rerun()

        st.html(COLUMN_ORDER_LOCK_SCRIPT, unsafe_allow_javascript=True)
    # -------------------------------------------------------------------------
    # 区块 3：历史程序（勾选当前运行程序后显示其所有历史版本，新→老）
    # -------------------------------------------------------------------------
    with st.container(border=True):
        st.subheader("历史程序")
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
                    if st.button("保存版本说明", key="save_program_versions"):
                        descs = dict(zip(edited_hist["版本"], edited_hist["版本说明"]))
                        for p in programs:
                            if p["program_name"] == selected and p["program_version"] in descs:
                                p["version_description"] = descs[p["program_version"]]
                        st.session_state.programs = programs
                        pass
                        for item in program_versions:
                            pid = next(
                                (q["program_id"] for q in programs
                                 if q["program_name"] == selected and q["program_version"] == item["program_version"]),
                                None,
                            )
                            if pid is not None and item["program_version"] in descs:
                                item["version_description"] = descs[item["program_version"]]
                        st.session_state.program_versions = program_versions
                        pass
                        st.toast("版本说明已保存")
                        st.rerun()
                    pending_ver = st.session_state.pop("pending_program_version_delete", None)
                    if pending_ver:
                        # 删除该程序名的指定版本
                        st.session_state.programs = [
                            p for p in st.session_state.programs
                            if not (p["program_name"] == selected and p["program_version"] == pending_ver)
                        ]
                        st.session_state.program_versions = [
                            v for v in st.session_state.program_versions
                            if not (
                                str(v["program_id"]) in {
                                    str(p["program_id"]) for p in st.session_state.programs
                                    if p["program_name"] == selected and p["program_version"] == pending_ver
                                }
                            )
                        ]
                        pass
                        pass
                        st.toast(f"已删除版本 {pending_ver}")
                        st.rerun()


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
    """勾选“下发”列后立即刷新历史程序。"""
    edited = st.session_state.get("program_editor")
    if not edited:
        return
    edits = edited.get("edited_rows", {}) if isinstance(edited, dict) else {}
    names = st.session_state.get("_program_names", [])
    current = st.session_state.get("program_selected_name")
    for row_idx, changes in edits.items():
        if "下发" not in changes or not (0 <= int(row_idx) < len(names)):
            continue
        name = names[int(row_idx)]
        if changes["下发"] is True:
            if current != name:
                st.session_state["program_selected_name"] = name
                return
        elif changes["下发"] is False and current == name:
            st.session_state.pop("program_selected_name", None)
            return


def _request_program_delete() -> None:
    click = st.session_state.get("program_delete_click")
    if click is None:
        return
    row = int(click["row"])
    names = st.session_state.get("_program_names", [])
    if 0 <= row < len(names):
        st.session_state["pending_program_delete"] = names[row]


def _request_program_version_delete() -> None:
    click = st.session_state.get("program_version_delete_click")
    if click is None:
        return
    row = int(click["row"])
    versions = st.session_state.get("_program_version_names", [])
    if 0 <= row < len(versions):
        st.session_state["pending_program_version_delete"] = versions[row]

render_page()
