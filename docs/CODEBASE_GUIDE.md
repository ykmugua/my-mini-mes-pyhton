# 项目代码详解

本文档面向维护者，说明 `my-mini-mes-pyhton` 的代码组织、关键函数职责、设计模式和使用的框架。面向使用者的快速上手与接口说明见 [README.md](../README.md)。

---

## 1. 项目定位

本项目是设备乙方内部使用的旁路式小型 MES。它不接入甲方 MES，只覆盖现场调试和测试数据闭环需要的能力：

- 设备通过 HTTP 拉取程序、上报程序状态、上报测试结果、查询放行状态、读写开放变量；
- 工程师通过 Streamlit 页面维护主数据、查看看板、查询产品流转与测试报告、执行工位操作；
- 所有持久化数据落在本地 SQLite 数据库文件中。

核心设计目标是：**协议可追溯、状态可解释、页面与设备接口解耦、测试数据不被业务操作误删**。

---

## 2. 框架与技术栈

| 层次 | 技术 | 说明 |
| --- | --- | --- |
| HTTP 接口 | FastAPI | 提供设备接口和 UI 数据接口，使用 Pydantic 模型校验请求 |
| 页面 | Streamlit | 内部工具页面，使用 `st.navigation` 组织多页面 |
| 数据访问 | SQLAlchemy Core | 只用 Core 和 `text()`，不引入 ORM 实体映射 |
| 数据库 | SQLite（WAL） | 主库 `mes.db`、流转库 `ProductFlow.db`、报告库 `TestReport.db` |
| 测试 | pytest、AppTest | 接口测试、业务规则测试、架构约束测试、Streamlit 页面冒烟 |
| 配置 | 环境变量 | 所有路径、地址、时区均可通过 `MES_*` 环境变量覆盖 |

---

## 3. 目录分层

```text
src/py_server/
├── api/                  FastAPI app、schemas、routers
├── application/          多步骤业务用例，负责事务编排
├── domain/               纯业务规则，无框架依赖
├── repositories/         唯一允许直接执行 SQL 的层
├── ui/                   Streamlit 页面与 HTTP client
├── config.py             路径/地址/时区配置
├── constants.py          跨层业务常量
├── engine.py             SQLAlchemy Engine 与表定义
├── db.py                 时间工具与初始化入口
├── services.py           兼容入口：输入校验 + 委托下层
├── seed.py               演示数据生成
└── streamlit_app.py       Streamlit 页面入口
```

### 分层依赖方向

```text
ui ──HTTP──▶ api/routers ──▶ services ──▶ application ──▶ domain
                                  │              │
                                  └──────────────┴──▶ repositories ──▶ engine.py ──▶ SQLite
```

约束：

- `domain/` 不依赖任何框架，也不访问数据库；
- `repositories/` 是唯一写 SQL 的目录；
- `ui/` 只通过 `ui/client.py` 调 HTTP 接口，不直接访问 repository 或数据库；
- `api/routers/` 只负责参数声明和调用下层；业务校验放在 services/application。

新增规则时按以下默认位置放置：

| 规则类型 | 默认位置 | 示例 |
| --- | --- | --- |
| 请求头和字段格式校验 | API / Pydantic schema | 必填请求头、`x-device-sn == station`、UUID 格式 |
| 依赖外部状态的准入检查 | services / application + repositories | 设备 SN 是否注册、设备是否启用、载具是否占用 |
| 幂等和查重 | application + repositories + 数据库约束 | `request_id` 重复、UUID 重复、测试项重复冲突 |
| 依赖统计或配置的流程卡控 | application / services | 设备使用次数超限、当班容量上限 |
| 纯业务状态机和稳定策略 | `domain` | 工件锁定不能直接 PASS、程序版本/SHA 判定、放行顺序 |

`domain` 不是所有限制规则的集合。只有“不需要查库、不依赖接口协议、只用传入的业务事实即可判定，并且规则稳定”的逻辑才进入 `domain`。

业务术语定义见 [GLOSSARY.md](../GLOSSARY.md)；domain 边界决策记录在 `.context/architecture.md`。

