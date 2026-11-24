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
