# 项目了解路线图

本文档面向需要快速理解 `my-mini-mes-pyhton` 的维护者。它回答两个问题：

1. 应该按什么顺序阅读项目；
2. 每个模块、每个函数大致负责什么，遇到问题时去哪里找。

代码级架构说明见 [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md)；使用与部署说明见 [README.md](../README.md)。

---

## 0. 先看结论：这个项目的骨架

项目是一个旁路式小型 MES，分成两个进程：

```text
设备 ──HTTP──▶ FastAPI :8000 ──▶ services/application/domain ──▶ repositories ──▶ SQLite
浏览器 ─────▶ Streamlit :8501 ──HTTP──▶ FastAPI :8000
```

三层数据库：

| 数据库 | 作用 |
| --- | --- |
| `data/mes.db` | 主数据、程序绑定、工件、变量、看板汇总、`active_products` 当前在制表 |
| `data/ProductFlow.db` | `product_overview` 与每产品流转历史 `F_<barcode>_<hash>` |
| `data/TestReport.db` | 唯一测试报告库，按工序分表 `report_index_<step>` 与 `SN_<step>_<barcode>_<hash>` |

最重要的边界：

- `ui/` 只能经 `ui/client.py` 调 FastAPI，不准直接访问 repository 或数据库；
- `repositories/` 是唯一允许写 SQL 的地方；
- `domain/` 只放少量纯业务规则：程序可信、联锁放行、工件状态机；
- `application/` 编排多步骤业务用例；
- `services.py` 是对外业务入口和输入校验层。

新增卡控规则时不要默认塞进 `domain`：请求头校验放 API/schema，查注册/查次数/查占用放 services/application，幂等和查重放 application/repositories/数据库约束，纯业务状态机或稳定策略才考虑放 `domain`。

---

## 1. 建议了解顺序

### 第 1 步：先跑起来，建立感性认识

阅读：

- `README.md`
- `src/py_server/streamlit_app.py`
- `src/py_server/api/app.py`

目标：

- 知道 8000/8501 两个服务怎么启动；
- 知道 Streamlit 有哪些页面；
- 知道 FastAPI 注册了哪些路由分组：`routers/device`、`routers/ui`、`routers/common`。

关键函数：

| 文件 | 函数 | 作用 |
| --- | --- | --- |
| `api/app.py` | `lifespan()` | 启动 FastAPI 时初始化数据库和程序目录 |
| `api/app.py` | `service_error_handler()` | 把 `ServiceError` 转成 HTTP JSON 错误 |
| `streamlit_app.py` | 顶层代码 | 设置页面、初始化 session、注册 `st.navigation` 页面 |

---

### 第 2 步：看配置与表结构

阅读：

- `src/py_server/config.py`
- `src/py_server/constants.py`
- `src/py_server/engine.py`
- `docs/DatabaseConventions/`

目标：

- 知道所有路径、地址、时区怎么配置；
- 知道业务常量集中在哪；
- 知道 SQLite 表结构定义在哪；
- 分清 `mes.db` / `ProductFlow.db` / `TestReport.db` 的边界。

关键函数/对象：

| 文件 | 名称 | 作用 |
| --- | --- | --- |
| `config.py` | `data_dir()` / `db_path()` / `details_db_path()` / `product_flow_db_path()` | 运行期路径解析 |
| `config.py` | `ui_api_base()` / `api_public_base()` | UI 与设备访问 FastAPI 的地址 |
| `engine.py` | `metadata` | 所有主库表定义 |
| `engine.py` | `get_engine()` | 获取 `mes.db` Engine |
| `engine.py` | `get_details_engine()` | 获取 `TestReport.db` Engine |
| `engine.py` | `get_product_flow_engine()` | 获取 `ProductFlow.db` Engine |
| `engine.py` | `init_schema()` | 创建缺失表，不修改已有表 |

---

### 第 3 步：看最核心业务规则 `domain/`

阅读顺序：

1. `domain/trust/`
2. `domain/interlock/policy.py`
3. `domain/workpiece/model.py`

目标：

- 理解“设备可信性”怎么判断；
- 理解“放行/联锁”怎么判断；
- 理解工件锁定/解锁的状态规则。

