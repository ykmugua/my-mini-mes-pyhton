"""程序下发页面的 session-state 占位数据与展示辅助函数。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

import streamlit as st

STATE_SCHEMA_VERSION = 9
MOCK_LOG_TIME = datetime(2026, 11, 13, 9, 30, 0)


def _mock_program_pulls(
    programs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成最近 30 条设备拉取记录，字段与正式页面保持一致。"""
    records = []
    for index in range(30):
        program = programs[index % len(programs)]
        step_no = int(program["step_no"])
        records.append(
            {
                "device_id": f"TEST-{step_no:02d}",
                "product": "P-1001" if step_no < 3 else "P-1002",
                "program_version": program["program_version"],
                "sha256": program["sha256"],
                "pulled_at": (
                    MOCK_LOG_TIME - timedelta(minutes=index * 11)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return records


def _mock_program_status_logs(
    programs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成最近 30 条设备状态上报记录，包含可信与异常场景。"""
    records = []
    for index in range(30):
        program = programs[index % len(programs)]
        step_no = int(program["step_no"])
        variant = index % 6
        trusted = variant not in {2, 5}
        reported_version = (
            "v1.1.0" if variant == 2 else program["program_version"]
        )
        reason = ""
        if variant == 2:
            reason = "程序版本与绑定不一致"
        elif variant == 5:
            reason = "SHA256 校验不一致"
        records.append(
            {
                "device_id": f"TEST-{step_no:02d}",
                "product": "P-1001" if step_no < 3 else "P-1002",
                "reported_version": reported_version,
                "reported_sha256": program["sha256"],
                "sha256_ok": variant != 5,
                "trusted": trusted,
                "reason": reason,
                "reported_at": (
                    MOCK_LOG_TIME - timedelta(minutes=index * 13 + 3)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return records


def initial_program_state() -> dict[str, list[dict[str, Any]]]:
    """返回一份新的占位数据，避免模块级可变状态在用户间共享。"""
    programs = [
        {
            "program_id": 1,
            "program_name": "TEST_MAIN",
            "program_version": "v1.2.0",
            "version_description": "增加压力检测与启动保护",
            "sha256": "6f3b8e0c1d2a9f7e4b5c6d8a1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f",
            "download_url": "http://192.168.1.50:8000/programs/fw_TEST-01_v1.2.0.zip",
            "step_no": 1,
        },
        {
            "program_id": 2,
            "program_name": "FUNC_TEST",
            "program_version": "v2.0.1",
            "version_description": "修复型号切换后的参数缓存",
            "sha256": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "download_url": "http://192.168.1.50:8000/programs/fw_FUNC-TEST_v2.0.1.7z",
            "step_no": 2,
        },
        {
            "program_id": 3,
            "program_name": "FINAL_CHECK",
            "program_version": "v1.0.0",
            "version_description": "正式终检参数模板",
            "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "download_url": "http://192.168.1.50:8000/programs/fw_FINAL-CHECK_v1.0.0.zip",
            "step_no": 3,
        },
    ]
    return {
        "steps": [
            {
                "step_no": 1,
                "step_name": "上电测试",
                "enabled": True,
                "remark": "首站上电与基础安全检查",
            },
            {
                "step_no": 2,
                "step_name": "功能测试",
                "enabled": True,
                "remark": "功能与参数校验",
            },
            {
                "step_no": 3,
                "step_name": "终检",
                "enabled": True,
                "remark": "出货前最终检查",
            },
            {
                "step_no": 4,
                "step_name": "包装",
                "enabled": False,
                "remark": "当前阶段暂未启用",
            },
        ],
        "lines": [
            {"line_id": "L1", "line_name": "一线"},
            {"line_id": "L2", "line_name": "二线"},
        ],
        "devices": [
            {
                "device_id": "TEST-01",
                "device_name": "上电测试机",
                "line_id": "L1",
                "step_no": 1,
                "enabled": True,
                "remark": "一线上电测试工位",
            },
            {
                "device_id": "TEST-01B",
                "device_name": "上电测试机B",
                "line_id": "L1",
                "step_no": 1,
                "enabled": True,
                "remark": "一线上电备用机",
            },
            {
                "device_id": "TEST-02",
                "device_name": "功能测试机",
                "line_id": "L2",
                "step_no": 2,
                "enabled": True,
                "remark": "一线功能测试工位",
            },
            {
                "device_id": "TEST-02B",
                "device_name": "功能测试机B",
                "line_id": "L2",
                "step_no": 2,
                "enabled": True,
                "remark": "二线功能测试工位",
            },
            {
                "device_id": "TEST-03",
                "device_name": "终检机",
                "line_id": "L2",
                "step_no": 3,
                "enabled": True,
                "remark": "一线终检工位",
            },
            {
                "device_id": "TEST-03B",
                "device_name": "终检机B",
                "line_id": "L2",
                "step_no": 3,
                "enabled": True,
                "remark": "二线终检工位",
            },
            {
                "device_id": "TEST-04",
                "device_name": "备用上电测试机",
                "line_id": "L1",
                "step_no": 1,
                "enabled": False,
                "remark": "备用设备，当前停用",
            },
        ],
        "programs": programs,
        "program_versions": [
            {
                "program_id": 1,
                "program_version": "v1.0.0",
                "version_description": "首版上电测试程序",
            },
            {
                "program_id": 1,
                "program_version": "v1.1.0",
                "version_description": "修复上电计时偏差",
            },
            {
                "program_id": 1,
                "program_version": "v1.2.0",
                "version_description": "增加压力检测与启动保护",
            },
            {
                "program_id": 2,
                "program_version": "v1.9.0",
                "version_description": "首版多型号功能测试程序",
            },
            {
                "program_id": 2,
                "program_version": "v2.0.0",
                "version_description": "优化整包比对流程",
            },
            {
                "program_id": 2,
                "program_version": "v2.0.1",
                "version_description": "修复型号切换后的参数缓存",
            },
            {
                "program_id": 3,
                "program_version": "v0.9.0",
                "version_description": "终检程序试运行版本",
            },
            {
                "program_id": 3,
                "program_version": "v1.0.0",
                "version_description": "正式终检参数模板",
            },
        ],
        "program_components": [
            {"program_id": 1, "component_no": "P-1001"},
            {"program_id": 2, "component_no": "P-1001"},
            {"program_id": 2, "component_no": "P-1002"},
        ],
        "products": [
            {
                "product_model": "P-1001",
                "product_name": "电源模块",
                "test_program_name": "TEST_MAIN",
                "test_program_path": "D:/test/P-1001/main.exe",
                "remark": "",
            },
            {
                "product_model": "P-1002",
                "product_name": "控制板",
                "test_program_name": "",
                "test_program_path": "",
                "remark": "待配置",
            },
        ],
        "product_routes": [
            {
                "product_model": "P-1001",
                "step_no": 1,
                "success_next_step": 2,
                "fail_next_step": "LOCK",
                "required": True,
            },
            {
                "product_model": "P-1001",
                "step_no": 2,
                "success_next_step": 3,
                "fail_next_step": "LOCK",
                "required": True,
            },
            {
                "product_model": "P-1001",
                "step_no": 3,
                "success_next_step": "END",
                "fail_next_step": "LOCK",
                "required": True,
            },
        ],
        "product_step_devices": [
            {
                "product_model": "P-1001",
                "step_no": 1,
                "device_id": "TEST-01",
            },
            {
                "product_model": "P-1001",
                "step_no": 1,
                "device_id": "TEST-01B",
            },
            {
                "product_model": "P-1001",
                "step_no": 2,
                "device_id": "TEST-02",
            },
            {
                "product_model": "P-1001",
                "step_no": 3,
                "device_id": "TEST-03",
            },
        ],
        "program_pulls": _mock_program_pulls(programs),
        "program_status_logs": _mock_program_status_logs(programs),
    }


def initialize_program_state() -> None:
    """首次初始化，并把旧版 session-state 数据结构迁移到新版。"""
    defaults = initial_program_state()
    version = st.session_state.get("program_data_version")

    if version == STATE_SCHEMA_VERSION:
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = deepcopy(value)
        for device in st.session_state.get("devices", []):
            device.setdefault(
                "line_id",
                "L1" if int(device["step_no"]) == 1 else "L2",
            )
        return

    if "programs" not in st.session_state:
        for key, value in defaults.items():
            st.session_state[key] = deepcopy(value)
    else:
        old_steps = st.session_state.get("line_steps")
        if isinstance(old_steps, list) and old_steps:
            st.session_state["steps"] = [
                {
                    "step_no": int(step["step_no"]),
                    "step_name": str(step["step_name"]),
                    "enabled": True,
                    "remark": "",
                }
                for step in old_steps
            ]
        else:
            st.session_state.setdefault("steps", deepcopy(defaults["steps"]))
        if "program_components" not in st.session_state:
            st.session_state["program_components"] = []
        if "program_versions" not in st.session_state:
            st.session_state["program_versions"] = deepcopy(
                defaults["program_versions"]
            )

        steps = [int(step["step_no"]) for step in st.session_state["steps"]]
        default_descriptions = {
            (str(item["program_id"]), str(item["program_version"])): str(
                item["version_description"]
            )
            for item in defaults["program_versions"]
        }
        for index, program in enumerate(st.session_state["programs"]):
            program.pop("program_mode", None)
            if "step_no" not in program:
                program["step_no"] = steps[index % len(steps)]
            if not any(
                str(item["program_id"]) == str(program["program_id"])
                and item["program_version"] == program["program_version"]
                for item in st.session_state["program_versions"]
            ):
                st.session_state["program_versions"].append(
                    {
                        "program_id": program["program_id"],
                        "program_version": program["program_version"],
                        "version_description": "",
                    }
                )
            for item in st.session_state["program_versions"]:
                if (
                    str(item["program_id"]) == str(program["program_id"])
                    and item["program_version"] == program["program_version"]
                ):
                    item.setdefault(
                        "version_description",
                        default_descriptions.get(
                            (
                                str(program["program_id"]),
                                str(program["program_version"]),
                            ),
                            "",
                        ),
                    )
            program.setdefault(
                "version_description",
                default_descriptions.get(
                    (str(program["program_id"]), str(program["program_version"])),
                    "",
                ),
            )

    st.session_state.pop("program_bindings", None)
    st.session_state.pop("line_steps", None)

    if "lines" not in st.session_state:
        st.session_state["lines"] = deepcopy(defaults["lines"])

    if "devices" not in st.session_state:
        st.session_state["devices"] = deepcopy(defaults["devices"])
    else:
        existing_device_ids = {
            str(device["device_id"]) for device in st.session_state["devices"]
        }
        for device in defaults["devices"]:
            if str(device["device_id"]) not in existing_device_ids:
                st.session_state["devices"].append(deepcopy(device))
    for device in st.session_state["devices"]:
        device.setdefault(
            "line_id",
            "L1" if int(device["step_no"]) == 1 else "L2",
        )

    for key in (
        "program_pulls",
        "program_status_logs",
        "products",
        "product_routes",
        "product_step_devices",
    ):
        if key not in st.session_state:
            st.session_state[key] = deepcopy(defaults[key])
    st.session_state.pop("product_step_configs", None)
    st.session_state["program_data_version"] = STATE_SCHEMA_VERSION


def step_by_no(
    steps: list[dict[str, Any]], step_no: int | str | None
) -> dict[str, Any] | None:
    for step in steps:
        if str(step["step_no"]) == str(step_no):
            return step
    return None


def step_label(
    steps: list[dict[str, Any]],
    step_no: int | str | None,
) -> str:
    step = step_by_no(steps, step_no)
    if step is None:
        return "未配置工序"
    return f"{step['step_no']} - {step['step_name']}"


def enabled_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [step for step in steps if bool(step.get("enabled"))]


def program_select_label(
    program: dict[str, Any], steps: list[dict[str, Any]]
) -> str:
    step = step_by_no(steps, program.get("step_no"))
    step_name = str(step["step_name"]) if step else "未配置工序"
    return (
        f"{program['program_name']} ({program['program_version']}) - {step_name}"
    )


def program_component_count(
    program_id: int | str, program_components: list[dict[str, Any]]
) -> int:
    return sum(
        1
        for item in program_components
        if str(item["program_id"]) == str(program_id)
    )


def program_type(component_count: int) -> str:
    if component_count == 0:
        return "未关联"
    if component_count == 1:
        return "单型号"
    return "多型号"


def available_program_versions(
    programs: list[dict[str, Any]],
    program_versions: list[dict[str, Any]],
) -> list[str]:
    versions: list[str] = []
    for item in program_versions:
        version = str(item["program_version"])
        if version not in versions:
            versions.append(version)
    for program in programs:
        version = str(program["program_version"])
        if version not in versions:
            versions.append(version)
    return versions


def program_version_description(
    programs: list[dict[str, Any]],
    program_versions: list[dict[str, Any]],
    program_id: int | str,
    version: str,
) -> str:
    for item in program_versions:
        if (
            str(item["program_id"]) == str(program_id)
            and item["program_version"] == version
        ):
            return str(item.get("version_description", ""))
    for program in programs:
        if (
            str(program["program_id"]) == str(program_id)
            and program["program_version"] == version
        ):
            return str(program.get("version_description", ""))
    return ""


def next_program_id(programs: list[dict[str, Any]]) -> int:
    return max((int(program["program_id"]) for program in programs), default=0) + 1
