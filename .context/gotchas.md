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

## 5. Gotcha：停用工序必须保留历史展示解析

工序的 enabled 只应控制“新建配置时的下拉候选”，不能从历史解析中删除。程序运行列表中的所属工序使用全部 steps 解析，否则停用工序后旧程序会显示成“未配置工序”。只有上传程序等新建场景使用 enabled_steps。

## 6. Gotcha：ButtonColumn 删除应经 pending state 再弹窗

Streamlit ButtonColumn 始终只读，点击信息只在回调所在 rerun 的 session_state[key] 中出现，随后会重置。

当前实现：
- on_click 回调只解析点击行并写入 pending_step_delete，不直接删除。
- 页面渲染后读取 pending_step_delete，再调用 st.dialog。
- 弹窗关闭/取消时通过 on_dismiss 或按钮回调清理 pending，避免下次 rerun 重复打开。

## 7. Gotcha：无启用工序时表单仍可渲染空 Selectbox

Streamlit 1.67 允许 `st.selectbox(options=[])` 配合 `index=None`、`disabled=True` 和 placeholder，因此在没有启用工序时无需跳过表单或伪造占位选项。

设备页使用该方式同时满足：
- 页面顶部显示启用工序警告；
- 工序下拉保持空选项；
- 添加设备按钮 disabled。

## 8. Gotcha：产品流程保存使用整产品替换

product_routes 按 product_model 分组维护。保存时若逐行更新容易残留已删除节点，因此当前实现会先删除该产品的全部旧流程，再写入编辑器返回的新流程。

delete 确认弹窗也会同时清理 products、product_routes、product_step_devices 三处记录，避免孤立数据。

## 9. Gotcha：线体删除必须检查设备引用

线体是 devices.line_id 的外键式引用。删除线体前必须统计 devices 中同 line_id 的记录；存在引用时保留线体并提示引用数量，不能级联删除设备。

空 lines 与空 enabled steps 是两种独立阻塞条件：新增设备按钮需在二者都非空时启用。

## 10. Gotcha：线体筛选不等于线体级分配

当前 product_step_devices 不存 line_id。设备选择时虽按“线体+工序”过滤，但保存会删除该 product_model + step_no 的所有旧设备记录。

因此：
- 在 L1 保存后切到 L2 再保存，会覆盖 L1 的分配结果。
- 若未来业务要求跨线体独立配置，必须先升级 product_step_devices 并修改删除键。
