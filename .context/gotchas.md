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

## 11. Gotcha：SelectboxColumn 混用整数和字符串会导致整列只读

在 Streamlit 1.67 的 `st.data_editor` 中，如果一列同时包含整数工序号和 `END`/`LOCK` 字符串，即使配置了 `SelectboxColumn`，前端也可能把该列标成 disabled，用户无法选择。

处理方式：
- 编辑器 DataFrame 中把下站值统一转换成字符串，`SelectboxColumn.options` 也使用字符串工序号。
- 保存校验时通过整数转换恢复真实 step_no，终端标记仍保留为 END/LOCK。
- 测试应检查列配置中的 disabled 为空，并实际确认下拉类型。

## Gotcha：uv run 在此环境锁定失败

`uv run pytest` 报 `Could not acquire lock ... uv\cache\.lock 拒绝访问`；改用 `.venv\Scripts\python.exe -m pytest` 可正常运行（基线 100 passed）。

## 11. Gotcha：SQLAlchemy 2.1 的 on_conflict_do_update 参数变化

SQLAlchemy 2.1.8 中 `Insert.on_conflict_do_update()` 不再接受 `constraint=` 关键字；改用 `index_elements=["col1", "col2"]`，这样同时兼容 SQLite/PostgreSQL。

## 12. Gotcha：SQLAlchemy 2.x text() 与 ? 占位符、executemany

- 原生 SQL 字符串通过 `text()` 执行时必须用具名参数 `:p0`；老代码 `?` 占位符需要转换。
- `conn.execute(insert_stmt, list_of_dicts)` 是 executemany，访问 `inserted_primary_key` 会抛 `InvalidRequestError`；需要捕获异常或改用 `inserted_primary_key_rows`。
- `union_all(...).order_by(1)` 不被接受；用 `order_by(text('1'))`。
- `String` 在 SQLite 中映射为 VARCHAR，且 primary key 默认 NOT NULL；要逐字对齐旧 schema（TEXT / PK 可空）需用 `Text` + `primary_key=True, nullable=True` + `sqlite_autoincrement=True` + `server_default`。

## Gotcha：FastAPI 未标注类型的 body 参数被当成 query

`@router.post` 中若写 `def f(payload):` 而不标注 Pydantic 类型，FastAPI 会把 `payload` 当作 required query 参数，JSON body 被忽略并返回 422。必须写 `payload: BindingsIn` 等具体模型类。

## Gotcha：pytest 系统临时目录权限

本机 `C:\Users\WL\AppData\Local\Temp\pytest-of-WL` 偶发 `PermissionError [WinError 5]`；用 `--basetemp=<项目内目录>` 可绕过。

## 13. Gotcha：Streamlit 子模块改动不会热重载

修改 `src/py_server/ui/pages/*.py` 这类被子模块 import 的文件后，运行中的 Streamlit 不会自动重载，页面仍是旧代码。必须重启 streamlit 进程。仅修改入口 `src/py_server/streamlit_app.py` 才会热重载。

## Gotcha：SQLite CHECK 约束变更需重建表

给 variables.type 的 CHECK 增加 float 时，SQLite 不支持 ALTER 修改约束，需建新表→INSERT SELECT→DROP→RENAME（真实 data/mes.db 已迁移，6 行数据保留）。

## 14. Gotcha：streamlit-sortables 组件 key 必须随列表变化

`sort_items()` 是自定义组件，key 固定时会缓存旧 items 状态；设备增删后 items 变了但组件不重建，导致顺序区显示旧列表。解决：key 含设备列表指纹，如 `f"device_order_sort_{hash('|'.join(ids))}"`。

## Gotcha：全局 st_autorefresh 与 dialog/multiselect 冲突

`st_autorefresh(interval=1000)` 每秒重建整个页面，会导致删除确认弹窗闪烁、交互中断。改用 `@st.fragment(run_every=1000)` 只包住需要刷新的卡片区，页面其他部分不重建。

## Gotcha：st.text_input 隐藏 label 后 AppTest 仍报告 label 属性

`label_visibility="collapsed"` 时视觉上不显示 label，但 AppTest 的 element.label 仍有值（proto 中 label_visibility=COLLAPSED），验证时应检查 proto。

### 2026-11-18：PowerShell 7 已可用（长期偏好更新）

- 用户长期偏好：**优先使用 PowerShell 7 (pwsh)** 执行 PowerShell 脚本/命令，仅当 pwsh 不可用时回退到 Windows PowerShell 5.1。
- 历史状态：之前 `where pwsh` 指向 WindowsApps 下 0 字节 stub（PS7 实际未装成），当时回退用 5.1。
- **当前状态（2026-11-18 验证）**：PowerShell 7.6.10 已真正安装，`where pwsh` → `C:\Program Files\PowerShell\7\pwsh.exe`，`pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'` 输出 7.6.10。
- 后续我启动脚本/执行 PS 命令一律优先用 `pwsh`（如 `pwsh -NoProfile -File .\scripts\run_ui.ps1`）。
