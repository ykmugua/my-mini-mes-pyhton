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

### 2026-11-18：pwsh 版本更新（商店版 7.7.0 成为默认）

- 用户长期偏好：**优先使用 PowerShell 7 (`pwsh`)** 执行 PowerShell 脚本/命令，仅当 `pwsh` 不可用时回退到 Windows PowerShell 5.1。
- 2026-11-18 再次验证：直接执行 `pwsh` 时，实际进程是 **商店版 PS 7.7.0**：
  - 真实执行体：`C:\Program Files\WindowsApps\Microsoft.PowerShell_7.7.0.0_x64__8wekyb3d8bbwe\pwsh.exe`
  - `where.exe pwsh` 第一项是 WindowsApps 的别名入口 `C:\Users\WL\AppData\Local\Microsoft\WindowsApps\Microsoft.PowerShell_8wekyb3d8bbwe\pwsh.exe`（0 字节 stub，能正确转发）
  - `pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'` → `7.7.0`
- 同时机器上还有传统 MSI 安装：`C:\Program Files\PowerShell\7\pwsh.exe` → **7.6.10**（这就是上一条记录里的版本，并非被卸载，只是不再是 `pwsh` 命令默认指向）。
- 结论：以后直接写 `pwsh` 即可，默认走 7.7.0；如需固定 7.6.10，显式调用 `C:\Program Files\PowerShell\7\pwsh.exe`。启动本工程脚本实测：`pwsh -NoProfile -File .\scripts\run_api.ps1` / `run_ui.ps1` 正常。

- **关联**：[2026-11-18：PowerShell 7 已可用（长期偏好更新）]

### 2026-11-18：任务完成后自动 /sync-save

- 用户明确要求：**每次完成一个明确的开发/修改任务（代码改动并验证通过后），自动执行 `/sync-save`**（调用 sync_push），无需用户再说 /sync-save。
- 范围：只读操作（查看文件、查询状态等）不触发；必须是改了东西的任务。
- 已同步写入 AGENTS.md 的“长期偏好”段落。

### 2026-11-18：/sync-save 仅用户主动说时执行（更正上一条）

- 用户更正：**不要自动执行 `/sync-save`**。只有用户主动说出 /sync-save 时才调用 sync_push。
- 上一条“任务完成后自动 /sync-save”作废，AGENTS.md 已同步改回。

### 2026-11-18：V1.3 实现踩坑

- `repositories/base.py` 的 `Conn.execute()` 返回项目自定义 `Result`，只支持 `fetchone()/fetchall()`，**没有 `scalar_one()`**；count 查询用 `int(conn.execute(stmt).fetchone()[0])`（参考 binding_repo.binding_count）。
- 删除旧接口会让 15 个业务规则测试失败（它们依赖 `/api/test-result`）；用户选择保留旧接口（方案 B），不要物理删除。

### 2026-11-18：架构措辞别写死“FastAPI 唯一入口”

- 用户纠正过两次：不要写成“FastAPI 独占数据库/写入唯一入口”。他的定位是：FastAPI 主要给机台；Streamlit 是内部工具，可直接经 Repository 读写数据库（不写 SQL 即可）。
- 写文档/架构图时用这个定位；代码上 Streamlit 已通过 repositories/station_repo 等访问，符合分层（Repository 隔离 SQL）。

### 2026-11-18：st.dataframe 行选择做表格选择器

- 产品查询页用 `st.dataframe(..., on_select="rerun", selection_mode="single-row", key=...)`，事件在 `event.selection.rows`，是 0-based 行索引；映射回 results[idx] 取工件码。
- 不要在表格里做选中又另加一个 selectbox + 按钮，两套选择逻辑会打架（用户明确要求改掉）。
- AppTest 里 `at.segmented_control` 可以访问 segmented_control；emoji 标签在 GBK 控制台打印会报 UnicodeEncodeError，只是测试脚本问题不是页面问题。

