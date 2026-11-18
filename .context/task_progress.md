# 任务进度

## 当前项目：my-mini-mes-pyhton

- **当前分支**：master
- **项目标题**：旁路式小型 MES

- [X] 已初始化 Context Sync
- [X] 梳理当前项目目标与范围
- [X] 实现“程序下发”页面
- [X] 实现“工序注册”页面
- [X] 实现“设备注册”页面
  - 增加线体管理与 devices.line_id
  - 被设备引用的线体禁止删除
- [X] 实现“产品管理”页面
  - 产品、工序流程、设备分配均已实现
  - 设备分配已改为“选产品 → 选线体 → 选工序 → 选设备”
  - 线体和工序筛选并排显示
  - 线体只作为候选筛选条件，不写入 product_step_devices
  - 保存会覆盖该 product_model + step_no 的全部分配
- [X] 调整产品工序流程
  - 去掉关键工序字段与左侧整行删除/选择控件
  - 成功下站、失败下站均可选择启用工序
  - 新增行保持可用，使用 num_rows="add"
  - 增加逐行删除 ButtonColumn + 确认弹窗
  - 确认删除只移除对应流程节点
- [X] 新增系统设计框架文档
  - `system_design_framework/manual.md`
  - `system_design_framework/System_Architecture_Diagram.drawio`
  - 目标分层：测试机台/Streamlit → FastAPI → Repository → SQLAlchemy Engine → SQLite/PostgreSQL
- [X] 记录 gotchas / architecture
- [X] 完成 /sync-save 与 /sync-load 验证

## 验证结果

- 产品管理测试：20 passed
- 完整测试套件：100 passed
- Agent API：产品页 ready；流程编辑器为 add-only；线体/工序位于同一双列布局
- 浏览器：流程删除按钮可弹出确认框，确认后流程行由 3 行变为 2 行
- 服务端控制台无新增警告或异常
- 仅有 starlette.testclient 的 httpx 弃用警告，不影响当前功能

## 阶段进度（2026-11-16）

- [x] Step 1: Schema 快照（tools/schema_baseline.json）+ SQL 清单（tools/_sql_inventory.py）
- [x] Step 2: engine.py（SQLAlchemy Core，9 张表 DDL 与旧 schema 结构一致）+ repositories/（8 个 repo 文件、with_conn/with_read_conn 事务边界）；100 原测试仍绿
- [x] Step 3: domain/trust（ProgramTrustPolicy + 6 TrustReason + 指纹优先级三 case）
- [x] Step 4: domain/workpiece（Workpiece 聚合 + UnlockOutcome + 空原因/confirm 校验）
- [x] Step 5: domain/interlock（InterlockPolicy 五步短路 + 缺 device_id 路径）
- [x] Step 6: application/ 三用例（report_test_result / unlock_workpiece / report_program_status 持有事务）；services.py 已改为委托层（无运行时 SQL）
- [x] 新增 25 条领域单测，全部 125 passed
- [ ] Step 7a/7b/7c: Streamlit 改 HTTP（ui/client.py + MES_UI_API_BASE）
- [ ] Step 8: 清理 services.py、README 更新

## 阶段进度更新（2026-11-16 17:40）