边界提醒：这里只放纯规则。设备 SN 是否注册、设备使用次数是否超限、UUID/`request_id` 是否重复、载具是否被占用等流程卡控不在 `domain`，而是在 API/services/application/repositories 中。

函数索引：

| 文件 | 名称 | 作用 |
| --- | --- | --- |
| `domain/trust/policy.py` | `evaluate()` / `ProgramTrustPolicy` | 根据绑定、版本、SHA256、自检结果判定可信 |
| `domain/trust/fingerprint.py` | 指纹相关函数 | 从状态上报或测试结果提取程序指纹 |
| `domain/trust/verdict.py` | `TrustVerdict` | 可信性结果值对象 |
| `domain/trust/binding.py` | `Binding` | 程序绑定关系值对象 |
| `domain/interlock/policy.py` | `InterlockPolicy` | 判断工件是否允许启动/放行 |
| `domain/workpiece/model.py` | `Workpiece` | 工件聚合，表达 lock/unlock/pass/fail 规则 |
| `domain/workpiece/model.py` | `UnlockOutcome` | 解锁结果值对象 |

阅读方法：先只理解规则，不急着追谁调用它。后面看 `application/` 时再回来对照。

---

### 第 4 步：看业务编排 `application/`

阅读顺序：

1. `application/upload_test_result_v1.py`
2. `application/station_workbench.py`
3. `application/unlock_workpiece.py`
4. `application/report_program_status.py`
5. `application/report_test_result.py`

目标：

- 看 V1.3 上报如何写多个表；
- 看手动入站、托盘解绑、删除流转如何影响当前在制和流转历史；
- 看解锁如何同时更新工件与 ProductFlow；
- 看程序状态上报如何进入可信性判定。

关键函数：

| 文件 | 函数 | 作用 |
| --- | --- | --- |
| `upload_test_result_v1.py` | `execute()` | V1.3 整单上报主流程：幂等、逐明细上报、写报告库、更新状态 |
| `upload_test_result_v1.py` | `_parse_testexecutetime()` | 解析协议时间 |
| `upload_test_result_v1.py` | `_duration_seconds()` | 解析测试用时 |
| `station_workbench.py` | `manual_inbound()` | 手动入站：写 workpieces、ProductFlow、active_products |
| `station_workbench.py` | `unbind_tray()` | 托盘解绑：写解绑历史、删除当前在制 |
| `station_workbench.py` | `delete_product_flow()` | 删除单个产品当前流转状态 |
| `station_workbench.py` | `delete_tray_flow()` | 删除整盘当前流转状态 |
| `unlock_workpiece.py` | `execute()` | 解锁用例：校验、更新工件、写流转 |
| `report_program_status.py` | `execute()` | 程序状态上报用例 |
| `report_test_result.py` | `execute()` | 单条测试结果上报用例 |

---

### 第 5 步：看门面层 `services.py`

目标：

`services.py` 是上层调用业务能力的入口。它不是最核心规则所在，但所有 API/用例都从这里进出。

重点函数分组：

| 分组 | 函数示例 | 作用 |
| --- | --- | --- |
| 程序 | `record_program_pull()` / `report_program_status()` / `program_drift()` | 程序拉取、状态上报、漂移告警 |
| 测试上报 | `report_test_result()` / `query_workpieces()` / `workpiece_detail()` | 测试结果与查询 |
| 联锁/解锁 | `interlock_check()` / `unlock_workpiece()` / `list_locked_workpieces()` | 放行、解锁、锁定列表 |
| 工位 | `manual_inbound()` / `unbind_tray()` / `workbench_recipe()` | 入站、解绑、工艺规则 |
| 看板 | `dashboard_snapshot()` / `station_summary()` / `station_fail_details()` | 看板数据 |
| 变量 | `get_variable()` / `set_variable()` / `variables_tree_from_api()` | 开放变量 |
| 主数据 | `distinct_products()` / `product_route_detail()` / `delete_variable()` | 查询辅助 |

理解原则：

- 看到 `services.xxx()` 时，把它当成“业务入口”；
- 真正规则在 `domain/`；
- 多步骤编排在 `application/`；
- SQL 在 `repositories/`。

