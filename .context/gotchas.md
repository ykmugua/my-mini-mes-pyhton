# 避雷点 / 踩坑记录

## 1. Gotcha：AppTest 无法模拟被 file_uploader type 拦截的扩展名

在 `st.file_uploader(type=["zip", "7z"])` 中，AppTest 尝试上传 `.txt` 时会在文件状态反序列化阶段直接抛出 `StreamlitAPIException: Invalid file extension`，脚本中的 `.zip/.7z` 兜底校验不会执行。

因此：
- 页面仍保留显式后缀校验，用于防御绕过前端限制的输入。
- AppTest 只验证合法 `.zip` 上传；非法后缀兜底以代码审查为准，真实浏览器文件选择器本身也会过滤非法类型。

## 2. Gotcha：程序页面 session-state 结构变更需要迁移旧会话

Streamlit 文件热重载会保留当前浏览器会话的 session_state。旧版 `programs` 含有 `program_mode` 且没有 `step_no`；若只替换页面代码，热重载后可能出现 KeyError。

处理方式：
- 使用 `program_data_version=2` 作为结构版本标记。
- 初始化时保留旧会话中的 programs/program_components，为 programs 补齐 step_no。
- 删除旧 program_mode 和 program_bindings，再写入新版结构。

## 3. Gotcha：Streamlit data_editor 默认允许拖动列，column_order 不能锁定顺序

Streamlit 1.67：
- `column_order` 只定义首次渲染的列顺序。
- `st.data_editor` 没有公开的 `allow_column_reorder=False` 一类参数。
- 问题与 Deploy 模式、表头列类型无关；Glide Data Grid 对可编辑和普通数据表都提供列移动能力。

当前处理：仅在 `.st-key-program_list_panel` 上拦截表头拖动，同时通过 `col-resize` 光标识别并放行列宽调整。

## 4. Gotcha：data_editor 的 disabled 列表可以精确控制可编辑列

在 Streamlit 1.67 中，`disabled` 传入列名列表时，列表中的列只读，未列出的列保持可编辑。可用以下方式表达“只允许编辑版本”：

```python
[column for column in PROGRAM_COLUMNS[1:] if column != "版本"]
```

测试可通过 `at.data_editor[0].proto.columns` 的 JSON 配置检查每个业务列的 `disabled` 状态。
