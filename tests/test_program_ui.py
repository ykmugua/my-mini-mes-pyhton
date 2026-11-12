"""程序下发占位页面测试：不依赖 FastAPI 或数据库。"""

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


def test_program_ui_renders_three_sections_and_derived_columns() -> None:
    at = _run()

    assert at.title[0].value == "📦 程序下发"
    assert [item.value for item in at.subheader] == [
        "上传程序文件",
        "程序运行列表",
        "型号关联",
    ]
    assert [item.label for item in at.expander] == [
        "上传程序文件",
        "设备拉取记录（最近 30 条）",
        "设备状态上报记录（最近 30 条）",
    ]
    assert len(at.data_editor) == 2
    assert at.radio(key="role").value == "工程师"

    programs = at.data_editor[0].value
    assert programs["关联型号数"].tolist() == [1, 2, 0]
    assert programs["程序类型"].tolist() == ["单型号", "多型号", "未关联"]
    assert [
        (item["program_id"], item["program_version"])
        for item in at.session_state["program_versions"]
    ] == [
        (1, "v1.0.0"),
        (1, "v1.1.0"),
        (1, "v1.2.0"),
        (2, "v1.9.0"),
        (2, "v2.0.0"),
        (2, "v2.0.1"),
        (3, "v0.9.0"),
        (3, "v1.0.0"),
    ]
    assert all(
        item.get("version_description")
        for item in at.session_state["program_versions"]
    )
    assert list(programs.columns).index("版本说明") == list(programs.columns).index(
        "版本"
    ) + 1

    column_config = json.loads(at.data_editor[0].proto.columns)
    editable_columns = {
        column
        for column, config in column_config.items()
        if not config.get("disabled") and column not in {"program_id", "_index"}
    }
    assert editable_columns == {"版本"}


def test_device_logs_render_latest_30_records() -> None:
    at = _run()

    assert len(at.session_state["program_pulls"]) == 30
    assert len(at.session_state["program_status_logs"]) == 30
    assert len(at.dataframe) == 4

    pull_frame = at.dataframe[2].value
    assert list(pull_frame.columns) == [
        "时间",
        "设备",
        "产品",
        "程序版本",
        "SHA256",
    ]
    assert len(pull_frame) == 30
    assert pull_frame.iloc[0]["设备"] == "TEST-01"
    assert pull_frame.iloc[0]["程序版本"] == "v1.2.0"
    assert pull_frame.iloc[0]["SHA256"].endswith("…")

    status_frame = at.dataframe[3].value
    assert list(status_frame.columns) == [
        "时间",
        "设备",
        "产品",
        "上报版本",
        "可信",
        "原因",
    ]
    assert len(status_frame) == 30
    assert status_frame.iloc[0]["可信"] == "是"
    assert status_frame.iloc[2]["可信"] == "否"
    assert status_frame.iloc[2]["原因"] == "程序版本与绑定不一致"


def test_upload_program_requires_and_stores_step() -> None:
    at = _run()
    content = b"demo-program"

    at.text_input(key="upload_program_name").input("UPLOAD_TEST")
    at.text_input(key="upload_program_version").input("v9.0.0")
    at.text_input(key="upload_version_description").input("新增型号参数支持")
    at.selectbox(key="upload_step_no").select(2)
    at.file_uploader(key="upload_program_file").upload("bundle.zip", content)
    at.form_submit_button[0].click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    programs = at.session_state["programs"]
    assert len(programs) == 4
    assert programs[-1]["program_id"] == 4
    assert programs[-1]["step_no"] == 2
    assert programs[-1]["version_description"] == "新增型号参数支持"
    assert "program_mode" not in programs[-1]
    assert programs[-1]["sha256"] == hashlib.sha256(content).hexdigest()
    assert (
        programs[-1]["download_url"]
        == "http://192.168.1.50:8000/programs/UPLOAD_TEST_v9.0.0.zip"
    )
    assert {
        "program_id": 4,
        "program_version": "v9.0.0",
        "version_description": "新增型号参数支持",
    } in at.session_state["program_versions"]

    updated_frame = at.data_editor[0].value
    assert updated_frame.iloc[-1]["所属工序"] == 2
    assert updated_frame.iloc[-1]["版本说明"] == "新增型号参数支持"
    assert updated_frame.iloc[-1]["关联型号数"] == 0
    assert updated_frame.iloc[-1]["程序类型"] == "未关联"


def test_program_editor_saves_version_and_step() -> None:
    at = _run()
    at.session_state["program_editor"] = {
        "edited_rows": {0: {"版本": "v1.0.0", "所属工序": 3}}
    }
    at.run()
    at.button(key="save_program_edits").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["programs"][0]["program_version"] == "v1.0.0"
    assert at.session_state["programs"][0]["step_no"] == 3
    assert (
        at.session_state["programs"][0]["version_description"]
        == "首版上电测试程序"
    )
    assert {
        "program_id": 1,
        "program_version": "v1.0.0",
        "version_description": "首版上电测试程序",
    } in at.session_state["program_versions"]


def test_program_editor_saves_version_description() -> None:
    at = _run()
    at.session_state["program_editor"] = {
        "edited_rows": {0: {"版本说明": "现场验证后的说明"}}
    }
    at.run()
    at.button(key="save_program_edits").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert at.session_state["programs"][0]["version_description"] == "现场验证后的说明"
    assert {
        "program_id": 1,
        "program_version": "v1.2.0",
        "version_description": "现场验证后的说明",
    } in at.session_state["program_versions"]


def test_component_duplicate_is_rejected() -> None:
    at = _run()
    components = at.session_state["program_components"]
    components.append({"program_id": 1, "component_no": "P-1001"})
    at.session_state["program_components"] = components
    at.run()

    at.button(key="save_component_links").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.error] == ["同一程序下型号不能重复"]


def test_zero_components_can_be_saved_with_warning() -> None:
    at = _run()
    at.selectbox(key="component_program_id").select(3).run()

    at.button(key="save_component_links").click().run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.warning] == [
        "未关联型号的程序无法被产品工序使用"
    ]
    assert not [
        item
        for item in at.session_state["program_components"]
        if item["program_id"] == 3
    ]


def test_readonly_role_disables_editing() -> None:
    at = _run()
    at.radio(key="role").set_value("只读").run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert not at.data_editor
    assert not at.button
    assert len(at.dataframe) == 4


def test_empty_program_tables_keep_columns() -> None:
    at = _run()
    at.session_state["programs"] = []
    at.session_state["program_components"] = []
    at.run()

    assert not at.exception, [str(item.value) for item in at.exception]
    assert [item.value for item in at.info] == [
        "暂无记录",
        "暂无程序，请先上传程序文件。",
    ]
    assert list(at.data_editor[0].value.columns) == [
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


def test_no_device_binding_state_or_ui() -> None:
    at = _run()

    assert "program_bindings" not in at.session_state
    assert "设备绑定" not in [item.value for item in at.subheader]
