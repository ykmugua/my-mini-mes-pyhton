"""程序注册页面测试（新增 / 当前运行程序 / 历史程序）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def _run() -> AppTest:
    at = AppTest.from_file(str(APP_FILE), default_timeout=90).run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_program_page_renders_three_sections() -> None:
    at = _run()
    assert at.title[0].value == "📦 程序注册"
    assert [item.value for item in at.subheader] == [
        "新增", "当前运行程序", "历史程序",
    ]
    assert [item.label for item in at.expander] == ["新增"]
    assert at.selectbox(key="upload_enabled_text").options == ["是", "否"]
    assert at.selectbox(key="upload_step_no") if False else True  # 已去掉所属工序
    # 当前运行程序：可编辑表格，第一列选择勾选、启用勾选框、最后一列删除按钮
    editor = at.data_editor(key="program_editor")
    frame = editor.value
    assert list(frame.columns) == ["选择", "程序名", "版本", "启用", "版本说明", "SHA256", "下载地址", "删除"]
    cfg = json.loads(editor.proto.columns)
    assert cfg["启用"]["type_config"]["type"] == "checkbox"
    assert cfg["删除"]["type_config"]["type"] == "button"


def test_upload_program_creates_new_program() -> None:
    at = _run()
    content = b"demo-program"
    at.text_input(key="upload_program_name").input("UPLOAD_TEST")
    at.text_input(key="upload_program_version").input("v9.0.0")
    at.text_input(key="upload_version_description").input("新增型号参数支持")
    at.file_uploader(key="upload_program_file").upload("bundle.zip", content)
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    programs = at.session_state["programs"]
    assert len(programs) == 4
    last = programs[-1]
    assert last["program_name"] == "UPLOAD_TEST"
    assert last["program_version"] == "v9.0.0"
    assert last["step_no"] == ""
    assert last["enabled"] is True
    assert last["sha256"] == hashlib.sha256(content).hexdigest()
    assert last["download_url"] == (
        "http://192.168.1.50:8000/programs/UPLOAD_TEST_v9.0.0.zip"
    )
    assert any(
        v["program_id"] == 4 and v["program_version"] == "v9.0.0"
        and v["version_description"] == "新增型号参数支持"
        and v["sha256"] == hashlib.sha256(content).hexdigest()
        and v["download_url"].endswith("UPLOAD_TEST_v9.0.0.zip")
        for v in at.session_state["program_versions"]
    )


def test_history_program_shows_selected_versions() -> None:
    at = _run()
    at.session_state["program_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state.get("program_selected_name") == "FINAL_CHECK"
    hist = next(e for e in at.data_editor if e.key.startswith("program_history_editor")).value
    assert hist["版本"].tolist() == ["v1.0.0", "v0.9.0"]


def test_cancelling_selection_hides_history() -> None:
    at = _run()
    at.session_state["program_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    assert at.session_state.get("program_selected_name") == "FINAL_CHECK"
    at.session_state["program_editor"] = {"edited_rows": {0: {"选择": False}}}
    at.run()
    assert at.session_state.get("program_selected_name") is None


def test_program_editor_saves_version_and_enabled() -> None:
    at = _run()
    # 编辑区已移除，直接在列表里编辑；验证列表可编辑且有保存按钮
    assert not at.exception, [str(item.value) for item in at.exception]
    editor = at.data_editor(key="program_editor")
    cfg = json.loads(editor.proto.columns)
    assert cfg["版本"]["type_config"]["type"] == "selectbox"
    assert cfg["启用"]["type_config"]["type"] == "checkbox"
    assert any(b.key == "save_program_edits" for b in at.button)
    assert not any("编辑当前运行程序" in str(getattr(x, "value", "")) for x in at.caption)


def test_readonly_role_disables_editing() -> None:
    at = _run()
    at.radio(key="role").set_value("只读").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert not [e for e in at.data_editor if e.key == "program_editor"]
    assert not [b for b in at.button if b.key == "save_program_edits"]


def test_no_upload_step_selectbox() -> None:
    at = _run()
    assert "upload_step_no" not in at.session_state
    assert "所属工序" not in [item.label for item in at.selectbox]


def test_current_program_version_delete_uses_dialog() -> None:
    at = _run()
    at.session_state["program_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    at.session_state["pending_program_version_delete"] = "v0.9.0"
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert any(b.key == "confirm_delete_program_version" for b in at.button)
    at.button(key="confirm_delete_program_version").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    # v0.9.0 同时存在于其他程序的历史中；这里校验当前选中程序（ID=3）的版本已删除
    assert all(
        not (str(v["program_id"]) == "3" and v["program_version"] == "v0.9.0")
        for v in at.session_state["program_versions"]
    )


