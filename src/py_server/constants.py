"""跨层业务常量。

这些值来源于设备协议、UI 约定和 ProductFlow 状态机。集中定义后，
application/domain/repositories/ui 共享同一份语义，避免散落的字符串魔术值。
"""

from __future__ import annotations

# 通用判定
TRUE_TEXT = "true"
FALSE_TEXT = "false"

# 设备协议上报结果
RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
DETAIL_RESULT_PASS = "true"
DETAIL_RESULT_FAIL = "false"

# V1.3 整单中的最终报告标记
FINAL_REPORT_TRUE = "true"
FINAL_REPORT_FALSE = "false"

# ProductFlow 状态与终端下站
BOARD_NORMAL = "normal"
BOARD_LOCK = "lock"
BOARD_FINAL = "final"
NEXT_LOCK = "LOCK"
NEXT_END = "END"

# 看板显示状态
DEVICE_STATUS_IDLE = "空闲"
DEVICE_STATUS_TESTING = "测试中"
DEVICE_STATUS_OFFLINE = "离线"
DEVICE_STATUS_DISABLED = "禁用"
STATUS_PASS_TEXT = "通过"
STATUS_FAIL_TEXT = "失败"

MISSING_TRAYCODE = "/"
MISSING_SLOT = "/"
LEGACY_MISSING_TRAYCODE_VALUES = frozenset({"", "no traycode", "/"})


def is_missing_traycode(value: object) -> bool:
    """判断载具号是否表示“没有载具”；兼容旧数据。"""
    return str(value or "").strip().casefold() in LEGACY_MISSING_TRAYCODE_VALUES

PRODUCT_OVERVIEW_COLUMNS = (
    "barcode",
    "componentcode",
    "process_code",
    "traycode",
    "tray_slot",
    "board_status",
    "current_step",
    "last_report_device",
    "last_report_note",
    "updated_at",
    "flow_table",
)

FLOW_DETAIL_COLUMNS = (
    "barcode",
    "traycode",
    "tray_slot",
    "board_status",
    "step_no",
    "next_step",
    "device",
    "note",
    "changed_at",
)

PRODUCT_FLOW_EXPORT_COLUMNS = PRODUCT_OVERVIEW_COLUMNS

# 看板状态阈值（秒）
DEVICE_HEARTBEAT_TIMEOUT_SECONDS = 90
DEVICE_IDLE_THRESHOLD_SECONDS = 300

# 筛选框“全部”选项
ALL_OPTION = "全部"

# 变量类型
VARIABLE_TYPE_INT = "int"
VARIABLE_TYPE_FLOAT = "float"
VARIABLE_TYPE_STR = "str"
VARIABLE_TYPE_BOOL = "bool"
VARIABLE_TYPES = (VARIABLE_TYPE_INT, VARIABLE_TYPE_FLOAT, VARIABLE_TYPE_STR, VARIABLE_TYPE_BOOL)

# 日志动作
LOG_ACTION_READ = "READ"
LOG_ACTION_WRITE = "WRITE"

# 权限
ROLE_ENGINEER = "工程师"
ROLE_VIEW = "只读"