---

## 4. 运行模型

系统由两个进程组成：

```text
设备 ──HTTP/JSON──▶ FastAPI :8000 ──▶ SQLite
浏览器 ───────────▶ Streamlit :8501 ──HTTP──▶ FastAPI :8000
```

Streamlit 默认用 `MES_UI_API_BASE=http://127.0.0.1:8000` 访问接口，避免访问本机内网 IP 时经过代理导致 502 或慢加载。设备侧程序下载地址使用 `MES_API_PUBLIC_BASE`，默认是本机内网 IP。

---

## 5. 核心模块与函数职责

### 5.1 配置层：`config.py`、`constants.py`

- `config.data_dir()`：返回运行期数据目录。
- `config.db_path()`：主库路径。
- `config.details_db_path()`：唯一测试报告库路径。
- `config.product_flow_db_path()`：产品流转库路径。
- `config.ui_api_base()`：Streamlit 调 FastAPI 的地址，默认回环地址。
- `config.api_public_base()`：设备可访问地址，用于下载 URL。
- `constants.py`：集中定义 `PASS/FAIL`、`normal/lock/final`、`LOCK/END`、`true/false`、`全部`、变量类型、权限角色等常量，避免魔术字符串散落。

### 5.2 接口层：`api/`

#### `api/app.py`

- `lifespan()`：服务启动时初始化数据库和程序目录。
- `service_error_handler()`：把 `ServiceError` 转成带 HTTP 状态码的 JSON 错误。
- `app`：注册所有 router。

#### `api/routers/device/program.py`

- `health()`：健康检查。
- `download_program_file()`：下载程序文件，路径在 repository 中做安全校验。
- `get_program()`：设备拉取程序绑定；同时记录拉取日志。
- `post_program_status()`：设备上报程序版本、SHA256、自检结果。
- `/api/ui/*`：页面读取/保存程序绑定、漂移、日志、发布程序。

#### `api/routers/device/test_result.py`

- `post_test_results_v1()`：V1.3 整单上报。校验请求头、构造 envelope、调用 `upload_test_result_v1.execute()`。

#### `api/routers/ui/master_data.py`

- `get_master()`：一次返回所有主数据快照。
- `get_master_key()` / `save_master_key()`：单项读写主数据。
- `save_master_key()` 还负责主键改名同步：
  - 组件号改名：同步 `processes.component_no` 与 `ProductFlow.componentcode`；
  - 程序名改名：同步 `process_step_resources.program_name`；
  - 工艺号改名：同步 `process_routes.process_code` 与 `process_step_resources.process_code`。

#### `api/routers/ui/product_query.py`

- 产品流转查询、测试报告查询、报告明细、删除入站状态、工位操作台接口都在这里。
- 复杂查询委托给 `repositories/report_query_store.py`。
- 业务操作委托给 `services.py`。

### 5.3 业务入口层：`services.py`

`services.py` 是对外业务入口，负责输入校验并委托下层。它主要负责：

- 输入清洗：`_clean_text()`、`_clean_sha256()`、`_clean_url()`；
- 领域错误到 HTTP 错误的映射：`ServiceError`、`ValidationError`、`NotFoundError`、`ConflictError`；
- 简单 CRUD 薄封装；
- 复杂逻辑委托给 `application/`；
-工位入站检查：只根据 ProductFlow 当前状态判断占用，不再把 `workpieces` 中存在记录误判为占用。

关键函数：

- `report_program_status()`：先校验绑定和上报内容，再调用 application 记录状态。
- `report_test_result()`：校验工件码、设备、测试项、结果和时间，再写入测试结果并维护联锁状态。
- `interlock_check()`：聚合设备可信性、工件状态、前道规则，调用 `InterlockPolicy` 得到放行结论。
- `manual_inbound()`：校验产品、工艺、工序、载具型号、容量、占用，再创建产品流转和工件占位。
- `delete_product_flow()` / `delete_tray_flow()`：删除入站状态；不删除测试报告。

### 5.4 应用层：`application/`

