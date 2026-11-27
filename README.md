# 旁路式小型 MES

设备乙方内部使用的轻量 MES 工具，聚焦产线测试数据、程序下发、工序联锁、产品流转与开放性变量。不对接甲方 MES，不处理工单、BOM、物料、排产或完整登录权限。

---

## 1. 当前功能

| 模块 | 说明 |
| --- | --- |
| 测试数据看板 | 按设备/工序查看今日或指定时间区间的测试数据、一次通过率、复测、失败明细；1 秒局部刷新 |
| 工位操作台 | 手动入站、当前已绑定托盘列表、托盘扫码解绑、产品解锁；按产品型号 + 工序校验载具型号 |
| 产品查询 | 产品流转查询与测试报告查询；报告库统一为 `TestReport.db`，按 `step_no` 保留工序来源 |
| 程序注册 | 程序新增、当前运行程序、历史版本、程序状态与漂移 |
| 注册配置 | 一个页面内用标签页维护程序、工序、设备、载具、组件；工序/设备/载具/组件的新增表单支持从模板新建 |
| 工艺配置 | 独立页面维护工艺号、工艺路线和工序资源；新增工艺支持从原有模板新建 |
| 开放性变量 | 三层变量树、变量定义、前缀筛选、设备读写、读写日志 |
| 设备接口 | 程序拉取/下载、程序状态上报、V1.3 整单测试上报、放行查询、变量读写、设备开启状态查询 |

技术栈：Python 3.14、FastAPI、Streamlit、SQLAlchemy Core、SQLite、plotly。部署为双进程：FastAPI 提供设备接口和 UI 接口，Streamlit 提供内部操作页面；Streamlit 通过 HTTP 客户端访问 FastAPI，不直接写数据库。

如果你是第一次了解项目，建议先读 [项目了解路线图](docs/PROJECT_ONBOARDING.md)，再读 [代码详解](docs/CODEBASE_GUIDE.md)。
设备端对接接口见 [设备端 API 文档](docs/设备端API文档.md)。

---

## 2. 快速开始

前置：Python ≥ 3.14、uv。

```powershell
cd E:\personal\xqk\my-mini-mes-pyhton

# 安装依赖
uv sync

# 清空并重建演示数据
.\.venv\Scripts\python.exe -m py_server.seed --reset --demo

# 启动接口服务
.\scripts\run_api.ps1 -BindAddress 0.0.0.0 -Port 8000

# 启动页面
.\scripts\run_ui.ps1 -BindAddress 0.0.0.0 -Port 8501

# 或一键后台启动接口服务与页面
.\scripts\start_all.ps1

# 一键停止接口服务与页面
.\scripts\stop_all.ps1
```

访问：

- 页面：<http://127.0.0.1:8501>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

启动脚本会设置 `MES_UI_API_BASE=http://127.0.0.1:8000`，避免 Streamlit 访问本机内网 IP 时经过代理或网关导致 502/慢加载。

---

## 3. 目录结构

```text
my-mini-mes-pyhton/
├─ src/py_server/
│  ├─ api/                  # FastAPI app、schemas、routers（device/ui/common 分组）
│  ├─ application/          # 多步业务用例：上报、解锁、入站、程序状态
│  ├─ domain/               # 纯业务规则：可信性、联锁、工件状态
│  ├─ repositories/         # SQL 与数据库访问；active_product_repo 维护当前在制表
│  ├─ ui/                   # Streamlit 页面、HTTP client、公共组件
│  ├─ config.py             # 配置与路径
│  ├─ engine.py             # SQLAlchemy Engine 与表定义
│  ├─ db.py                 # 时间工具与初始化兼容层
│  ├─ services.py           # 兼容业务入口与输入校验
│  ├─ seed.py               # 演示数据初始化
│  └─ streamlit_app.py      # Streamlit 页面入口
├─ data/                    # 运行期数据，已 gitignore
├─ docs/                    # 文档、协议与设计资料
├─ examples/                # 设备侧参考客户端
├─ scripts/                 # 启动脚本
└─ tests/                   # 接口、业务规则、架构与 AppTest 测试
```

---

## 4. 架构与数据流

```text
设备 ──HTTP/JSON──▶ FastAPI :8000
                     │ routers/device：设备接口
                     │ routers/ui：界面接口
                     │ routers/common：双方共用接口
                     │ services/application：校验与用例编排
                     │ domain：纯业务规则
                     └ repositories：SQL、SQLite 访问

浏览器 ───────────▶ Streamlit :8501
                     └ ui/client.py ──HTTP──▶ FastAPI
```

约束：

- `domain/` 不依赖 FastAPI、Streamlit、SQLAlchemy 或 sqlite3，只保留程序可信、联锁放行、工件状态机三块纯规则；新增流程卡控默认放 services/application。
- `repositories/` 是唯一允许写 SQL 的目录。
- `ui/` 只通过 `client.py` 访问接口，不直接连接数据库。
- `mes.db` 维护主数据、程序、工件、变量与当前在制产品；`ProductFlow.db` 维护当前总览和每产品流转历史；`TestReport.db` 是唯一测试报告库。

---

## 5. 数据与数据库

运行期数据在 `data/`：

