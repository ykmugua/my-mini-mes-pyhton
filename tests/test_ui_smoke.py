"""Streamlit 页面冒烟测试（AppTest）。

覆盖：主入口与四个页面可渲染、漂移告警展示、只读权限、
页面内解锁流程、页面内新增变量。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from py_server import services

UI_DIR = Path(__file__).resolve().parent / "ui_apps"
MAIN_APP = Path(__file__).resolve().parents[1] / "src" / "py_server" / "streamlit_app.py"


def _run(page_file: str | Path) -> AppTest:
    at = AppTest.from_file(str(page_file), default_timeout=90)
    at.run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_main_app_renders_with_drift_alert(seeded):
    at = _run(MAIN_APP)
    assert at.title[0].value == "📦 程序下发"
    assert any("版本漂移" in item.value for item in at.error)


def test_program_page_editor_and_metrics(seeded):
    at = _run(UI_DIR / "program_app.py")
    labels = [metric.label for metric in at.metric]
    assert labels == ["绑定关系", "版本漂移告警", "可生产设备"]
    assert at.metric[0].value == "5"
    buttons = {button.label: button for button in at.button}
    assert buttons["💾 保存绑定关系"].disabled is False
    assert buttons["发布并更新绑定"].disabled is False


def test_readonly_role_disables_editing(seeded):
    at = AppTest.from_file(str(UI_DIR / "program_app.py"), default_timeout=90)
    at.session_state["mes_role"] = "只读"
    at.run()
    assert not at.exception
    assert all(button.disabled for button in at.button)


def test_interlock_unlock_from_page(seeded):
    at = _run(UI_DIR / "interlock_app.py")
    locked_before = services.list_locked_workpieces()
    assert locked_before
    at.text_input(key="unlock_operator").input("测试员")
    at.text_input(key="unlock_reason").input("返修后复测确认放行")
    at.checkbox(key="unlock_confirm").check()
    at.button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert len(services.list_locked_workpieces()) == len(locked_before) - 1
    logs = services.list_unlock_logs()
    assert logs and logs[0]["operator"] == "测试员"
    assert logs[0]["reason"] == "返修后复测确认放行"


def test_dashboard_metrics_and_untrusted_warning(seeded):
    at = _run(UI_DIR / "dashboard_app.py")
    labels = [metric.label for metric in at.metric]
    assert labels == ["今日测试总数", "PASS", "FAIL", "合格率（可信数据）"]
    assert int(at.metric[0].value) > 0
    assert any("不可信" in item.value for item in at.warning)


def test_variables_add_from_page(seeded):
    at = _run(UI_DIR / "variables_app.py")
    at.text_input(key="new_var_name").input("ui_ready")
    at.selectbox(key="new_var_type").select("bool")
    at.text_input(key="new_var_value").input("true")
    at.button[0].click().run()
    assert not at.exception, [str(item.value) for item in at.exception]
    assert services.get_variable("ui_ready")["value"] is True