应用层持有事务边界，负责多表协作。

#### `upload_test_result_v1.py`

- `execute()`：V1.3 整单上报主流程。
  1. 校验请求头和结果字段；
  2. `request_id` 幂等检查；
  3. 每条明细触发内部单条结果上报，保留可信性/联锁链路；
  4. 写 `test_reports` 主表和工序明细表；
  5. 写对应工序的 `report_index_<step>` 总览表；
  6. 写 ProductFlow 当前状态；
  7. 更新 station 看板汇总。

#### `report_test_result.py`

- `execute()`：单条测试结果入库。
- `evaluate_trust()`：根据绑定版本、SHA256、自检状态判断设备是否可信。

#### `unlock_workpiece.py`

- `execute()`：工件解锁。必须确认并写解锁日志；若指定目标工序，同时更新 ProductFlow 流转锁。

#### `station_workbench.py`

- `manual_inbound()`：写入工件占位与 ProductFlow 首条流转记录。
- `unbind_tray()`：整盘解绑，写一条 `托盘解绑` 流转历史，删除 `active_products` 当前在制记录，并兼容清理 ProductFlow 总览。
- `delete_product_flow()` / `delete_tray_flow()`：删除入站状态，并清理无测试数据的工件占位；测试数据保留。

### 5.5 领域层：`domain/`

领域层是纯 Python 业务规则。

- `domain/trust/policy.py::ProgramTrustPolicy`：程序可信规则。
- `domain/trust/verdict.py`：可信结论值对象。
- `domain/interlock/policy.py::InterlockPolicy`：放行判定顺序：
  1. 设备程序可信；
  2. 工件未锁定；
  3. 工件非 FAIL；
  4. 人工放行；
  5. 前道关键设备均有可信 PASS。
- `domain/workpiece/model.py::Workpiece`：工件状态聚合，负责状态变更但不写库。
- `domain/workpiece/manual_release.py`：人工放行结果值对象定义保留在文档中；实际状态字段在 `Workpiece` 中。

### 5.6 数据访问层：`repositories/`

#### `base.py`

- `with_conn()` / `with_read_conn()`：读写事务上下文。
- `Result`、`RowWrapper`：对不同 SQLAlchemy 结果形态做统一封装。
- `rows_to_dicts()`：把查询结果转成普通字典。

#### `workpiece_repo.py`

- `get_workpiece()`：查询工件主记录。
- `insert_workpiece_ignore()`：入站时幂等插入工件占位。
- `delete_workpiece_if_no_tests()`：仅当没有测试结果和报告时删除工件占位，保证删除入站状态不会误删测试数据。
- `lock_workpiece()` / `fail_workpiece()` / `pass_workpiece()`：更新工件状态。

#### `product_flow_store.py`

- `product_overview`：当前入线状态总览。
- `F_<barcode>_<hash>`：每产品一张流转历史表。
- `list_overview()`：按条码/组件/托盘/状态/工序筛选当前状态。
- `create_inbound()`：创建入站状态与首条流转。
- `unbind_tray()`：整盘解绑。
- `delete_product()` / `delete_tray()`：删除当前入站状态和对应流转表。
- `rename_componentcode()`：组件号改名时同步总览表组件号。

#### `report_details_store.py`

测试报告统一放在 `TestReport.db`，但在库内按工序分表：

- `report_index_<step_no>`：每道工序一张报告总览表；
- `SN_<step>_<barcode>_<hash>`：每条报告/每个条码在对应工序下的明细表；
- `ensure_overview_table()` / `ensure_table()`：保证表存在；
- `insert_overview()` / `insert_details()`：写入报告总览与明细；
- `list_overview()`：按工序读取，避免不同工序 details 混在一起；
- `list_details_by_table()`：按表名精确读取明细，表名格式严格校验。

#### `report_query_store.py`

- `report_engines()`：统一报告库入口；
- `list_report_index()`：按条码/工序读取报告总览；
- `list_details()`：按 `details_table` 读取明细；
- `latest_traycodes()`：按条码取最后一次测试上报托盘码；
- `filter_options()`：构造报告查询筛选选项；
- `query_reports()`：按产品、工序、条码、托盘、结果、板状态等条件查询报告。