---

### 第 6 步：看 FastAPI 路由

阅读顺序：

1. `api/routers/device/`
2. `api/routers/common/`
3. `api/routers/ui/`
4. `api/schemas.py`、`api/schemas_v1.py`

目标：

知道每个 HTTP 请求进来后第一步发生什么。

路由文件：

| 文件 | 作用 |
| --- | --- |
| `routers/device/program.py` | `/health`、`/programs/{filename}`、`/api/program`、`/api/program/status` |
| `routers/device/test_result.py` | `/api/v1/test-results` |
| `routers/common/interlock.py` | `/api/interlock` 与 UI 解锁/前道规则接口 |
| `routers/common/variable.py` | `/api/variable/{name}` 与 UI 变量接口 |
| `routers/ui/dashboard.py` | 看板和设备列表接口 |
| `routers/ui/master_data.py` | 主数据快照、保存、程序历史 |
| `routers/ui/product_query.py` | 产品查询、报告查询、工位入站/解绑、当前在制 |

注意：

- 旧 `api/routers/*.py` 文件仍保留为兼容 re-export；
- 真正实现已移动到上述 `device/ui/common` 子目录；
- URL 没变。

---

### 第 7 步：看 Repository 层

阅读顺序建议按业务主题，而不是按文件名字母序：

1. 主数据：`master_data_repo.py`
2. 程序：`binding_repo.py`、`program_files.py`
3. 工件与结果：`workpiece_repo.py`、`report_repo.py`
4. 报告查询：`report_details_store.py`、`report_query_store.py`
5. 产品流转：`product_flow_store.py`、`active_product_repo.py`
6. 看板：`dashboard_repo.py`、`station_repo.py`
7. 其他：`variable_repo.py`、`upstream_repo.py`、`log_repo.py`、`product_query_repo.py`

重点理解：

| 文件 | 代表函数 | 作用 |
| --- | --- | --- |
| `master_data_repo.py` | `snapshot()` / `replace_*()` | 主数据总览与整体替换 |
| `binding_repo.py` | `record_pull()` / `insert_status_log()` / `list_pull_logs()` | 程序绑定与日志 |
| `report_details_store.py` | `ensure_overview_table()` / `insert_details()` / `insert_overview()` | 写 TestReport.db |
| `report_query_store.py` | `query_reports()` / `filter_options()` / `latest_traycodes()` | 报告查询聚合 |
| `product_flow_store.py` | `create_inbound()` / `close_tray_flow()` / `list_flow()` | ProductFlow 当前态和历史 |
| `active_product_repo.py` | `upsert()` / `list_active()` / `delete_tray()` | 当前在制产品表 |
| `workpiece_repo.py` | `insert_workpiece_ignore()` / `lock_workpiece()` / `unlock_workpiece_row()` | 工件主表 |
| `dashboard_repo.py` | `snapshot()` | 看板汇总 |

---

### 第 8 步：看 Streamlit UI

阅读顺序：

1. `ui/client.py`
2. `ui/common.py`
3. `page_dashboard.py`
4. `page_workbench.py`
5. `page_product_query.py`
6. `page_variables.py`
7. `pages/registration_hub.py`
8. `pages/process_config.py`

目标：

- UI 只通过 `client.py` 调 FastAPI；
- 页面状态集中在 `st.session_state`；
- 删除类操作通常用 pending state + dialog 两步确认。

关键文件：

| 文件 | 作用 |
| --- | --- |
| `ui/client.py` | 唯一 HTTP 客户端；所有请求从这里发出 |
| `ui/common.py` | 侧边栏、权限、错误提示、operator |
| `tag_page.py` | 当前已绑定托盘列表与行内解绑按钮 |
| `page_dashboard.py` | 测试数据看板；卡片数据从 TestReport.db 统计，状态从 station 接口来 |
| `page_workbench.py` | 工位操作台：入站、当前托盘、解绑、产品解锁 |
| `page_product_query.py` | 产品流转查询与测试报告查询 |
| `pages/registration_hub.py` | 注册配置总入口 |
| `pages/process_config.py` | 工艺配置 |

