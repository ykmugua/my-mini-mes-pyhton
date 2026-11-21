"""组件注册 + 工艺配置页面测试（新工艺结构）。"""
from __future__ import annotations

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


def _open_product(at: AppTest) -> AppTest:
    at.switch_page("app_pages/product_management.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def _open_process(at: AppTest) -> AppTest:
    at.switch_page("app_pages/process_config.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_product_page_renders_sections() -> None:
    at = _open_product(_run())
    assert at.title[0].value == "📋 组件注册"
    assert [x.value for x in at.subheader] == ["新增组件", "组件列表"]
    frame = at.data_editor[0].value
    assert list(frame.columns) == ["组件号", "组件名称", "启用", "备注", "删除"]
    assert set(frame["组件号"]) >= {"P-1001", "P-1002"}


def test_add_product_form_appends_product() -> None:
    at = _open_product(_run())
    at.text_input(key="new_product_name").input("显示面板")
    at.text_input(key="new_product_model").input("P-1003")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    last = at.session_state["products"][-1]
    assert last["product_model"] == "P-1003"
    assert last["product_name"] == "显示面板"
    assert "process_code" not in last


def test_add_product_rejects_duplicate() -> None:
    at = _open_product(_run())
    at.text_input(key="new_product_model").input("P-1001")
    at.text_input(key="new_product_name").input("重复组件")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert [e.value for e in at.error] == ["组件号不能重复"]


def test_process_page_renders_list() -> None:
    at = _open_process(_run())
    assert at.title[0].value == "⚙️ 工艺配置"
    editor = at.data_editor(key="process_editor")
    frame = editor.value
    assert list(frame.columns) == ["选择", "工艺号", "工艺名称", "绑定组件", "启用", "来源工艺", "备注", "删除"]
    assert set(frame["工艺号"]) >= {"PROC-001", "PROC-002"}
    cfg = json.loads(editor.proto.columns)
    assert cfg["选择"]["type_config"]["type"] == "checkbox"
    assert cfg["启用"]["type_config"]["type"] == "checkbox"
    assert any(b.key == "save_processes" for b in at.button)
    assert not any(b.key == "delete_process_btn" for b in at.button)
    assert not any("编辑当前工艺" in e.label for e in at.expander)


def test_process_derive_deep_copies_routes_and_resources() -> None:
    at = _open_process(_run())
    at.text_input(key="new_process_code").input("PROC-003")
    at.text_input(key="new_process_name").input("派生工艺")
    at.selectbox(key="new_process_source").select("PROC-001")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    procs = at.session_state["processes"]
    assert any(p["process_code"] == "PROC-003" and p["source_process_code"] == "PROC-001" for p in procs)
    routes = [r for r in at.session_state["process_routes"] if r["process_code"] == "PROC-003"]
    resources = [r for r in at.session_state["process_step_resources"] if r["process_code"] == "PROC-003"]
    assert len(routes) == 3
    assert len(resources) == 3
    assert all(r["process_code"] == "PROC-003" for r in routes)
    # 深拷贝：源工艺不受影响
    assert len([r for r in at.session_state["process_routes"] if r["process_code"] == "PROC-001"]) == 3


def test_process_detail_shows_on_selection() -> None:
    at = _open_process(_run())
    at.session_state["process_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert any("工艺详情：PROC-001" in x.value for x in at.subheader)
    assert any(e.key == "route_editor_PROC-001" for e in at.data_editor)
    assert any(e.key == "res_editor_PROC-001" for e in at.data_editor)


def test_process_resources_use_models() -> None:
    at = _open_process(_run())
    at.session_state["process_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    res = next(e for e in at.data_editor if e.key == "res_editor_PROC-001")
    assert list(res.value.columns) == ["工序", "程序", "可执行设备型号", "转运载具型号", "删除"]
    cfg = json.loads(res.proto.columns)
    assert cfg["可执行设备型号"]["type_config"]["type"] == "multiselect"
    assert cfg["转运载具型号"]["type_config"]["type"] == "multiselect"


def test_readonly_disables_process_editing() -> None:
    at = _open_process(_run())
    at.radio(key="role").set_value("只读").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert not [b for b in at.button if b.key == "save_process_routes"]


def test_process_detail_delete_route_and_resource_use_dialogs() -> None:
    at = _open_process(_run())
    at.session_state["process_editor"] = {"edited_rows": {0: {"选择": True}}}
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]

    at.session_state["pending_route_delete"] = {
        "process_code": "PROC-001",
        "step_no": at.session_state["process_routes"][0]["step_no"],
    }
    at.run()
    assert any(b.key == "confirm_delete_route" for b in at.button)
    assert any(b.key == "confirm_delete_route" for b in at.button)
    at.button(key="confirm_delete_route").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(
        not (r["process_code"] == "PROC-001" and r["step_no"] == "S1")
        for r in at.session_state["process_routes"]
    )

    at.session_state["pending_resource_delete"] = {
        "process_code": "PROC-001",
        "step_no": at.session_state["process_step_resources"][0]["step_no"],
    }
    at.run()
    assert any(b.key == "confirm_delete_resource" for b in at.button)
    before = len(at.session_state["process_step_resources"])
    at.button(key="confirm_delete_resource").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert len(at.session_state["process_step_resources"]) == before - 1