#### `master_data_repo.py`

- `snapshot()`：一次返回工序、设备、载具、程序、版本、组件、工艺、路线、资源九类主数据。
- `replace_*()`：整表替换主数据；页面保存时先全量校验再写回。
- `list_program_history()`：按程序名查历史版本。

### 5.7 UI 层：`ui/`

#### `ui/client.py`

唯一 HTTP 客户端。

- `_request()`：统一发 HTTP 请求，解析错误，支持测试模式 `MES_UI_INPROCESS=1`；
- `_cached_get()`：失败时返回 session_state 中上次成功数据，并显示降级提示；
- 其余函数按业务分组包装 FastAPI 接口。

#### `ui/common.py`、`ui/pages/_common.py`

- `common.init_session()`：初始化操作员、角色；
- `common.can_edit()`：统一权限判断；
- `common.show_error()`：显示接口降级提示；
- `pages/_common.py::ensure_master_data()`：首次加载主数据，失败时写入空列表避免页面崩溃；
- `pages/_common.py::save_key()`：保存当前 session_state 中的主数据到后端。

#### 注册页通用骨架：`ui/pages/registry_helpers.py`、`constants.py`

设备、载具、工序、组件四类注册页已经统一到同一套逻辑：

- `clean_text()`：清洗编辑器空值；
- `is_editable()`：判断只读/可编辑；
- `enabled_from_text()` / `enabled_from_cell()`：统一启用值转换；
- `make_frame()`：字典列表转 DataFrame；
- `request_delete()` / `clear_pending()`：删除按钮到确认弹窗的 pending state；
- `save_rows()`：写 session_state、调用接口保存、提示成功并 rerun。

`constants.py` 集中定义角色、启用选项、空值占位、工序号正则等 UI 常量。

#### 页面清单

- `page_dashboard.py`：测试数据看板。
- `page_workbench.py`：工位操作台（手动入站、入线状态、托盘解绑、产品解锁）。
- `tag_page.py`：入线状态内容与删除弹窗。
- `page_product_query.py`：产品流转查询、测试报告查询、测试履历。
- `page_program.py`、`page_variables.py`：旧版/简化页面入口。
- `pages/registration_hub.py`：统一注册入口，用标签页承载程序、工序、设备、载具、组件。
- `pages/process_config.py`：独立工艺配置页，支持工艺号修改、从模板新建、路线/资源维护。
- `pages/program.py`：程序注册，支持程序名修改和版本维护。

---

## 6. 数据库设计

### `mes.db`

主库，保存：

- 主数据：`steps`、`devices`、`trays`、`products`、`processes`、`process_routes`、`process_step_resources`；
- 程序：`programs`、`program_versions`、`program_bindings`、拉取/状态日志；
- 测试：`test_results`、`test_reports`；
- 工件：`workpieces`、`unlock_logs`；
- 变量：`variables`、`variable_logs`；
- 看板：`station_summary`、`station_fail_detail`；当前在制：`active_products`。

### `ProductFlow.db`

- `product_overview`：ProductFlow 当前入线状态（历史兼容）；
- `F_<barcode>_<hash>`：每产品流转历史；
- 状态：`normal`、`lock`、`final`；
- 终端下站：`LOCK`、`END`。

### `TestReport.db`

统一测试报告库，按工序分表：

- `report_index_1`、`report_index_2`、……：每工序一张总览；
- `SN_<step>_<barcode>_<hash>`：每工序每条码一张明细；

---

## 7. 设计模式

### 7.1 分层架构（Layered Architecture）

- Router 处理 HTTP；
- Service 提供业务入口和输入校验；
- Application 编排事务；
- Domain 表达少量纯业务规则（可信性、联锁、工件状态机），不是万能校验层；
- Repository 封装 SQL；
- Engine 管理连接和表结构。

好处：规则可测试、SQL 可替换、UI 不依赖数据库。

### 7.2 外观模式（Facade）