### 2026-11-18：主子表插入时取自增 id

- `repositories.base.Conn.execute()` 返回的包装 Result 没有可靠的 `lastrowid`；SQLAlchemy 2.0 insert 经 Conn 包装后 `result.inserted_primary_key` 也拿不到。
- 解决：插入主表后用 `conn.lastrowid`（Conn 包装类字段），若为 None 则按唯一键（request_id）`select(id)` 查回。
- seed.py 在 py_server 包顶层，内部导入必须用 `from .repositories ...` / `from .engine ...`，不能用 `from ..`。

### 2026-11-18：产品查询展示“还是以前那种”的真实原因

- 现象：代码已改成 JSON 文本框 + details 列表，但页面还是旧表格。
- 根因1：seed 只写 test_reports 主子表，没写 workpieces 主表，导致新演示工件 SN202611180001~0010 不在查询结果列表里；用户实际选中的是旧工件 WP-xxxx，走“旧单条记录兼容表格”分支，看起来没变。
- 修复：seed_test_reports 同步写 workpieces（status/当前设备来自整单）；product_query_repo.list_workpieces 也补入“仅在 test_reports 中”的工件，避免真实上报后查不到。
- 根因2：曾出现两个 Streamlit 进程同时运行（旧进程没杀干净），重启时要用 Get-CimInstance 按命令行匹配杀掉所有 streamlit/uvicorn 进程。

### 2026-11-18：SQLite 表结构变更必须删库重建

- engine.py 改了 Table 列后，`seed --reset --demo` 只清数据，`create_all()` 不会 ALTER 已有表，旧库仍是旧列 → 报 `table test_reports has no column named componentcode`。
- 处理：先停掉占用 mes.db 的 API/UI 进程，删除 data/mes.db*（db/wal/shm），再跑 seed --reset --demo 重建表。
- 另: 测 AppTest 时必须确保 API 服务已启动，否则 client 报 WinError 10061，验证结果无效。

### 2026-11-18：动态表名安全与 SQLite 表结构变更

- 每产品一张明细表时，表名由 `sha256(barcode)[:16]` 派生（`d_` 前缀），避免条码含特殊字符/超长；不要直接用条码拼 SQL。
- 主库表结构变更后（如删除 test_report_details），必须停服删 mes.db* 再 seed --reset --demo；create_all 不会 ALTER 已有表。
- 独立详情库 changes 不影响主库：seed 重置时调 report_details_store.drop_all_tables()。

### 2026-11-18：SQLite 动态表名不能以数字开头

- 纯 16 位 hash 作表名时，如以数字开头（933786...），SQLite 报 `unrecognized token`。
- 解决：表名用 `SN_<safe条码>_<hash16>`，SQL 中为动态表名加双引号；router 校验 `SN_[0-9A-Za-z_]{1,40}_[0-9a-f]{16}` 防注入。
- SQLite `sqlite_sequence` 由 AUTOINCREMENT 自动创建；用户要求删除，则主键用 `INTEGER PRIMARY KEY`（仍有 rowid 自增）并在重置时 DROP sqlite_sequence。

### 2026-11-18 data 目录清理与动态明细列

- data/ 运行时只应保留两个数据库：mes.db + TestReport.db（各带 -shm/-wal），以及 programs/ 目录。之前表结构重建反复 rename 留下的 details_* / mes_* / TestReport_* 备份文件已清理（16 个）。
- 测试明细页面列不再写死：pd.DataFrame(details) 直接用数据库返回的列；丢弃原 id 列，在最前插入 "序号" 自增列。这样数据库 detail 表加/减字段时页面自动跟随。

### 2026-11-18：多库改造踩坑

- repos 自定义 Row 不是 SQLAlchemy Row，没有 `_mapping`；需用 dict(row) 访问列名。
- 批量替换 `with eg.get_details_engine().begin()` 时误把 drop_all_tables 改成 `_engine_for(engine)`，导致 NameError；drop_all_tables 必须固定用默认 details engine。
- seed 的 station 必须是 devices 表已注册设备，否则 report_route 回退 TestReport.db，不会生成 db_<工序>_<工序名>.db。

