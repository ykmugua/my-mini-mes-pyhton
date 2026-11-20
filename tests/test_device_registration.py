"""设备注册页面测试（单线，无线体）。"""
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


def _open_page(at: AppTest) -> AppTest:
    at.switch_page("app_pages/device_registration.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_device_registration_renders_sections() -> None:
    at = _open_page(_run())
    assert at.title[0].value == "🖥️ 设备注册"
    assert [item.value for item in at.subheader] == ["设备管理（可直接修改，改完点“保存设备修改”）", "设备列表"]
    assert len(at.data_editor) == 1
    frame = at.data_editor[0].value
    assert list(frame.columns) == ["设备编号", "设备名称", "设备型号", "启用", "备注", "删除"]
    assert set(frame["设备编号"]) == {
        "TEST-01", "TEST-01B", "TEST-02", "TEST-02B", "TEST-03", "TEST-03B", "TEST-04",
    }
    cfg = json.loads(at.data_editor[0].proto.columns)
    for column in ("设备编号", "设备名称", "设备型号", "启用", "备注"):
        assert "disabled" not in cfg[column]


def test_add_device_form_appends_device() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-05")
    at.text_input(key="new_device_name").input("包装检测机")
    at.text_input(key="new_device_model").input("DM-200")
    at.text_input(key="new_device_remark").input("新设备")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["devices"][-1] == {
        "device_id": "TEST-05", "device_name": "包装检测机",
        "device_model": "DM-200", "enabled": True, "remark": "新设备",
    }


def test_add_device_rejects_duplicate_id() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-01")
    at.text_input(key="new_device_name").input("另一台设备")
    at.text_input(key="new_device_model").input("DM-999")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["设备编号不能重复"]


def test_add_device_rejects_empty_fields() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-05")
    at.form_submit_button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["设备编号、设备名称和设备型号不能为空"]


def test_device_editor_saves_model_and_enabled() -> None:
    at = _open_page(_run())
    at.session_state["device_editor"] = {
        "edited_rows": {0: {"设备型号": "DM-NEW", "启用": False}}
    }
    at.run()
    at.button(key="save_devices").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["devices"][0]["device_model"] == "DM-NEW"
    assert at.session_state["devices"][0]["enabled"] is False


def test_delete_device_dialog_confirms_deletion() -> None:
    at = _open_page(_run())
    at.session_state["pending_device_delete"] = "TEST-01"
    at.run()
    at.button(key="confirm_delete_device").click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(d["device_id"] != "TEST-01" for d in at.session_state["devices"])


def test_empty_device_table_keeps_columns() -> None:
    at = _open_page(_run())
    at.session_state["devices"] = []
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert list(at.data_editor[0].value.columns) == [
        "设备编号", "设备名称", "设备型号", "启用", "备注", "删除",
    ]


def test_readonly_device_page_disables_editing() -> None:
    at = _open_page(_run())
    at.radio(key="role").set_value("只读").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert not at.data_editor