`services.py` 是典型 Facade：调用者不需要知道 application/domain/repository 的细节，可通过 `services.report_test_result()`、`services.manual_inbound()` 等函数完成业务。

### 7.3 值对象（Value Object）

`Workpiece`、`Binding`、`TrustVerdict`、`UnlockOutcome` 等 dataclass 表达业务事实，很多是 frozen，避免误改。

### 7.4 策略模式（Strategy）

`ProgramTrustPolicy` 和 `InterlockPolicy` 把判断规则从流程代码中剥离，便于单独测试和调整。

### 7.5 Repository 模式

所有 SQL 都在 repositories 下，上层只调用语义化函数，如 `list_overview()`、`insert_overview()`，不写 SELECT/UPDATE 字符串。

### 7.6 幂等模式

- 测试结果唯一键：`(workpiece, device_id, test_item)`；
- V1.3 主表幂等键：`request_id`；
- 入站工件占位：`INSERT ... ON CONFLICT DO NOTHING`。

### 7.7 状态机模式

- 工件状态：`PENDING/PASS/FAIL`；
- 流转状态：`normal/lock/final`；
- 终端下站：`LOCK/END`；
- 可信状态：`trusted/untrusted`。

### 7.8 Session State + Pending State（Streamlit）

删除操作分两步：

1. ButtonColumn 点击时把目标主键写入 `session_state[pending_key]`；
2. 下一次 rerun 根据 pending 打开确认 dialog。

这样避免回调期间直接删数据导致弹窗不显示。

---

## 8. 关键流程

### 8.1 V1.3 测试上报

```text
POST /api/v1/test-results
  └─ test_result router：请求头 + schema 校验
      └─ upload_test_result_v1.execute()
          ├─ request_id 幂等
          ├─ 每条明细调用单条上报（可信性/联锁）
          ├─ 写 test_reports
          ├─ 写 TestReport.db: SN_<step>_... 明细表
          ├─ 写 TestReport.db: report_index_<step> 工序总览
          ├─ 写 ProductFlow.db 当前状态和历史明细，并同步 mes.db.active_products
          └─ 更新 station_summary / station_fail_detail
```

### 8.2 手动入站

```text
POST /api/ui/workbench/inbound
  └─ services.manual_inbound()
      ├─ 产品型号启用校验
      ├─ 工艺启用校验
      ├─ 工序路线与载具型号校验
      ├─ 托盘容量与占用校验
      ├─ ProductFlow 当前状态校验
      └─ station_workbench.manual_inbound()
          ├─ mes.db.workpieces 插入占位
          └─ ProductFlow.db 写总览与首条流转
```

### 8.3 删除入站状态

```text
DELETE /api/ui/product/flow 或 /tray-flow
  └─ services.delete_product_flow/delete_tray_flow
      └─ station_workbench.delete_*()
          ├─ 删除 ProductFlow 总览和流转表
          └─ 仅当无测试结果、无测试报告时删除 workpieces 占位
```

测试数据和报告不会被删除。

---

## 9. 魔术值清理策略

之前散落在代码中的协议/状态字符串已集中到：

- `src/py_server/constants.py`：跨层业务常量；
- `src/py_server/ui/pages/constants.py`：UI 常量；
- `domain/*` 中的 Enum：领域状态值。

后续新增状态或协议字段时，应优先在这些位置定义常量，避免直接写字符串。

---

## 10. 注释规范

- 每个 Python 文件必须有模块 docstring；
- 每个公开函数、类都要有 docstring；
- 私有函数如果有业务语义，也要写 docstring；
- 注释说明“为什么这样做”，代码本身表达“做了什么”；
- 修改业务流程时同步更新本文档和 README。

---

## 11. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

覆盖：

- 设备接口与 V1.3 上报；
- 程序可信性、联锁与解锁；
- ProductFlow 入站/解绑/删除；
- 测试报告查询与工序隔离；
- 页面 AppTest 冒烟；
- 架构约束测试（domain 无框架依赖、UI 不直连数据库、注册页复用公共逻辑）。

最近一次全量测试：`109 passed`。