### 2026-11-18 产品查询两个交互问题

- 筛选条码后产品流转应自动聚焦该产品：/api/ui/product/flow-overview 增加 barcode 参数；_render_product_flow(wp_id) 接收当前选中条码过滤，单个匹配时自动选中第一行展示流转表。
- 选中 ProductFlow lock 但 mes.db 工件未锁时，页面原解锁判断只看 detail.locked 显示“未锁定”。已改为同时检查 product_flow_overview 的 board_status==lock。
- 解锁用例支持 flow_only：仅当 mes.db 未锁且显式传 target_step 时，跳过领域工件解锁，只写 ProductFlow；否则保持未锁不可重复解锁规则（通过验收测试）。

### 2026-11-18 参数改名要清理全部旧引用

- 将 list_workpieces 的 status 参数改名 device 时，函数体中仍有 status 过滤导致 NameError（500）。参数改名后用 `Select-String '\bstatus\b'` 全文检查并清理旧引用。

## 15. seed 重建分库数据（2026-11-19）
- `report_details_store.drop_all_tables()` 只清默认 details engine（TestReport.db），不会清 `db_<工序号>.db` 分库；seed --reset 重建演示数据时若只调它，分库的 report_index 旧行会残留（出现 id 1-10 旧空值 + 11-20 新数据）。已在 seed_test_reports() 中遍历 `config.data_dir().glob("db_*.db")` 逐个 DROP report_index/SN_表 修复。
- seed 的 report dict 加了 traycode 后，直接传给 report_repo.insert_report 会报 `CompileError: Unconsumed column names: traycode`（主表 test_reports 无该列）；需先用 dict comprehension 剔除 traycode 再写主表。

## 16. AppTest 行选择与编辑（2026-11-20）
- AppTest 的 data_editor 不支持 select_row()/set_value()：行选择要给 `st.dataframe(key=...)` 的 key 设置 session_state `{"selection": {"rows": [0]}}`；编辑要给 data_editor 的 key 设置 `{"edited_rows": {0: {"列": 值}}}` 后再 run()。
- st.dataframe 行选择读到的是 widget 自己的 selection state，不用另存 pq_current 式变量时也可靠；取消勾选 = rows=[]。

## 17. 用户协作偏好（2026-11-20）
- **特别大的改动前，先执行 `/sync-save` 并上传/提交 git 作为检查点**（用户怕改废了），再动手重构。
- **上传 git 前先整理文件夹**：删掉 `.pytest_tmp*` 等无用临时目录、检查 .gitignore 覆盖，别把无用文件上传。
- 已清理 45 个 `.pytest_tmpNN` 目录，`.gitignore` 从 `.pytest_tmp/` 改为 `.pytest_tmp*/`。

- Streamlit ButtonColumn 删除必须走 pending state + st.dialog 确认。工艺配置里「工序路线/工序资源」曾直接改 session_state，导致点击无弹窗；程序历史列表的 ButtonColumn 也需同样处理。AppTest 中 dialog 标题需要从 `at.caption` 或按钮 key 检查，不总是出现在 markdown。
- 程序注册页当前运行程序列表删除历史版本时，不能只从当前激活版本元数据取 program_id；历史版本可能不是激活版本，必须从该程序名对应的全部程序记录收集 program_id，再按 (program_id, version) 删除 program_versions，避免历史版本删不掉。

