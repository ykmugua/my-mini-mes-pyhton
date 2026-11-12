"""程序下发页面：全部读写均使用 st.session_state 占位数据。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app_pages._mock_program_data import (
    available_program_versions,
    next_program_id,
    program_component_count,
    program_select_label,
    program_type,
    program_version_description,
    step_by_no,
    step_label,
)

PROGRAM_COLUMNS = [
    "program_id",
    "程序名",
    "所属工序",
    "版本",
    "版本说明",
    "SHA256",
    "下载 URL",
    "关联型号数",
    "程序类型",
]
COMPONENT_WARNING_KEY = "program_components_warning"
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


def _program_frame(
    programs: list[dict[str, Any]],
    program_components: list[dict[str, Any]],
) -> pd.DataFrame:
    records = []
    for program in programs:
        component_count = program_component_count(
            program["program_id"], program_components
        )
        records.append(
            {
                "program_id": program["program_id"],
                "程序名": program["program_name"],
                "所属工序": program["step_no"],
                "版本": program["program_version"],
                "版本说明": program.get("version_description", ""),
                "SHA256": program["sha256"][:16],
                "下载 URL": program["download_url"],
                "关联型号数": component_count,
                "程序类型": program_type(component_count),
            }
        )
    return pd.DataFrame(records, columns=PROGRAM_COLUMNS)


def _program_config(
    line_steps: list[dict[str, Any]], version_options: list[str]
) -> dict[str, Any]:
    return {
        "program_id": None,
        "程序名": st.column_config.TextColumn("程序名", required=True, width="medium"),
        "所属工序": st.column_config.SelectboxColumn(
            "所属工序",
            options=[int(step["step_no"]) for step in line_steps],
            format_func=lambda step_no: step_label(line_steps, step_no),
            required=True,
            width="medium",
        ),
        "版本": st.column_config.SelectboxColumn(
            "版本",
            options=version_options,
            required=True,
            width="small",
        ),
        "版本说明": st.column_config.TextColumn(
            "版本说明", width="large"
        ),
        "SHA256": st.column_config.TextColumn(
            "SHA256",
            help="列表显示 SHA256 的前 16 位。",
            required=True,
            width="medium",
        ),
        "下载 URL": st.column_config.LinkColumn(
            "下载 URL",
            display_text="下载程序",
            disabled=True,
            width=110,
        ),
        "关联型号数": st.column_config.NumberColumn(
            "关联型号数",
            disabled=True,
            format="%d",
            width=70,
        ),
        "程序类型": st.column_config.TextColumn(
            "程序类型", disabled=True, width="small"
        ),
    }


def _component_frame(component_nos: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"component_no": pd.Series(component_nos, dtype="string")})


def _validate_program_rows(
    rows: list[dict[str, Any]],
    current: list[dict[str, Any]],
    line_steps: list[dict[str, Any]],
    version_options: list[str],
    program_versions: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
    str | None,
]:
    current_by_id = {int(item["program_id"]): item for item in current}
    valid_steps = {int(item["step_no"]) for item in line_steps}
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
        step_no = _integer(row.get("所属工序"))
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
                "step_no": step_no,
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
) -> None:
    for item in program_versions:
        if (
            str(item["program_id"]) == str(program_id)
            and item["program_version"] == version
        ):
            item["version_description"] = description
            return
    program_versions.append(
        {
            "program_id": program_id,
            "program_version": version,
            "version_description": description,
        }
    )


def _read_components(edited: pd.DataFrame) -> list[str]:
    return [
        component_no
        for value in edited.get("component_no", pd.Series(dtype="string")).tolist()
        if (component_no := _text(value))
    ]


read_only = st.session_state.get("role", "工程师") == "只读"
line_steps: list[dict[str, Any]] = st.session_state.line_steps
programs: list[dict[str, Any]] = st.session_state.programs
program_versions: list[dict[str, Any]] = st.session_state.program_versions
program_components: list[dict[str, Any]] = st.session_state.program_components
version_options = available_program_versions(programs, program_versions)

st.title("📦 程序下发")
st.caption("程序文件与型号关联。本页面使用 session state 占位数据。")

saved_warning = st.session_state.pop(COMPONENT_WARNING_KEY, None)
if saved_warning:
    st.warning(saved_warning)


# -----------------------------------------------------------------------------
# 区块 1：上传程序文件
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("上传程序文件")
    if read_only:
        with st.expander("上传程序文件", expanded=False):
            st.info("只读角色不可上传程序。")
    else:
        with st.expander("上传程序文件", expanded=False):
            with st.form("program_upload_form", clear_on_submit=False):
                name_col, version_col, step_col = st.columns([2, 1, 2])
                program_name = name_col.text_input(
                    "程序名",
                    key="upload_program_name",
                    placeholder="例如 TEST_MAIN",
                )
                program_version = version_col.text_input(
                    "程序版本",
                    key="upload_program_version",
                    placeholder="例如 v1.2.0",
                )
                step_no = step_col.selectbox(
                    "所属工序",
                    options=[int(step["step_no"]) for step in line_steps],
                    format_func=lambda value: step_label(
                        line_steps, value, include_device=True
                    ),
                    key="upload_step_no",
                )
                uploaded_file = st.file_uploader(
                    "程序文件",
                    type=["zip", "7z"],
                    accept_multiple_files=False,
                    key="upload_program_file",
                )
                version_description = st.text_input(
                    "版本说明",
                    key="upload_version_description",
                    placeholder="例如：修复型号切换后的参数缓存",
                )
                submitted = st.form_submit_button("上传并保存")

            if submitted:
                clean_name = program_name.strip()
                clean_version = program_version.strip()
                if not clean_name or not clean_version:
                    st.error("程序名和程序版本不能为空")
                elif step_by_no(line_steps, step_no) is None:
                    st.error("请选择有效的所属工序")
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
                        programs.append(
                            {
                                "program_id": program_id,
                                "program_name": clean_name,
                                "program_version": clean_version,
                                "version_description": version_description.strip(),
                                "sha256": digest,
                                "download_url": (
                                    "http://192.168.1.50:8000/programs/"
                                    f"{clean_name}_{clean_version}{suffix}"
                                ),
                                "step_no": int(step_no),
                            }
                        )
                        st.session_state.programs = programs
                        _upsert_version_description(
                            program_versions,
                            program_id,
                            clean_version,
                            version_description.strip(),
                        )
                        st.session_state.program_versions = program_versions
                        st.toast(
                            "程序已上传（模拟），请前往型号关联区块添加型号"
                        )
                        st.rerun()

    st.caption(
        "仅支持 `.zip` 或 `.7z` 压缩包。工序选项来自线体工序配置。"
        "上传后系统会计算 SHA256 并自动生成下载地址。"
    )


# -----------------------------------------------------------------------------
# 区块 2：程序运行列表
# -----------------------------------------------------------------------------
with st.container(border=True, key="program_list_panel"):
    st.subheader("程序运行列表")
    save_program_clicked = False
    if not read_only:
        with st.container(horizontal=True, horizontal_alignment="right"):
            save_program_clicked = st.button(
                "保存程序修改",
                icon=":material/save:",
                disabled=not programs,
                key="save_program_edits",
            )

    edited_programs: pd.DataFrame | None = None
    program_frame = _program_frame(programs, program_components)
    if read_only:
        st.dataframe(
            program_frame,
            column_config=_program_config(line_steps, version_options),
            column_order=PROGRAM_COLUMNS[1:],
            hide_index=True,
            width="stretch",
            alt="程序运行列表",
        )
    else:
        edited_programs = st.data_editor(
            program_frame,
            column_config=_program_config(line_steps, version_options),
            column_order=PROGRAM_COLUMNS[1:],
            disabled=[
                column for column in PROGRAM_COLUMNS[1:] if column != "版本"
            ],
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            alt="程序运行列表编辑器",
            key="program_editor",
        )
    if not programs:
        st.info("暂无记录")

    st.html(
        COLUMN_ORDER_LOCK_SCRIPT,
        unsafe_allow_javascript=True,
    )

    if save_program_clicked and edited_programs is not None:
        rows = edited_programs.to_dict("records")
        updated_programs, updated_versions, error = _validate_program_rows(
            rows, programs, line_steps, version_options, program_versions
        )
        if error:
            st.error(error)
        else:
            st.session_state.programs = updated_programs
            st.session_state.program_versions = updated_versions
            st.toast("已保存")
            st.rerun()


# -----------------------------------------------------------------------------
# 区块 3：型号关联
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("型号关联")
    if not programs:
        st.info("暂无程序，请先上传程序文件。")
    else:
        selected_program_id = st.selectbox(
            "选择程序",
            options=[int(item["program_id"]) for item in programs],
            format_func=lambda item: program_select_label(
                next(
                    program
                    for program in programs
                    if int(program["program_id"]) == int(item)
                ),
                line_steps,
            ),
            key="component_program_id",
        )
        selected_components = [
            str(item["component_no"])
            for item in program_components
            if int(item["program_id"]) == int(selected_program_id)
        ]

        component_editor_key = f"component_editor_{selected_program_id}"
        edited_components: pd.DataFrame | None = None
        if read_only:
            st.dataframe(
                _component_frame(selected_components),
                column_config={"component_no": "型号 / 组件号"},
                hide_index=True,
                width="stretch",
                alt="当前程序的型号关联",
            )
        else:
            edited_components = st.data_editor(
                _component_frame(selected_components),
                column_config={
                    "component_no": st.column_config.TextColumn(
                        "型号 / 组件号",
                        required=True,
                        width="medium",
                    )
                },
                hide_index=True,
                num_rows="dynamic",
                width="stretch",
                alt="当前程序的型号关联编辑器",
                key=component_editor_key,
            )
        if not selected_components:
            st.info("暂无记录")

        if not read_only and st.button(
            "保存型号关联",
            icon=":material/save:",
            key="save_component_links",
        ):
            new_components = _read_components(edited_components)
            if len(new_components) != len(set(new_components)):
                st.error("同一程序下型号不能重复")
            else:
                retained = [
                    item
                    for item in program_components
                    if int(item["program_id"]) != int(selected_program_id)
                ]
                retained.extend(
                    {
                        "program_id": int(selected_program_id),
                        "component_no": component_no,
                    }
                    for component_no in new_components
                )
                st.session_state.program_components = retained
                if not new_components:
                    st.session_state[COMPONENT_WARNING_KEY] = (
                        "未关联型号的程序无法被产品工序使用"
                    )
                st.toast("型号关联已保存")
                st.rerun()