- [x] Step 7a/7b/7c: Streamlit 页面全部改走 `ui/client.py`（HTTP）；新增 `/api/ui/*` 路由；`MES_UI_API_BASE` 配置；3s 超时 + 失败降级；AppTest 用 MES_UI_INPROCESS=1 走进程内 TestClient
- [x] Step 8（部分）: api 重构为包（api/app.py + api/schemas.py + api/deps.py + api/routers/*）；seed.py SQL 迁移到 repo；架构静态检查通过
- [x] 新增架构守卫测试 + UI 客户端测试，全部 134 passed
- [ ] README 更新架构图与三条取舍
- [ ] 最终全量验收（health/docs/四页面）

## 改造完成（2026-11-16）

- 全部执行步骤完成：schema 基线 → engine/repositories → domain/trust → domain/workpiece → domain/interlock → application 三用例 → Streamlit HTTP（ui/client.py + MES_UI_API_BASE）→ 清理与 README。
- 最终 `134 passed`（原 100 + 新增领域 25 + 架构/客户端 9）；schema `table_info` diff = 0。
- 真实双进程验证：FastAPI `/health`、`/docs`、`/openapi.json`（19 paths）正常；Streamlit agent API 四个页面全部 `status=ready`、无 exception；真实 HTTP 下绑定拉取返回新版本/SHA、变量读写往返通过。
- API 包结构：`api/app.py` + `api/schemas.py` + `api/deps.py` + `api/routers/{program,test_result,interlock,variable,dashboard}.py`；`api.py` 单文件已删除。
- 注意：FastAPI UI POST 路由的 `payload` 必须显式标注 Pydantic 模型类型（如 `payload: BindingsIn`），否则 FastAPI 把它当 query 参数导致 422。
- 验证脚本保留在 tools/：`_dump_schema.py`、`_check_schema.py`。

## A2 完成（2026-11-16 18:05）

- engine.py 新增 9 张主数据表（steps/lines/devices/programs/program_versions/program_components/products/product_routes/product_step_devices），共 18 张表，不改原有 9 张。
- master_data_repo.py 实现全部读写；api/routers/master_data.py 暴露 /api/ui/master[/{key}]；ui/client.py 增加 master_snapshot/list/save。
- master_data.json + master_seed.py 从 app_pages 原型迁移演示主数据，seed.py 自动写入。
- app_pages 4 个页面复制到 ui/pages/ 并包装为 render_page()，通过 _common.ensure_master_data()/save_key() 走 HTTP；内嵌生成所有 state 写入后的后端保存。
- 主入口改为 6 页：程序下发/工序注册/设备注册/产品管理/看板/变量；工序锁页已移除。
- can_edit() 同步 role key（工程师/只读）给 app_pages 页面。
- 真实双进程 agent API 验证 6 页全部 status=ready、无 exception；主数据 HTTP 保存往返通过，真实库已重新 seed。
- 134 passed。注意 pytest 临时目录权限问题，需 --basetemp 指到项目内目录。

### 2026-11-16 晚间续：变量增强 + 主数据 UI 多轮调整

**变量模块增强**：
- 三层变量树（组.子组.键点分路径），新增 `/api/ui/variables/tree` 返回嵌套 JSON；设备 API 完全兼容旧扁平变量。
- 变量类型新增 `float`（services.coerce/typed + engine CHECK 约束迁移）。真实库 variables 表 CHECK 已重建为 int/float/str/bool。
- 新增 `variable_logs` 表记录设备 READ/WRITE；设备 GET 用可选 `device_id` 查询参数记读取、POST 记写入；`/api/ui/variable-logs/read|write`。
- 变量页：列表内直接编辑（变量名/类型/当前值）+「保存修改」；JSON树与接口示例合并在一个 tab 组；设备读写记录 tab。

**程序下发增强**：
- 程序历史管理：`/api/ui/program-history?name=`（按 program_id 倒序=新→老）、`DELETE /api/ui/program-version/{id}`（级联清理版本说明/型号关联）。页面选程序名→版本列表→删版本；新增型号用独立 expander 表单，列表 num_rows=fixed + 右侧删除 ButtonColumn。
- 设备拉取/上报记录改为 tab 形式（与变量页一致）。

**UI 统一调整**：
- 所有保存按钮移到列表左下角（data_editor 之后）。
- 工序/线体/设备列表支持直接修改（去掉 disabled）。
- 设备新增与设备列表合并到同一容器。
- 导航首页改为「测试数据看板」。
- 型号关联的新增+列表用子容器包裹（与「选择程序」同级）。

**Gotcha**：Streamlit 不热重载 `ui/pages/` 子模块改动，改完必须重启 UI 进程才能生效（改主入口 streamlit_app.py 会热重载）。

### 2026-11-17：测试数据看板 → 产线工站监控（完全重写）

**需求演变**：从 Redis 数据源改为 **SQLite 汇总表 station_summary**（前端只读、不算业务逻辑；后端负责维护汇总表与原始流水）。

**后端新增**：
- `engine.py` 新增 `station_summary`（device_id,name,status,barcode,total,first_pass,retest_pass,fail + 后来加的 status_since,test_duration）与 `station_fail_detail`（失败项明细：device_id,test_item,barcode,failed_at）。
- `repositories/station_repo.py`：`get_by_device()` / `list_fail_details()` 只读查询。
- `seed.py`：`seed_station_summary()` 写入演示数据（设备 ID 最终统一为设备注册页的 TEST-xx），失败明细 7 条。
- 依赖：`streamlit-autorefresh`、`plotly`、`streamlit-sortables` 加入；`redis` 已移除。

**页面（ui/page_dashboard.py）最终结构**：
- 标题「产线测试工站监控｜设备主动上报」。
- 默认折叠 expander「⚙️ 监控设备管理与显示设置」：内含监控设备管理（data_editor：设备编号/设备名称/所属线体/所属工序/删除列；新增设备从设备注册页 enabled 设备按产线+工序筛选后选择；保存修改；删除确认 dialog）+ 调整显示顺序（每行卡片数 number_input 1~12；sort_items 横向拖拽排序，key 含设备列表指纹避免删除后组件状态不同步）。
- 设备来源：`config/device_config.json`（只控制"显示哪些设备"），新增/删除/改名/排序写回该文件；config 保留 line_id/line_name/step_no/step_name。
- 卡片区：用 `@st.fragment(run_every=1000)` **只局部刷新卡片**（不再全局 autorefresh，避免删除弹窗闪烁）；放在 `st.tabs(["设备页"])` tab 容器里（与卡片内部 tab 同款样式）。
- 每张卡片：设备名居中（无括号 ID）→ 条码 text_input（label_visibility=collapsed，20px 蓝色加粗）→ 状态块（状态居中 + 右侧 HH:MM:SS 时间小字；通过/失败显示 test_duration 用时，其他显示 status_since 持续时间）→ 三个 tab：**统计**（plotly 横向柱状图 140px，hover 数量+百分比，total=0 显示 `--`）/ **失败详计**（dataframe 两列：条码/失败信息，height=120 可上下滚动）/ **设备控制**（预留空页）。
- 每个 tab 内容固定高度 150px 容器，切换 tab 卡片大小不变；每行固定 n_cols 列（不足补空），卡片大小一致不填满行。

**验证**：144 passed（含新增 test_variable_tree.py 等）；AppTest 多次确认渲染无异常。

**当前未提交 git 的改动**：pyproject.toml、uv.lock、engine.py、seed.py、page_dashboard.py、test_architecture.py、test_ui_smoke.py、config/、repositories/station_repo.py。

**补充（2026-11-17 同步时）**：README.md 已更新「功能一览」与「页面说明」两处的看板描述（产线工站监控 / station_summary / 失败详计 / 1s 局部刷新 / 设备拖拽排序），并在技术栈段落标注看板依赖 plotly + streamlit-sortables、刷新用 @st.fragment。

### 2026-11-17：新增「产品查询」页面（追溯 + 解绑）

**新增文件**：
- `repositories/product_query_repo.py`：只读查询工件（按产品/工件码/状态/时间范围）、工件详情、测试履历、工艺路线、产品信息、解锁记录、产品列表。
- `api/routers/product_query.py`：5 个只读 API（/api/ui/product/options, /workpieces, /workpiece/{id}/detail, /workpiece/{id}/history, /route/{model}），注册到 app。
- `ui/page_product_query.py`：查询条件（产品/工件码/状态/时间）→ 结果表格+选工件 → 详情（基本信息、工艺路线、测试履历/解锁记录两个 tab、工序解绑表单）。解绑复用 `client.unlock_workpiece`，原因必填+勾选确认。

**导航**：streamlit_app.py 新增「产品查询」页（url_path=product_query），位于测试数据看板之后。

**services** 增加 query_workpieces/workpiece_detail/workpiece_test_history/workpiece_unlock_history/product_route_detail/distinct_products 薄封装。

**验证**：144 passed；新 API 实测（产品列表/工件列表/详情/履历）正常；agent API 确认页面 ready 无异常。

### 2026-11-17 下午/晚间续：产品查询页 + skill 合规整改

**产品查询页**（ui/page_product_query.py）：查询条件（产品/工件码/状态/时间）+ 查询结果 + 追溯详情（基本信息/工艺路线/测试履历/解锁记录）+ 工序解绑（复用 unlock 用例，原因必填+勾选）。新增 product_query_repo + API 路由 + client 方法 + 导航入口。所有区块一次排开；首次自动加载全部，改条件后点“查询”按钮过滤（实时查询时序不稳已修复）。时间控件最终用两个原生 st.datetime_input（format=YYYY/MM/DD, step=60, value=None），精确到分钟。

**seed 修复**：report_test_result 补传 program_sha256，工件状态正确推进为 PASS(20)/FAIL(5)，此前全停留 PENDING 导致产品查询按状态查不到。

**Streamlit skill 合规整改**：
- COMPACT_CSS 从 st.markdown(unsafe_allow_html=True) 改为 st.html()；私有 data-testid 选择器改为 .st-key-barcode_*；去掉 .block-container 等私有类。
- 状态块/卡片标题改用 st.html()；去掉纯间隔 div 的 markdown。
- 所有 st.dataframe / st.data_editor / st.plotly_chart 补 alt=（看板/工序锁/产品查询/程序页/型号关联）。
- 验证：unsafe_allow_html=0、use_container_width=0，144 passed，agent API 多页 ready 无异常。

**看板 UI 细节**：设备页从单标签 tab 改为 bordered container 内嵌 tab；删除设备后 sort_items key 含列表指纹避免不同步；卡片 tab 固定高度 150px；每行卡片数可调；设备列表与注册页列一致（编号/名称/线体/工序/删除）。

**当前改动均未提交 git**（context 与工程代码都有）。

### 2026-11-18 MES V1.3 上传改造完成

- 新增 schemas_v1.py / application/upload_test_result_v1.py / repositories/upload_repo.py / engine.upload_requests 表。
- station_repo 新增 apply_result/ensure_device（上传时维护看板汇总）。
- test_result router 同时提供 V1.3 整单接口和旧单条接口。
- 新增 tests/test_upload_v1.py（6 个用例）。
- design_data/system_design_framework/manual.md 已按方案 A 改措辞。
- 全量测试：150 passed。
- 服务已用 pwsh 重启，8000/8501 正常。

### 2026-11-18 文档同步（README + design_data）

- README.md：技术栈/取舍改为“FastAPI 写入唯一入口，看板经 Repo 只读”；设备接口表加 V1.3；新增 6.3 整单上传章节 + 6.3b 旧接口；目录/数据模型（+station_summary/station_fail_detail/upload_requests、variables float）；验收加第 8 条；测试数 39→150；刷新 10s→1s；部署/FAQ 同步。
- design_data/MesFormat/MES上传接口文档.md：littleValue→LowerValue（以 JSON 示例为准）；5.3 码表标注已实现；待确认事项两项勾选已落地。
- design_data/system_design_framework/manual.md：上一轮已按方案 A 改措辞（FastAPI 写入唯一入口 + 看板只读例外）。

### 2026-11-18 System_Architecture_Diagram.drawio 同步

- 之前只更新了 manual.md，架构图 drawio 仍是旧的 /api/upload /api/records 接口名。
- 本轮更新：FastAPI 节点改为实际接口（含 POST /api/v1/test-results V1.3 + 旧单条）；Repository 节点改为实际 repo（含 station_repo 只读 / upload_repo 幂等）；新增“station_summary 看板汇总表（Repository 只读旁路）”节点与 Streamlit→Repo 只读虚线；机台→FastAPI 连线改为 HTTP POST /api/v1/test-results。XML 校验通过（17 cells）。

### 2026-11-18 产品查询页交互重构

- 用户指出“查询条件往后设计思路有问题”。已重写 page_product_query.py：
  - 状态过滤 selectbox → st.segmented_control（4 个选项一眼看全）；
  - 查询结果 st.dataframe 改为 on_select="rerun" + selection_mode="single-row"，点行选中工件；
  - 删除“选择工件查看追溯”下拉框 + “查看追溯详情”按钮；
  - 点行写 pq_current，查询后若已选工件仍在新结果中则保留，否则清除；不再默认展示第一个；
  - 详情区整体包一个 bordered container；工艺路线用 expander；测试履历/解锁记录/工序解绑改为三个 tabs。
- 验证：py_compile 通过；AppTest 零异常，segmented_control 生效；全量 pytest 150 passed；UI 已重启。

### 2026-11-18 JSON 字段顺序调整同步

- 用户调整 mesUploadTestDataFormat.json：programname/programversion 从末尾移到 linecode 之后。字段集合不变，仅顺序。
- 同步：MES上传接口文档.md（3.1 结构、3.2 字段表、3.4 示例）、README.md 6.3 示例、schemas_v1.py TestResultUploadIn 字段顺序、tests/test_upload_v1.py payload。
- JSON 对象顺序不影响 Pydantic 解析，代码功能不变；test_upload_v1.py 6 个用例通过。

### 2026-11-18 整单主子表 + 测试履历展示完成

- engine.py：新增 test_reports/test_report_details，删除 upload_requests。
- 新增 repositories/report_repo.py：insert_report（主子表同事务）、get_by_request_id、list_reports。
- 改 upload_test_result_v1.py：写主子表、幂等用 request_id、保留 station_summary 汇总和旧 test_results 联锁写入。
- 改 product_query_repo/services：workpiece_test_history 优先整单、回退旧表。
- 改 page_product_query.py：新增 _render_test_history，整单顶层字段文本框、details 列表；旧记录表格兼容。
- seed.py：新增 seed_test_reports 演示数据（SN202611170001）；已执行 seed --reset --demo。
- 测试：新增 test_v1_upload_master_detail_history；全量 151 passed；API/UI 已重启。

### 2026-11-18 演示整单数据改为从 JSON 派生 10 份

- seed_test_reports() 改为读取 design_data/MesFormat/mesUploadTestDataFormat.json 作模板，派生 10 份不同整单（SN202611180001~0010），每份不同 station/linecode/programname/programversion/testtime/testlongtime/result/明细实测值与判定；写入主子表共 10 reports + 20 details。
- 已执行 seed --reset --demo 验证：10/20 条正确；全量 pytest 151 passed。

### 2026-11-18 产品查询测试履历展示修正（按用户原意）

- 用户指出上一版把顶层字段做成 8 个 text_input 很怪。已改为：每个 V1.3 整单一个容器，上方用一个只读 st.text_area 按 JSON 格式显示顶层字段（station/linecode/programname/programversion/testtime/barcode/result/testlongtime，不含 details），下方用 dataframe 显示 details 列表。
- 旧单条记录仍用表格兼容。
- 验证：py_compile + AppTest 零异常；全量 pytest 151 passed；UI 已重启。

### 2026-11-18 修复产品查询显示旧数据问题

- seed 写 workpieces 主表 + product_query_repo 补入 report-only 工件；AppTest 选中 SN202611180001 验证 text_area（255 字符 JSON）+ details dataframe 正常；全量 151 passed；杀掉重复进程后重启 API/UI。

### 2026-11-18 JSON 字段变更 + 显示要求落地

- 按新 JSON 全链路改字段；seed 重新派生 10 份（含 componentcode）；删除旧库重建；验证 reports=10/details=20，首单 componentcode=L120201091。
- 产品查询：顶层 9 个只读文本框，details 10 列（含 id）；AppTest 验证 0 异常、10 text_inputs、details 10 列；全量 pytest 151 passed；服务已重启。

### 2026-11-18 明细独立库完成

- 实施 ADR-027；验证 10 产品=10 张表、每表 id 从 1 开始；README 配置/数据模型已更新；全量 pytest 151 passed；服务已重启。

### 2026-11-18 report_index 总览表 + isfinalreport 完成

- 实施 ADR-028；总览表写入/查询在 report_details_store；seed 派生数据写入总览表；新增测试 test_v1_upload_writes_overview；全量 152 passed；服务已重启。

### 2026-11-18 六点要求完成

- 按 ADR-029 完成；重启 API/UI；全量 152 passed；演示库 TestReport.db 含 10 SN_ 表 + report_index、无 sqlite_sequence。

### 2026-11-18 data 清理 + 明细动态列

- 清理 data/ 下 16 个旧 DB 备份文件；保留 mes.db/TestReport.db 及 programs。
- page_product_query 测试明细改为动态列 + 首位序号列；全量 pytest 152 passed；UI 已重启。

### 2026-11-18 数据库约定文档

- 按用户要求只写文档不改代码；新建 design_data/DatabaseConventions 两份约定文档；manual.md 增加引用；context 记 ADR-030。

### 2026-11-18 ADR-031 首版完成

- 实现按工序分测试库与 ProductFlow 首版；工序输入限制英文数字；产品查询新增产品流转 tab；seed 生成 S1/S2/S3 工序库和 ProductFlow.db；全量 152 passed；服务已重启。

### 2026-11-18 流转规范化 6 点完成

- 时间与状态规范化、列名/备注、解锁页设计、去掉解锁记录 tab；重建 ProductFlow.db；清理 18 个备份库；全量 152 passed；API/UI 已重启。

### 2026-11-18 产品查询交互修复

- 产品流转按当前条码过滤并自动选中；解绑页识别 ProductFlow lock；解锁支持 flow-only；全量 152 passed；API/UI 重启。

### 2026-11-18 产品查询改造完成

- 按 ADR-033 完成 3 点；服务重启；全量 152 passed。

### 2026-11-18 产品查询页面结构再调整

- 测试履历独立成查询结果同级块；详情 tab 只保留产品流转/工序解绑；查询条件保留一个工序下拉框；UI 重启；全量 152 passed。

### 2026-11-18 详情区精简完成

- 按 ADR-035 完成 4 点；UI 重启；全量 152 passed。

### 2026-11-18 查询条件与表头调整完成

- 按 ADR-036 完成；全量 152 passed；API/UI 重启。

### 2026-11-18 查询结果改为流转总览完成

- 按 ADR-037 完成；API/UI 重启；全量 152 passed。

### 2026-11-18 查询条件顺序最终调整

- 查询下拉顺序按 product_overview 字段：barcode/componentcode/board_status/current_step/last_report_device；查询按钮放第二行左下。AppTest 0 异常；全量 152 passed；UI 重启。

### 2026-11-18 演示数据扩充

- seed_test_reports 改为 10 个产品 × 3 道工序（S1/S2/S3）× 每份报告 10 条测试明细。
- 验证：主库 test_reports=30；db_1_S1/db_2_S2/db_3_S3 各 10 份 report_index、100 条明细；ProductFlow overview=10、每产品 3 条流转记录（共 30）。
- 清理旧备份库；全量 152 passed；API/UI 重启。

### 2026-11-18 看板统计时间区间完成

- 按 ADR-038 完成 5 点；UI 重启；全量 152 passed。

### 2026-11-18 看板工序页完成

- 按 ADR-039 新增工序页 tab；全量 152 passed；UI 重启。

### 2026-11-18 工序页与时间区间/刷新联动

- 设备页和工序页统一用 _device_stats(device_id, applied_stat_range) 获取统计；有生效区间则按各工序库 report_index 统计，否则读 station_summary。
- 两页仍各自 @st.fragment(run_every=refresh_interval) 每 1 秒刷新；工序页显示当前生效区间 caption。
- AppTest：看板 0 异常；区间 caption 正确输出；全量 152 passed；UI 重启。

### 2026-11-18 阶段性任务完成：前端页面功能基本完成

- 产品查询：查询结果改用 ProductFlow.product_overview；筛选字段按数据库字段名与顺序；测试履历独立成同级块并按工序分 tab；产品流转/工序解绑顺序排列；工序解绑可任切工序并写备注。
- 测试数据看板：设备页 + 工序页 tabs；监控设备管理 / 设置显示两个同级折叠容器；设置显示含卡片顺序、每行卡片数、统计时间区间（可点选 datetime、清空、查询才生效）；两页均 1 秒 fragment 刷新且共用 applied_stat_range。
- V1.3 上传、按工序分测试库、ProductFlow 流转库、演示数据扩充（10 产品 × 3 工序 × 10 明细）均稳定。
- 整理：README/数据模型/页面说明同步；清理 __pycache__、临时脚本、日志；compileall 通过；全量 pytest 152 passed；API/UI 重启。