---

## 2. 跟一条完整链路读代码

### 链路 A：设备 V1.3 上报

```text
POST /api/v1/test-results
  -> api/routers/device/test_result.py: post_test_results_v1()
  -> application/upload_test_result_v1.py: execute()
       -> services.report_test_result()
       -> domain/trust：判断程序可信
       -> repository/report_repo.py：写 test_reports
       -> repository/report_details_store.py：写 TestReport.db 的 report_index_<step> 和 SN 明细
       -> repository/product_flow_store.py：写 ProductFlow 当前态和历史
       -> repository/active_product_repo.py：同步当前在制表
       -> repository/station_repo.py：维护 station_summary / station_fail_detail
```

### 链路 B：手动入站

```text
POST /api/ui/workbench/inbound
  -> api/routers/ui/product_query.py: ui_workbench_inbound()
  -> services.manual_inbound()
  -> application/station_workbench.py: manual_inbound()
       -> workpieces 插入工件占位
       -> ProductFlow 写当前总览与首条流转
       -> active_products 写当前在制
```

### 链路 C：托盘解绑

```text
POST /api/ui/workbench/tray-unbind
  -> api/routers/ui/product_query.py: ui_workbench_tray_unbind()
  -> services.unbind_tray()
       -> active_product_repo.list_active() 判断当前占用
       -> application/station_workbench.py: unbind_tray()
            -> product_flow_store.close_tray_flow()：写托盘解绑历史，清 ProductFlow 总览
            -> active_product_repo.delete_tray()：删除当前在制
```

### 链路 D：产品查询为什么能查到解绑后的工件

```text
GET /api/ui/product/workpieces
  -> services.query_workpieces()
  -> product_query_repo.list_workpieces()
       -> 主查 mes.db.workpieces
       -> 合并 ProductFlow 当前态字段
       -> 合并测试报告字段
```

所以即使托盘解绑后 `active_products` 和 `ProductFlow.product_overview` 被清掉，工件档案和测试报告仍在，产品查询仍可追溯。

---

## 3. 每个目录一句话总结

| 目录 | 一句话 |
| --- | --- |
| `api/routers/device` | 设备调用的 FastAPI 接口 |
| `api/routers/ui` | Streamlit 页面调用的 FastAPI 接口 |
| `api/routers/common` | 设备和 UI 都调用的接口 |
| `application` | 多步业务用例，负责顺序和事务边界 |
| `domain` | 纯业务规则，不依赖框架和数据库 |
| `repositories` | 唯一写 SQL 的地方 |
| `ui` | Streamlit 页面和 HTTP client |
| `docs` | 使用文档、代码说明、协议和数据库约定 |
| `tests` | 接口、业务、页面和架构测试 |

---

## 4. 如何继续深入了解

建议按顺序做这几件事：

1. 打开 Swagger，逐一请求 `/health`、`/api/program`、`/api/v1/test-results`、`/api/ui/master`；
2. 在 Streamlit 页面完成一次手动入站，然后观察 `mes.db.active_products` 和 `ProductFlow.db.product_overview`；
3. 用设备客户端上报一条 V1.3 数据，观察 `TestReport.db` 中 `report_index_<step>` 和 `SN_<step>_...`；
4. 做一次托盘解绑，确认历史新增“托盘解绑”、当前在制被删除；
5. 跑一次 `pytest`，从失败用例反推业务约束；
6. 最后再看 `domain/`，你会发现规则变得更好理解。

---

## 5. 文档维护约定

修改以下文件后，必须同步更新文档：

| 修改内容 | 需要更新 |
| --- | --- |
| 新增/删除 FastAPI 路由 | README、CODEBASE_GUIDE、本指导文档 |
| 修改数据库表含义 | README、对应 DatabaseConventions 文档 |
| 修改业务规则 | CODEBASE_GUIDE、本指导文档 |
| 修改页面流程 | README、本指导文档 |
| 新增核心函数 | 本指导文档函数索引 |

当前代码规模快照：87 个 Python 模块、610 个函数/方法、39 个类，模块/函数/类 docstring 缺失数为 0。