- 工位操作台手动入站必须先校验载具是否已占用。演示数据会预先绑定 T02001~T02010；已占用载具不能直接追加新条码，需先在“托盘解绑”或 `/api/ui/workbench/tray-unbind` 解除绑定。
- 手动入站跨 mes.db 与 ProductFlow.db 两个 SQLite 库，不能依赖单事务原子性；服务层先完整校验产品工艺、载具型号、载荷数量、条码重复与占用，再用 application 用例写入。
- Streamlit Agent API 驱动工位操作台时，输入未占用载具（如测试库中的 T02001）后应出现等于 `trays.capacity` 的 `workbench_barcode_<token>_<n>` 输入框；本机验证为 20 个。

- 新增 `py_server.ui.client` 函数后，仅刷新 Streamlit 页面可能仍报 `module ... has no attribute`：Streamlit 热重载会重跑入口脚本，但已加载的导入模块可能继续使用旧缓存。必须重启 Streamlit 进程；若同时新增 FastAPI 路由，也必须重启 uvicorn，否则页面会从 AttributeError 变成对应接口 404。2026-11-21 工位操作台实际遇到并验证此问题。

- 工位操作台页面被 `tests/ui_apps/workbench_app.py` 直接包装测试时不会经过主入口，因此 `render()` 内必须调用 `common.init_session()`；否则 `common.operator()` 为空，解锁接口会因 operator 长度不足返回 422。

- Streamlit `st.text_input` 没有 autofocus 参数；扫码枪连续作业必须额外处理焦点。当前使用 `st.html(..., unsafe_allow_javascript=True)` 定时聚焦带 key 的输入框，并让脚本内容随扫码状态 marker 变化，否则 Streamlit 可能复用相同脚本而不重新执行。
- 标签页如果默认 `on_change="ignore"`，所有页面会在隐藏状态一起执行，焦点脚本会提前过期。扫码页必须使用 `st.tabs(..., on_change="rerun", key=...)` 并结合 `.open` 只渲染当前标签。

- Streamlit 对同一 key 的 text_input 动态修改 `disabled` 后，浏览器实际 DOM 可能仍保持可编辑。工位操作台改为按状态切换 widget key：`workbench_barcode_input_*` / `disabled_*` / `locked_*`，并用独立 value key `workbench_barcode_<token>_<index>` 保存内容；新 widget key 创建前用 session_state 回填旧值。

- 入线状态删除报 `DELETE /api/ui/product/flow ... 404 Not Found` 时，先检查运行中 FastAPI 的 `/openapi.json` 是否存在该 DELETE 路径。本项目的 `scripts/run_api.ps1` 未启用 reload，后端新增路由后必须重启 8000 服务，否则 Streamlit 页面会调用到旧进程。2026-11-21 已重启并确认路由存在。

- SQLAlchemy `conn.execute(text(...)).fetchone()` 返回 Row；当 SELECT 多列时，不能直接用 `row["column"]` 读取，应使用 `row._mapping["column"]`。2026-11-21 自动解绑逻辑初始化时报 `tuple indices must be integers`，已修正。

- Streamlit selectbox 若用“工序号 · 工序名”作为显示选项，回调中不能直接把选项文本当工序号提交；工位操作台将显示值 `workbench_process_step` 与真实提交值 `workbench_inbound_step_no` 分离。

- 工位操作台扫码焦点脚本不能在每次 rerun 默认聚焦托盘框，也不能在 3 秒内每 100ms 重复 focus。当前只在 `workbench_inbound_focus_key` 明确的扫码流程状态变化时执行，并且成功聚焦一次后立即 clearInterval；浏览器验证数量输入框可保持焦点 1.2 秒不被抢。

- 产品查询是测试结果/产品解锁视图，不能由托盘操作驱动。手动解绑与自动解绑只清 `product_overview.traycode`，不能写 ProductFlow 明细、不能覆盖 `last_report_device` / `last_report_note`；否则产品查询会错误出现“托盘解绑/托盘自动解绑”。历史数据可用 `POST /api/ui/product/repair-tray-report-fields` 修复，产品解锁记录保持不动。

