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
