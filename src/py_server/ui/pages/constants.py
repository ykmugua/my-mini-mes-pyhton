"""页面层共享常量。

集中放置各注册页共用的文案、状态值和校验表达式，避免同一个魔术字符串
散落在多个 Streamlit 页面中。
"""

from __future__ import annotations

# 权限
ROLE_EDIT = "工程师"
ROLE_VIEW = "只读"

# 启用选项
ENABLED_YES = "是"
ENABLED_NO = "否"
ENABLED_OPTIONS = (ENABLED_YES, ENABLED_NO)

# 空值清洗：编辑器里 pandas/Streamlit 可能写入这些文本占位
EMPTY_TEXT_VALUES = frozenset({"nan", "none", "nat"})

# 工序号只用于数据库文件名和内部标识，限制为字母/数字
STEP_NO_PATTERN = r"[A-Za-z0-9]+"

# 通用提示
EMPTY_STATE_HINT = "暂无数据，请新增"
READ_ONLY_HINT = "只读角色不可修改数据。"
SAVE_SUCCESS = "已保存"
DELETE_SUCCESS = "已删除"

# 从模板新建
TEMPLATE_LABEL = "从原有模板中新建"
BLANK_TEMPLATE = "空白新增"
COPY_SUFFIX = "COPY"
COPY_SUFFIX_ALNUM = "COPY"

# 注册配置区块标题
CREATE_PROGRAM_SECTION = "新增程序"
CREATE_STEP_SECTION = "新增工序"
CREATE_DEVICE_SECTION = "新增设备"
CREATE_TRAY_SECTION = "新增载具"
CREATE_COMPONENT_SECTION = "新增组件"
ACTIVE_PROGRAMS_SECTION = "当前运行程序"
PROGRAM_VERSIONS_SECTION = "程序版本历史"
PROGRAM_HISTORY_SECTION = "历史程序"
PROGRAM_HISTORY_MANAGEMENT_SECTION = "程序历史管理"
STEP_LIST_SECTION = "工序列表"
DEVICE_LIST_SECTION = "设备列表"
TRAY_LIST_SECTION = "载具列表"
COMPONENT_LIST_SECTION = "组件列表"

# 注册配置表单按钮
CREATE_PROGRAM_BUTTON = "新增程序"
CREATE_STEP_BUTTON = "新增工序"
CREATE_DEVICE_BUTTON = "新增设备"
CREATE_TRAY_BUTTON = "新增载具"
CREATE_COMPONENT_BUTTON = "新增组件"
SAVE_PROGRAM_BUTTON = "保存程序"
SAVE_VERSION_DESCRIPTION_BUTTON = "保存版本说明"
SAVE_STEP_BUTTON = "保存工序"
SAVE_DEVICE_BUTTON = "保存设备"
SAVE_TRAY_BUTTON = "保存载具"
SAVE_COMPONENT_BUTTON = "保存组件"