- Streamlit 按钮触发查询后，`st.button` 只在点击当次 rerun 为 True。若表格用 `on_select="rerun"`，勾选会再次 rerun，而按钮已恢复 False；此时若代码 `if not submitted: return`，结果表和 selection 都不会被处理，details 就不会出现。应把查询结果保存到 session_state，并在每次 rerun 都渲染结果表读取 selection。

- 测试报告查询结果表取消勾选时，必须清空 `pq_report_current` 及详情标题缓存，并让详情渲染只使用本次 `event.selection`；不能再从旧 session_state 回退，否则取消勾选后仍显示上一次 details。

## 18. Gotcha：Streamlit 用本机内网 IP 调 FastAPI 会绕代理导致 502/慢页面
2026-11-23 实测：Streamlit 通过 `http://172.130.64.122:8000/api/ui/master` 访问同机 FastAPI 时约 5.5 秒并返回 502；`http://127.0.0.1:8000/api/ui/master` 约 30–90ms 且返回 200。此前 `ui_api_base()` 默认复用 `api_public_base()`，会把设备侧公网/内网地址误用于 UI 服务调用，导致页面加载慢、接口超时降级。当前修复：`ui_api_base()` 未显式设置 `MES_UI_API_BASE` 时固定返回 `http://127.0.0.1:<MES_API_PORT>`；`api_public_base()` 保持不变，供设备下载地址使用。排查方式：分别用 httpx 请求 127.0.0.1 与局域网 IP，对比 status/耗时。

## 19. Gotcha：主数据加载失败时页面必须初始化空列表
`pages/_common.py::ensure_master_data()` 在 `client.master_snapshot()` 失败时以前只显示错误并返回，不写 session_state；直接读 `st.session_state.devices` / `steps` / `products` 的注册页会抛 `st.session_state has no attribute "devices"`。当前修复：失败分支对所有 MASTER_KEYS 及 `program_pulls`、`program_status_logs` 执行 `setdefault(key, [])`，保证页面显示空表而不是崩溃。

## 20. Gotcha：工位操作台工序框不能按需消失
`_render_inbound` 以前只有选择产品型号并成功读取工艺后才创建“工序” selectbox，未选型号时该控件不存在，现场看起来像工序框消失。当前实现：在产品型号同一行固定渲染“工序”框；未选型号时 options=[]、disabled=True、placeholder="请先选择产品型号"；选择型号后再加载该型号的 route_options。测试需验证初始时 `workbench_process_step` 存在且 disabled，选择型号后存在且 enabled。

## 21. Gotcha：本机 pytest-of-WL 临时目录可能权限拒绝
2026-11-23 在 Windows 直接运行 pytest 时，setup 阶段报 `PermissionError: [WinError 5] ... C:\Users\WL\AppData\Local\Temp\pytest-of-WL`。解决：运行 pytest 时传入项目内 `--basetemp`，例如 `--basetemp E:\personal\xqk\my-mini-mes-pyhton\.pytest_tmp_full`。这不是项目代码失败。

## 22. Gotcha：合并测试报告库时必须保留工序来源
原按工序分库的“工序”信息来自物理文件 db_<step>.db。合并到单库后必须新增/使用 report_index.step_no，否则 query_reports(step_no=...) 无法筛选，筛选框选工序 1 会返回所有工序或空结果。迁移历史数据时可按 station 回填（如 TEST-01→1、TEST-02→2、TEST-03→3），新上报由 upload_test_result_v1 和 seed 显式写入 step_no。

- 托盘解绑不能只清空 `traycode`：那会导致条码仍被重复入站校验拦截。当前正确语义是「结束当前流转 + 写解绑流转历史」，保留产品流转明细和测试数据。
- `master_data.json` 是 seed 文件，不是 UI 运行时数据；UI 修改写数据库，不会回写 JSON。测试使用 `MES_MASTER_SEED_FILE` 指向旧 fixture，避免生产种子数据影响测试。
- Streamlit `ButtonColumn` 当前版本不支持 `disabled`；只读模式下必须不渲染该列。
