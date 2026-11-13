"""设备注册占位页面测试。"""

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


def test_device_registration_renders_three_sections() -> None:
    at = _open_page(_run())

    assert at.title[0].value == "🖥️ 设备注册"
    assert [item.value for item in at.subheader] == [
        "线体管理",
        "新增设备",
        "设备列表",
    ]
    assert len(at.data_editor) == 2

    line_frame = at.data_editor[0].value
    assert list(line_frame.columns) == ["线体编号", "线体名称", "删除"]
    assert line_frame["线体编号"].tolist() == ["L1", "L2"]
    line_config = json.loads(at.data_editor[0].proto.columns)
    assert line_config["线体编号"]["disabled"] is True
    assert line_config["删除"]["type_config"]["type"] == "button"

    device_frame = at.data_editor[1].value
    assert list(device_frame.columns) == [
        "设备编号",
        "设备名称",
        "所属线体",
        "所属工序",
        "启用",
        "备注",
        "删除",
    ]
    assert set(device_frame["设备编号"]) == {
        "TEST-01",
        "TEST-01B",
        "TEST-02",
        "TEST-02B",
        "TEST-03",
        "TEST-03B",
        "TEST-04",
    }

    device_config = json.loads(at.data_editor[1].proto.columns)
    assert device_config["所属线体"]["type_config"]["type"] == "selectbox"
    assert device_config["所属工序"]["type_config"]["type"] == "selectbox"
    assert device_config["启用"]["type_config"]["type"] == "checkbox"
    assert device_config["删除"]["type_config"]["type"] == "button"
    for column in ("设备编号", "设备名称", "备注"):
        assert device_config[column]["disabled"] is True
    assert "disabled" not in device_config["所属线体"]
    assert "disabled" not in device_config["所属工序"]
    assert "disabled" not in device_config["启用"]


def test_add_line_form_appends_line() -> None:
    at = _open_page(_run())
    at.text_input(key="new_line_id").input("L3")
    at.text_input(key="new_line_name").input("三线")
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["lines"][-1] == {
        "line_id": "L3",
        "line_name": "三线",
    }


def test_add_line_rejects_duplicate_id() -> None:
    at = _open_page(_run())
    at.text_input(key="new_line_id").input("L1")
    at.text_input(key="new_line_name").input("重复线体")
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["线体编号不能重复"]


def test_line_editor_saves_name() -> None:
    at = _open_page(_run())
    at.session_state["line_editor"] = {
        "edited_rows": {0: {"线体名称": "一号线"}}
    }
    at.run()
    at.button(key="save_lines").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["lines"][0] == {
        "line_id": "L1",
        "line_name": "一号线",
    }


def test_delete_line_with_devices_is_blocked() -> None:
    at = _open_page(_run())
    at.session_state["pending_line_delete"] = "L1"
    at.run()
    at.button(key="confirm_delete_line").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any(
        "该线体下还有" in item.value and "台设备" in item.value
        for item in at.error
    )
    assert any(line["line_id"] == "L1" for line in at.session_state["lines"])


def test_delete_unreferenced_line_succeeds() -> None:
    at = _run()
    at.session_state["lines"].append({"line_id": "L3", "line_name": "三线"})
    at = _open_page(at)
    at.session_state["pending_line_delete"] = "L3"
    at.run()
    at.button(key="confirm_delete_line").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(line["line_id"] != "L3" for line in at.session_state["lines"])


def test_add_device_form_appends_device() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-05")
    at.text_input(key="new_device_name").input("包装检测机")
    at.selectbox(key="new_device_line_id").select("L2")
    at.selectbox(key="new_device_step_no").select(2)
    at.checkbox(key="new_device_enabled").check()
    at.text_input(key="new_device_remark").input("二线设备")
    at.form_submit_button[1].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["devices"][-1] == {
        "device_id": "TEST-05",
        "device_name": "包装检测机",
        "line_id": "L2",
        "step_no": 2,
        "enabled": True,
        "remark": "二线设备",
    }


