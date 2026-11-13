"""工序注册占位页面测试。"""

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
    at.switch_page("app_pages/step_registration.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_step_registration_renders_editor() -> None:
    at = _open_page(_run())

    assert at.title[0].value == "🧱 工序注册"
    assert [item.value for item in at.subheader] == ["新增工序", "工序列表"]
    assert len(at.data_editor) == 1
    assert list(at.data_editor[0].value.columns) == [
        "工序号",
        "工序名",
        "启用",
        "备注",
        "删除",
    ]
    assert len(at.data_editor[0].value) == 4
    column_config = json.loads(at.data_editor[0].proto.columns)
    assert column_config["启用"]["type_config"]["type"] == "checkbox"
    assert column_config["启用"]["default"] is True
    assert column_config["删除"]["type_config"]["type"] == "button"
    for column in ("工序号", "工序名", "备注"):
        assert column_config[column]["disabled"] is True
    assert "disabled" not in column_config["启用"]


def test_new_step_form_adds_step() -> None:
    at = _open_page(_run())
    at.text_input(key="new_step_no").input("5")
    at.text_input(key="new_step_name").input("包装检查")
    at.checkbox(key="new_step_enabled").check()
    at.text_input(key="new_step_remark").input("出货包装确认")
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["steps"][-1] == {
        "step_no": 5,
        "step_name": "包装检查",
        "enabled": True,
        "remark": "出货包装确认",
    }


def test_step_save_updates_only_enabled() -> None:
    at = _open_page(_run())
    at.session_state["step_editor"] = {
        "edited_rows": {0: {"启用": False}}
    }
    at.run()
    at.button(key="save_steps").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["steps"][0] == {
        "step_no": 1,
        "step_name": "上电测试",
        "enabled": False,
        "remark": "首站上电与基础安全检查",
    }


def test_delete_dialog_confirms_deletion() -> None:
    at = _open_page(_run())
    at.session_state["pending_step_delete"] = 1
    at.run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any("确定删除工序" in item.value for item in at.markdown)
    at.button(key="confirm_delete_step").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(step["step_no"] != 1 for step in at.session_state["steps"])


def test_step_number_must_be_unique() -> None:
    at = _run()
    at.session_state["steps"].append(
        {
            "step_no": 1,
            "step_name": "重复工序",
            "enabled": True,
            "remark": "",
        }
    )
    at = _open_page(at)

    at.button(key="save_steps").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["工序号不能重复"]


def test_step_name_must_be_unique() -> None:
    at = _run()
    at.session_state["steps"].append(
        {
            "step_no": 99,
            "step_name": "上电测试",
            "enabled": True,
            "remark": "",
        }
    )
    at = _open_page(at)

    at.button(key="save_steps").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["工序名不能重复"]


def test_empty_step_table_keeps_columns() -> None:
    at = _run()
    at.session_state["steps"] = []
    at = _open_page(at)

    assert [item.value for item in at.info] == ["暂无工序，请新增"]
    assert list(at.data_editor[0].value.columns) == [
        "工序号",
        "工序名",
        "启用",
        "备注",
        "删除",
    ]


def test_readonly_role_disables_step_editor() -> None:
    at = _run()
    at.session_state["role"] = "只读"
    at = _open_page(at)

    assert not at.data_editor
    assert not at.button
    assert len(at.dataframe) == 1