| 文件 | 用途 |
| --- | --- |
| `mes.db` | 主库：主数据、程序绑定、工件状态、变量、看板汇总与 `active_products` 当前在制表 |
| `ProductFlow.db` | 产品流转：`product_overview` 与每产品流转表 `F_<条码>_<hash>` |
| `TestReport.db` | **唯一测试报告库**：按工序分表 `report_index_<step_no>` 与每工序明细表 `SN_<step>_<条码>_<hash>` |
| `programs/` | 程序文件静态目录 |

测试报告统一写入 `TestReport.db`，库内按工序分表；不再使用旧的 `db_1.db`、`db_2.db` 等按工序分库。SQLite 使用 WAL；清理或迁移数据时需先停止 8000/8501 服务。

重建演示数据：

```powershell
.\.venv\Scripts\python.exe -m py_server.seed --reset --demo
```

该命令会清空并重建主库、产品流转库和测试报告库，生成一批规则一致的演示数据：主数据、程序绑定/状态、前道规则、变量、测试报告、测试明细、工件状态和产品流转记录。

---

## 6. 主要接口

Swagger 文档见 `/docs`。常用接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/api/program` | 拉取程序元数据与下载地址 |
| GET | `/programs/{filename}` | 下载程序文件 |
| POST | `/api/program/status` | 上报程序版本/SHA256/自检结果 |
| POST | `/api/v1/test-results` | V1.3 整单测试上报（机台主接口） |
| GET | `/api/ui/interlock-check` | 工件放行判定 |
| GET/POST | `/api/variable/{name}` | 读取/写入开放变量 |
| GET | `/api/device/enable` | 查询设备是否开启 |

设备端最小 API 集：健康检查、程序元数据、程序文件下载、程序状态上报、放行判定、V1.3 报告上传、变量读写、设备开启状态查询。UI 接口不提供给设备端使用。
| GET | `/api/ui/master` | 页面主数据快照 |
| GET | `/api/ui/product/workpieces` | 产品流转查询 |
| GET | `/api/ui/product/report-query` | 测试报告查询（单库 + step_no 筛选） |
| GET | `/api/ui/product/report-details` | 报告明细 |
| GET | `/api/ui/workbench/recipe` | 工位操作台工艺与载具规则 |
| POST | `/api/ui/workbench/inbound` | 手动入站 |
| POST | `/api/ui/workbench/tray-unbind` | 托盘解绑 |

V1.3 上报不再使用自定义请求头；业务幂等键为 `barcode + testexecutetime + station + testlongtime`，重试时保持这几个字段不变。

上报成功后系统会：写入 `test_reports` 与 SN 明细表、维护 `report_index.step_no`、更新工件与 ProductFlow 状态、刷新看板汇总。

---

## 7. 关键业务规则

- 设备可信：有绑定、上报版本一致、SHA256 一致、自检未失败。
- 不可信测试结果会写入，但不计入可信合格率，并锁定工件。
- FAIL 会锁定工件；人工解锁必须填写原因并勾选确认，且写入 `unlock_logs`。
- 放行顺序：设备程序可信 → 工件未锁定 → 非 FAIL → 人工放行 → 前道设备均有可信 PASS。
- 产品托盘码：产品查询显示最后一次测试上报托盘码；当前绑定托盘在工位操作台“当前已绑定托盘”和托盘扫码解绑页展示。
- 托盘解绑表示产品下线：写入一条 `托盘解绑` 流转历史，删除 `active_products` 当前在制记录，并兼容清理 `ProductFlow.product_overview`；测试数据和测试报告不会删除。
- 工位入站按产品型号 + 工序校验允许载具型号。
- 当前托盘占用以 `mes.db.active_products` 为准，产品流转历史以 `ProductFlow.db` 为准。

---

## 8. 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MES_DATA_DIR` | `<项目>/data` | 数据目录 |
| `MES_DB_PATH` | `<data>/mes.db` | 主库 |
| `MES_DETAILS_DB_PATH` | `<data>/TestReport.db` | 测试报告库 |
| `MES_PRODUCT_FLOW_DB_PATH` | `<data>/ProductFlow.db` | 产品流转库 |
| `MES_PROGRAM_DIR` | `<data>/programs` | 程序目录 |
| `MES_API_PORT` | `8000` | 接口端口 |
| `MES_API_PUBLIC_BASE` | `http://<本机内网IP>:8000` | 设备可访问地址，用于程序下载 URL |
| `MES_UI_API_BASE` | `http://127.0.0.1:8000` | Streamlit 访问 FastAPI 地址 |
| `MES_TZ` | `Asia/Shanghai` | 业务时区 |

---

## 9. 测试与验收

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前测试覆盖：接口边界、V1.3 上报、可信性/联锁/解锁、产品查询、工位操作台、架构约束与 Streamlit AppTest 冒烟。最近一次全量结果：`109 passed`。

---

## 10. 常见问题

**页面提示接口超时或显示旧数据？** 检查 `MES_UI_API_BASE` 是否为 `http://127.0.0.1:8000`，并确认 8000 服务正常。默认配置已使用回环地址。

**测试报告查询不到工序数据？** 单库后工序来源由 `report_index_<step_no>` 分表保存，确认对应工序表存在。

**数据库清理后页面为空？** 运行 `python -m py_server.seed --reset --demo` 重建演示数据，并重启 8000/8501。

**修改代码后页面没变化？** Streamlit 文件保存后通常会热重载，但新增函数或 FastAPI 路由后需要重启对应进程。

**旧 `app_pages/` 还能用吗？** 已删除。当前唯一页面入口是 `src/py_server/streamlit_app.py`。
