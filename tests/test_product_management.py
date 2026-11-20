"""组件注册与工艺配置页面测试。"""

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
    at.switch_page("app_pages/product_management.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def _open_process_page(at: AppTest) -> AppTest:
    at.switch_page("app_pages/process_config.py").run()
    assert not at.exception, [str(item.value) for item in at.exception]
    return at


def test_product_page_renders_two_sections() -> None:
    at = _open_page(_run())

    assert at.title[0].value == "📋 组件注册"
    assert [item.value for item in at.subheader] == [
        "新增组件",
        "组件列表",
    ]
    assert len(at.data_editor) == 1

    product_config = json.loads(at.data_editor[0].proto.columns)
    assert product_config["组件号"]["disabled"] is True
    assert product_config["删除"]["type_config"]["type"] == "button"
    assert list(at.data_editor[0].value.columns) == [
        "组件号",
        "组件名称",
        "启用",
        "备注",
        "删除",
    ]


def test_process_page_renders_three_sections() -> None:
    at = _open_process_page(_run())

    assert at.title[0].value == "⚙️ 工艺配置"
    assert [item.value for item in at.subheader] == [
        "产品型号工序流程",
        "为型号分配设备",
        "为型号分配载具",
        "型号关联",
        "设备读写记录",
    ]
    assert len(at.data_editor) == 2
    assert at.selectbox(key="selected_product").value == "P-1001"
    assert at.selectbox(key="assign_step").value == "1"
    assert at.multiselect(key="assign_P-1001_1").value == [
        "TEST-01",
        "TEST-01B",
    ]
    assert "product_step_configs" not in at.session_state
    assert all(
        "line_id" not in item
        for item in at.session_state["product_step_devices"]
    )
    assert all(
        "required" not in route
        for route in at.session_state["product_routes"]
    )

    route_config = json.loads(at.data_editor[0].proto.columns)
    assert route_config["当前工序"]["type_config"]["type"] == "selectbox"
    assert route_config["成功下站"]["type_config"]["type"] == "selectbox"
    assert route_config["失败下站"]["type_config"]["type"] == "selectbox"
    assert route_config["删除"]["type_config"]["type"] == "button"
    assert list(at.data_editor[0].value.columns) == [
        "当前工序",
        "成功下站",
        "失败下站",
        "删除",
    ]
    assert at.data_editor[0].proto.editing_mode == 3
    assert len(at.data_editor[0].value) == 3


def test_add_product_form_appends_product() -> None:
    at = _open_page(_run())
    at.text_input(key="new_product_name").input("显示面板")
    at.text_input(key="new_product_model").input("P-1003")
    at.text_input(key="new_product_remark").input("新导入型号")
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["products"][-1] == {
        "product_model": "P-1003",
        "product_name": "显示面板",
        "enabled": True,
        "remark": "新导入型号",
    }


def test_add_product_rejects_duplicate_model() -> None:
    at = _open_page(_run())
    at.text_input(key="new_product_model").input("P-1001")
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["组件号不能重复"]


def test_product_editor_saves_editable_fields() -> None:
    at = _open_page(_run())
    at.session_state["product_editor"] = {
        "edited_rows": {
            0: {
                "组件名称": "电源模块 Pro",
                "备注": "已更新",
            }
        }
    }
    at.run()
    at.button(key="save_products").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    product = at.session_state["products"][0]
    assert product["product_name"] == "电源模块 Pro"
    assert product["remark"] == "已更新"
    assert product["product_model"] == "P-1001"


def test_delete_product_cascades_all_related_data() -> None:
    at = _open_page(_run())
    at.session_state["pending_product_delete"] = "P-1001"
    at.run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any("同时删除其工序流程和设备分配" in item.value for item in at.caption)
    at.button(key="confirm_delete_product").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert all(
        product["product_model"] != "P-1001"
        for product in at.session_state["products"]
    )
    assert all(
        route["product_model"] != "P-1001"
        for route in at.session_state["product_routes"]
    )
    assert all(
        item["product_model"] != "P-1001"
        for item in at.session_state["product_step_devices"]
    )


def test_delete_product_cancel_keeps_data() -> None:
    at = _open_page(_run())
    at.session_state["pending_product_delete"] = "P-1001"
    at.run()
    at.button(key="cancel_delete_product").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any(
        product["product_model"] == "P-1001"
        for product in at.session_state["products"]
    )


def test_route_duplicate_step_is_rejected() -> None:
    at = _run()
    at.session_state["product_routes"].append(
        {
            "product_model": "P-1001",
            "step_no": "1",
            "success_next_step": "END",
            "fail_next_step": "LOCK",
        }
    )
    at = _open_process_page(at)
    at.button(key="save_product_routes").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["同一产品型号下当前工序不能重复"]


def test_route_next_step_must_exist_in_product_flow() -> None:
    at = _run()
    at.session_state["product_routes"][0]["success_next_step"] = 99
    at = _open_process_page(at)
    at.button(key="save_product_routes").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.error[0].value == (
        "第 1 行的成功下站指向工序 99，但该工序未在当前产品型号流程中配置"
    )


def test_route_editor_saves_success_and_fail_targets() -> None:
    at = _open_process_page(_run())
    at.session_state["route_editor_P-1001"] = {
        "edited_rows": {
            0: {
                "成功下站": "3",
                "失败下站": "3",
            }
        }
    }
    at.run()
    at.button(key="save_product_routes").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    route = next(
        route
        for route in at.session_state["product_routes"]
        if route["product_model"] == "P-1001" and route["step_no"] == "1"
    )
    assert route["success_next_step"] == "3"
    assert route["fail_next_step"] == "3"


def test_delete_route_confirmation_removes_only_selected_step() -> None:
    at = _open_process_page(_run())
    at.session_state["pending_product_route_delete"] = {
        "product_model": "P-1001",
        "step_no": "1",
    }
    at.run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any("确定从产品型号" in item.value for item in at.markdown)
    at.button(key="confirm_delete_route").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert {
        route["step_no"] for route in at.session_state["product_routes"]
    } == {"2", "3"}


def test_delete_route_cancel_keeps_route() -> None:
    at = _open_process_page(_run())
    at.session_state["pending_product_route_delete"] = {
        "product_model": "P-1001",
        "step_no": "1",
    }
    at.run()
    at.button(key="cancel_delete_route").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert {
        route["step_no"] for route in at.session_state["product_routes"]
    } == {"1", "2", "3"}


def test_success_cycle_warns_but_saves() -> None:
    at = _run()
    routes = at.session_state["product_routes"]
    next(route for route in routes if route["step_no"] == "2")[
        "success_next_step"
    ] = "1"
    at = _open_process_page(at)
    at.button(key="save_product_routes").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert any("存在环路" in item.value for item in at.warning)


def test_device_assignment_switches_and_saves() -> None:
    at = _open_process_page(_run())
    at.selectbox(key="assign_step").select("2").run()
    assignment = at.multiselect(key="assign_P-1001_2")
    assert assignment.value == ["TEST-02"]

    assignment.set_value(["TEST-02B"]).run()
    at.button(key="save_product_step_devices").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assigned = {
        item["device_id"]
        for item in at.session_state["product_step_devices"]
        if item["product_model"] == "P-1001" and item["step_no"] == "2"
    }
    assert assigned == {"TEST-02B"}
    assert all(
        "line_id" not in item
        for item in at.session_state["product_step_devices"]
    )


def test_device_candidates_are_all_enabled_devices() -> None:
    at = _open_process_page(_run())
    at.selectbox(key="assign_step").select("2").run()
    assignment = at.multiselect(key="assign_P-1001_2")
    assert set(assignment.options) >= {"TEST-02 - 功能测试机", "TEST-02B - 功能测试机B"}


def test_device_assignment_rehydrates_for_other_product() -> None:
    at = _open_process_page(_run())
    at.selectbox(key="selected_product").select("P-1002").run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.multiselect(key="assign_P-1002_1").value == []
    assert at.info


def test_device_assignment_caption_explains_filter_scope() -> None:
    at = _open_process_page(_run())

    assert any(
        "单线运行：候选设备为全部启用设备" in item.value
        for item in at.caption
    )


def test_no_enabled_steps_shows_warning() -> None:
    at = _run()
    for step in at.session_state["steps"]:
        step["enabled"] = False
    at = _open_process_page(at)

    assert any(
        item.value == "请先在工序注册页添加并启用工序"
        for item in at.warning
    )


def test_readonly_product_page_disables_editing() -> None:
    at = _run()
    at.session_state["role"] = "只读"
    at = _open_process_page(at)

    assert not at.data_editor
    assert not at.button
    assert len(at.dataframe) == 4
    assert at.multiselect(key="assign_P-1001_1").disabled is True


def test_empty_products_show_empty_states() -> None:
    at = _run()
    at.session_state["products"] = []
    at.session_state["product_routes"] = []
    at.session_state["product_step_devices"] = []
    at = _open_process_page(at)

    assert "暂无产品型号，请先在组件注册页新增产品型号" in [
        item.value for item in at.info
    ]
    assert "请先在上方选择产品型号" in [item.value for item in at.info]