def test_add_device_rejects_duplicate_id() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-01")
    at.text_input(key="new_device_name").input("另一台设备")
    at.selectbox(key="new_device_line_id").select("L1")
    at.selectbox(key="new_device_step_no").select(1)
    at.form_submit_button[1].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["设备编号不能重复"]


def test_add_device_rejects_empty_name() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-05")
    at.selectbox(key="new_device_line_id").select("L1")
    at.selectbox(key="new_device_step_no").select(1)
    at.form_submit_button[1].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["设备编号和设备名称不能为空"]


def test_add_device_requires_line_and_step() -> None:
    at = _open_page(_run())
    at.text_input(key="new_device_id").input("TEST-05")
    at.text_input(key="new_device_name").input("包装检测机")
    at.form_submit_button[1].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["所属线体必须选择已有线体"]


def test_device_editor_saves_line_step_and_enabled() -> None:
    at = _open_page(_run())
    at.session_state["device_editor"] = {
        "edited_rows": {
            0: {"所属线体": "L2", "所属工序": 2, "启用": False}
        }
    }
    at.run()
    at.button(key="save_devices").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["devices"][0]["line_id"] == "L2"
    assert at.session_state["devices"][0]["step_no"] == 2
    assert at.session_state["devices"][0]["enabled"] is False


def test_device_save_rejects_unknown_line() -> None:
    at = _run()
    at.session_state["devices"][0]["line_id"] = "L9"
    at = _open_page(at)
    at.button(key="save_devices").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["所属线体必须选择已有线体"]


def test_device_save_rejects_disabled_step() -> None:
    at = _run()
    at.session_state["devices"][0]["step_no"] = 4
    at = _open_page(at)
    at.button(key="save_devices").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["所属工序必须选择启用中的工序"]


def test_delete_device_dialog_confirms_deletion() -> None:
    at = _open_page(_run())
    at.session_state["pending_device_delete"] = "TEST-01"
    at.run()
    dialog_texts = [item.value for item in at.markdown] + [
        item.value for item in at.caption
    ]
    assert any("未配置设备" in text for text in dialog_texts)
    at.button(key="confirm_delete_device").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(
        device["device_id"] != "TEST-01"
        for device in at.session_state["devices"]
    )


def test_no_lines_disables_add_device() -> None:
    at = _run()
    at.session_state["lines"] = []
    at = _open_page(at)

    assert "请先在线体管理区块添加线体" in [
        item.value for item in at.warning
    ]
    assert at.selectbox(key="new_device_line_id").options == []
    assert at.selectbox(key="new_device_line_id").disabled is True
    assert at.form_submit_button[1].disabled is True


def test_no_enabled_steps_disables_add_device() -> None:
    at = _run()
    for step in at.session_state["steps"]:
        step["enabled"] = False
    at = _open_page(at)

    assert "请先在工序注册页添加并启用工序" in [
        item.value for item in at.warning
    ]
    assert at.selectbox(key="new_device_step_no").options == []
    assert at.selectbox(key="new_device_step_no").disabled is True
    assert at.form_submit_button[1].disabled is True


def test_empty_device_table_keeps_columns() -> None:
    at = _run()
    at.session_state["devices"] = []
    at = _open_page(at)

    assert "暂无设备，请新增" in [item.value for item in at.info]
    assert list(at.data_editor[1].value.columns) == [
        "设备编号",
        "设备名称",
        "所属线体",
        "所属工序",
        "启用",
        "备注",
        "删除",
    ]


def test_empty_line_table_keeps_columns() -> None:
    at = _run()
    at.session_state["lines"] = []
    at = _open_page(at)

    assert "暂无线体，请新增" in [item.value for item in at.info]
    assert list(at.data_editor[0].value.columns) == [
        "线体编号",
        "线体名称",
        "删除",
    ]


def test_readonly_device_page_disables_editing() -> None:
    at = _run()
    at.session_state["role"] = "只读"
    at = _open_page(at)

    assert not at.data_editor
    assert not at.button
    assert len(at.dataframe) == 2
