"""注册页模板补齐规则测试。"""

from __future__ import annotations

from py_server.ui.pages.registry_helpers import fill_missing_text_values


def test_fill_missing_values_keeps_user_input():
    form = {"针床码": "NB-999", "针床名称": "", "针床型号": "M-A"}
    template = {"针床码": "NB-001", "针床名称": "模板针床", "针床型号": "M-B"}
    assert fill_missing_text_values(form, template) == {
        "针床码": "NB-999",
        "针床名称": "模板针床",
        "针床型号": "M-A",
    }


def test_fill_missing_values_without_template():
    form = {"针床码": "", "针床名称": "名称"}
    assert fill_missing_text_values(form, None) == form
