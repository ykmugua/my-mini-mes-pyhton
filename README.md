```
旁路式小型 MES
```

设备乙方内部使用的轻量工具：汇总整条产线的测试数据、向测试设备下发程序、用工序锁控制放行、提供开放性变量给机台之间交换数据。

**不对接甲方 MES**，不处理工单、BOM、物料、排产；只做设备乙方现场调试和监控需要的那部分能力。

---

## 1. 功能一览

| 模块         | 能力                                                                                                                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 程序注册     | 程序新增 / 当前运行程序 / 历史程序（勾选程序查看历史版本，可删除程序或版本）                                      |
| 工序注册     | 全厂工序主数据：工序号/名称/启用/备注；新增、编辑、删除                                                                       |
| 设备注册     | 设备主数据：设备编号/名称/型号/启停/备注                                                                      |
| 载具注册     | 载具（托盘）主数据：载具码/名称/载荷数量/启停/备注；新增、直接修改、删除 |
| 组件注册     | 产品主数据、工序流程（成功/失败下站）、产品-工序-设备分配范围                                                                |
| 工艺配置     | 新增工艺（空白/从已有工艺深拷贝派生）、工艺列表、工艺详情（工序路线 + 工序资源：程序/可执行设备型号/转运载具型号） |
| 工位操作台   | 四个标签页：手动入站、入线状态、托盘解绑、产品解锁；入站按“产品型号 + 工序”校验允许的载具型号，入线状态按托盘一行聚合展示；托盘操作不写入产品查询记录 |
| 测试数据看板 | 设备页流式卡片 + 工序页按工序统计；折叠容器「监控设备管理」与「设置显示」；时间区间查询、每行卡片数、拖拽排序；1 秒局部刷新 |
| 开放性变量   | 最多三层组/子组/键层级（JSON 树视图）；变量定义与当前值查看、前缀筛选；新增变量；30 秒自动刷新；设备按完整路径读写接口          |
| 产品查询     | 两个标签页：产品流转查询、测试报告查询；报告按“产品型号 + 测试工序”直查 db_1.db 等工序库，结果可勾选查看报告总览与 details |
| 设备接口     | 程序拉取、程序状态上报、测试结果上报（V1.3 整单 + 旧单条）、放行查询、变量读写；请求头幂等 + 测试项幂等                        |

技术栈：**Streamlit 1.67 + FastAPI + SQLAlchemy Core + SQLite**；看板额外使用 `plotly`（柱状图）/ `streamlit-sortables`（拖拽排序），刷新用 Streamlit 原生 `@st.fragment`。双进程部署：**FastAPI 主要给机台使用**（上传/查询/程序拉取/放行/变量）；**Streamlit 作为内部工具可直接通过 Repository 读写数据库**（看板已直读 `station_summary`），也可经 HTTP 调 FastAPI。见 design_data/system_design_framework/manual.md。

```
                    ┌──────────────────────────────────┐
   浏览器 ─────────▶│ Streamlit :8501（8 个页面）      │
                    │  Repository 读写 / HTTP（可选）   │
                    └───┬──────────────────────┬───────┘
                        │ Repository 读写      │ HTTP/JSON（可选）
                        │（内部工具）          └────────────┐
   测试设备 ───────▶┌───▼───────────────────────────────▼─┐
   (HTTP/JSON)      │ FastAPI :8000（主要给机台）          │
                    │  api/routers + application/（4 用例） │
                    │  domain/（纯 Python）                 │
                    └───────────────┬──────────────────────┘
                                    │ Repository（唯一写 SQL）
                    ┌───────────────▼──────────────────────┐
                    │ SQLAlchemy Engine (engine.py)         │
                    │ SQLite（可切 PostgreSQL）             │
                    └───────────────┬──────────────────────┘
                                    ▼
                         data/mes.db + data/programs/
```

### 三条取舍（本次改造明确保持）

1. **FastAPI 主要给机台使用**：机台经 HTTP 访问；Streamlit 是内部工具，可直接通过 Repository 读写数据库（不写 SQL、不感知 SQLAlchemy），也可经 HTTP 调 FastAPI。
2. **薄应用层用例**：`report_test_result`、`unlock_workpiece`、`report_program_status`、`upload_test_result_v1`（MES V1.3 整单上传）以及工位操作台的入站/托盘解绑持有事务边界；其余 CRUD 路由直接调 repo，不配空壳用例。
3. **聚合不写库，事务由用例持有**：`domain/` 方法只做状态判定并返回领域结果（如 `UnlockOutcome`、`TrustVerdict`），日志与落盘由 application 用例在同一事务内完成。

---

## 2. 快速开始（Windows / PowerShell）

前置：Python ≥ 3.14、[uv](https://docs.astral.sh/uv/)。

```powershell
cd py-server

# 1) 安装依赖（使用 pyproject.toml 中配置的清华镜像）
uv sync

# 2) 初始化演示数据（--demo 会生成今天的测试数据，方便直接看看板）
uv run python -m py_server.seed --reset --demo

# 3) 启动设备接口服务（新终端）
.\scripts\run_api.ps1 -BindAddress 0.0.0.0 -Port 8000

# 4) 启动页面（另一个新终端）
.\scripts\run_ui.ps1 -BindAddress 0.0.0.0 -Port 8501
```

打开：

* 页面：[http://127.0.0.1:8501](http://127.0.0.1:8501)
* 接口文档（Swagger）：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* 健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

演示数据包含：5 条程序绑定（TEST-01/02/03、AOI-01、TEST-04）、3 条前道规则、4 个开放变量；TEST-03 故意上报了旧版本，用于展示**版本漂移告警**。

> 角色只在页面左侧切换「工程师（可编辑）/ 只读」，不做登录鉴权，符合“初期只区分可编辑和只读”的定位。
>
> 如果 PowerShell 提示禁止运行脚本，可先执行 `Set-ExecutionPolicy -Scope Process Bypass`，或直接手动运行脚本里的 uvicorn / streamlit 命令。

---

## 3. 目录结构

```
py-server/
├─ src/py_server/
│  ├─ config.py            # 环境变量配置（含 MES_UI_API_BASE）
│  ├─ engine.py            # SQLAlchemy Engine + Table 定义 + init_schema()
│  ├─ db.py                # 兼容层：时间工具 + 旧 init_db
│  ├─ domain/              # 纯领域层（不 import 任何框架）
│  │  ├─ trust/            # ProgramTrustPolicy / Binding / TrustVerdict
│  │  ├─ workpiece/        # Workpiece 聚合 / UnlockOutcome / LockReason
│  │  └─ interlock/        # InterlockPolicy 五步判定
│  ├─ application/         # 薄应用层：业务用例，持有事务边界
│  ├─ repositories/        # 唯一写 SQL 的层（含 station_repo / upload_repo 幂等）
│  ├─ api/                 # FastAPI 实例 / schemas(.py/.v1) / deps / routers/
│  ├─ services.py          # 兼容入口：输入校验 + 委托各层
│  ├─ ui/                  # client.py（唯一 HTTP 客户端）+ pages/ + 公共组件
│  ├─ seed.py              # 演示数据初始化
│  └─ streamlit_app.py     # Streamlit 入口（st.navigation）
├─ examples/device_client.py  # 设备侧参考客户端（续传/补传/幂等示例）
├─ scripts/                # Windows 启动脚本
├─ tests/                  # 7 条验收标准 + 接口边界 + UI 冒烟测试
└─ data/                   # 运行期数据（已 gitignore）
```

---

## 4. 配置项

全部通过环境变量覆盖，未设置时使用默认值。

| 环境变量                | 默认值                       | 说明                                                     |
| ----------------------- | ---------------------------- | -------------------------------------------------------- |
| `MES_DATA_DIR`        | `<项目>/data`              | 运行期数据目录                                           |
| `MES_DB_PATH`         | `$MES_DATA_DIR/mes.db`     | SQLite 文件路径                                          |
| `MES_DETAILS_DB_PATH` | `$MES_DATA_DIR/TestReport.db` | **生产明细独立库**：每产品一张明细表，物理隔离主库         |
| `MES_PROGRAM_DIR`     | `$MES_DATA_DIR/programs`   | 程序文件静态目录，挂在 `/programs`                     |
| `MES_TZ`              | `Asia/Shanghai`            | “今日”统计与页面展示使用的业务时区                     |
| `MES_API_PORT`        | `8000`                     | 接口服务端口（用于拼默认下载地址）                       |
| `MES_API_PUBLIC_BASE` | `http://<本机内网IP>:8000` | **设备可访问的接口地址**；部署到内网时建议显式设置 |
| `MES_UI_API_BASE`     | `MES_API_PUBLIC_BASE` | **Streamlit 访问 FastAPI 的地址**；双机部署时必须显式设置 |
| `MES_API_HOST`        | `0.0.0.0`                  | `python -m py_server.api` 时的监听地址                 |

数据库时间统一存 UTC ISO 字符串，页面展示时转换为业务时区。

---

## 5. 数据模型

| 表                      | 用途                                                                                         |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| `program_bindings`    | 设备-产品-程序绑定；含下载 URL、SHA256、最后拉取时间、设备上报版本/校验和、可生产状态        |
| `program_pull_logs`   | 设备拉取记录                                                                                 |
| `program_status_logs` | 设备程序状态上报记录（含不可信原因）                                                         |
| `workpieces`          | 工件当前状态：PASS/FAIL/待测、当前设备、锁定原因/时间、解锁人/原因/人工放行时间              |
| `test_results`        | 测试结果；`UNIQUE(workpiece, device_id, test_item)` 保证幂等；`trusted` 标记数据是否可信 |
| `station_summary`     | 产线看板汇总：设备状态/条码/总数/一次通过/复测通过/失败/持续时间；由 V1.3 上报维护，前端只读 |
| `station_fail_detail` | 看板失败明细：设备/失败项/条码/时间；由 V1.3 上报维护，前端只读                        |
| `test_reports`        | V1.3 整单主表（主库）：请求 ID 幂等 + JSON 顶层字段（含 isfinalreport）；每单一行      |
| `db_<工序号>.db` | 按工序测试库：`report_index` 总览 + 每产品 `SN_<条码>_<hash>` 明细表；明细表 id 从 1 开始；工序名不进入文件名 |
| `ProductFlow.db`      | 产品流转库：`product_overview` 总览（`barcode`/`componentcode`/`traycode`/状态等） + 每产品 `F_<条码>_<hash>` 流转表；状态 normal/lock/final |
| `TestReport.db`       | 兼容旧版测试报告库；新上报不再写入                                                     |
| `unlock_logs`         | 解锁留痕（工件、解锁人、原因、锁定原因、时间）                                               |
| `variables`           | 开放变量：名称、类型（int/str/bool/float）、当前值、最后写入设备、更新时间                    |
| `upstream_devices`    | 前道关键设备配置；产品留空表示对所有产品生效                                                 |
| `processes` / `process_routes` / `process_step_resources` | 工艺主表 / 工序路线 / 工序资源（程序、设备型号、载具型号） |
| `settings`            | 预留的键值配置表                                                                             |

---

## 6. 设备侧接口

所有接口返回 JSON。Swagger 文档见 `/docs`。

| 方法 | 路径                                     | 用途                                               |
| ---- | ---------------------------------------- | -------------------------------------------------- |
| GET  | `/api/program?device_id=&product=`     | 拉取程序元数据（同时写拉取记录）                   |
| POST | `/api/program/status`                  | 上报已加载版本与校验结果                           |
| POST | `/api/v1/test-results`                 | **V1.3 整单上报（机台主接口）**：请求头 SN/时间戳/请求 ID，幂等，更新看板汇总 |
| POST | `/api/test-result`                     | 旧单条上报接口（内部/测试兼容用，机台不再使用）    |
| GET  | `/api/ui/program/drift`                | 页面：版本漂移清单                                 |

| GET  | `/api/interlock?workpiece=&device_id=` | 查询工件能否在本设备操作（`device_id` 建议必传） |
| GET  | `/api/variable/{name}`                 | 读取开放变量                                       |
| POST | `/api/variable/{name}`                 | 写入开放变量                                       |
| GET  | `/health`                              | 健康检查                                           |
| GET  | `/programs/{filename}`                 | 程序文件下载（静态目录）                           |

### 6.1 拉取程序

```http
GET /api/program?device_id=TEST-01&product=P-1001
```

```json
{
  "device_id": "TEST-01",
  "product": "P-1001",
  "program_version": "v1.2.0",
  "download_url": "http://192.168.1.50:8000/programs/fw_TEST-01_P-1001_v1.2.0.bin",
  "sha256": "0430e7...",
  "last_pull_at": "2026-11-12T00:41:33+00:00",
  "server_time": "2026-11-12T00:41:33+00:00"
}
```

设备只绑定一个产品时 `product` 可省略；绑定多个产品时必须指定，否则返回 400。

### 6.2 上报程序状态

```http
POST /api/program/status
Content-Type: application/json

{"device_id": "TEST-01", "product": "P-1001", "program_version": "v1.2.0",
 "sha256": "0430e7...", "sha256_ok": true}
```

返回：

```json
{"trusted": true, "can_produce": true, "reason": "",
 "binding_version": "v1.2.0", "binding_sha256": "0430e7...", ...}
```

版本或校验和与绑定不一致、设备自检失败时 `trusted=false`，该设备后续上报的测试结果会被标记为**不可信**。只上报校验和但缺少版本、或自检失败时，也会进入页面顶部的漂移告警（提示上报信息不完整 / 自检失败）。

### 6.3 上报测试结果（MES V1.3 整单，机台主接口）

```http
POST /api/v1/test-results
Content-Type: application/json; charset=UTF-8
x-device-sn: <barcode>
x-timestamp: <毫秒时间戳，秒级取整，13 位>
x-request-id: <32 位 UUID，重试时保持不变>
```

请求体（所有 string 字段禁止 null，空值用 `/` 占位；服务端按字符串原样接收）：

```json
{
  "station": "39C0-L2-1F-DIP16-FCT01",
  "componentcode": "L120201091",
  "traycode": "T02001",
  "barcode": "71202011752609010004567V8083",
  "programname": "TEST-DUT-001",
  "programversion": "V0.0.2",
  "testexecutetime": "2025/4/22 13:55:35.123",
  "testlongtime": "00:00:06.300",
  "result": "FAIL",
  "details": [
    {"TestItem": "测试温度", "TestStep": "SOC_HW_ID1", "StandardValue": "1.10",
     "UpperValue": "1.20", "LowerValue": "0.90", "MeasureValue": "1.12",
     "TestResult": "true", "TestBeginTime": "13:55:35.123", "TestEndTime": "13:55:37.123"}
  ]
}
```

* 明细下限字段名是 **`LowerValue`**（以 `design_data/MesFormat/mesUploadTestDataFormat.json` 为准，协议文档里的 `littleValue` 是旧称）；
* `x-device-sn` 必须等于 `barcode`，否则业务码 `40003`；三个请求头缺一返回 `40001`；
* 响应统一为四字段信封：`{"success": true, "message": "success", "code": 0, "result": {...}}`；失败时 `result=null`，`code` 为 `40001/40003/409/50000`；
* `x-request-id` 是幂等键：网络超时/5xx/50000/50300 重试时复用同一值，服务端直接返回上次结果；`409` 视为成功，不为成功重试；
* 上报成功会自动维护 `station_summary` / `station_fail_detail`，测试数据看板 1 秒内显示真实数据；同一条码第二次上报识别为复测；
* 整单中每条明细作为一条内部测试结果入库，沿用原有程序可信性判定（不可信仍锁定工件）。

响应示例：

```json
{"success": true, "message": "success", "code": 0,
 "result": {"workpiece": "71202011752609010004567V8083", "station": "39C0-L2-1F-DIP16-FCT01",
            "result": "FAIL", "retest": false, "request_id": "a1b2c3d4e5f67890abcdef1234567890"}}
```

### 6.3b 上报测试结果（旧单条接口，内部/测试兼容）


```http
POST /api/test-result
Content-Type: application/json

{"workpiece": "WP-0001", "device_id": "TEST-01", "test_item": "上电电流",
 "result": "PASS", "measured_value": "1.02A", "program_version": "v1.2.0",
 "program_sha256": "0430e7...", "tested_at": "2026-11-12T08:30:00+08:00"}
```

* `workpiece` 也兼容 `workpiece_code` / `workpiece_id`；`tested_at` 兼容 `timestamp` / `ts`；
* 同一 `(工件码, 设备, 测试项)` 重复上报只记一次，重复请求返回 `"duplicate": true`，不会重复计数；
* 如果重复上报的判定结果与已记录结果**不一致**（例如先 PASS 后又报 FAIL），返回 `409` 并说明冲突，不会静默改数据；现场复测请使用新的测试项名称；
* 结果不可信时自动锁定工件；FAIL 时自动锁定并记录原因；
* 返回体中带 `workpiece_status`（工件最新状态、锁定原因等）。

### 6.4 放行查询

```http
GET /api/interlock?workpiece=WP-0001&device_id=TEST-02
```

```json
{"allowed": false,
 "reason": "前道关键设备无 PASS 记录：TEST-01",
 "upstream_required": ["TEST-01"], "upstream_missing": ["TEST-01"],
 "status": "PENDING", "locked": false, "device_trusted": true}
```

判定顺序：设备程序可信 → 工件未锁定 → 工件非 FAIL → 人工放行 → 前道关键设备均有可信 PASS。

`device_id` 建议必传；省略时按工件最近一次所在设备判定（便于人工排查 FAIL 工件），若工件还没有任何设备记录则返回 `"allowed": false` 并提示缺少 `device_id`。

### 6.5 开放变量

```http
GET /api/variable/line_mode
→ {"name": "line_mode", "type": "str", "value": "AUTO", "last_device": null, ...}

POST /api/variable/line_mode
{"value": "MANUAL", "device_id": "TEST-02"}
→ {"name": "line_mode", "value": "MANUAL", "last_device": "TEST-02", ...}
```

变量必须先通过页面新增（定义类型和初始值），设备侧只做读写；类型不匹配返回 400，变量不存在返回 404。变量名会出现在 URL 路径中，因此只允许英文字母、数字、下划线、点、短横线（以字母或下划线开头，长度 ≤ 64），避免出现设备无法寻址的名字（如 `a/b`）。

---

## 7. 业务规则说明

### 程序可信性

设备可信 = 已配置绑定 **且** 设备上报的版本与绑定版本一致 **且** 上报的 SHA256 与绑定一致，且设备没有上报过自检失败（`program_ok ≠ 0`）。版本/校验和优先取测试结果自带的字段，其次取设备最近一次 `/api/program/status` 上报值；两者都没有则视为不可信。推荐设备启动后先调用 `/api/program/status`，这样页面也能同步显示“可生产状态”。不满足可信条件时：

* 测试结果写入 `test_results` 但 `trusted=0`，附带不可信原因；
* 工件被锁定，禁止放行；
* 看板将其排除出合格率统计，仅单独提示数量；FAIL 分布保留全部 FAIL（含不可信数据）便于排查；

### 工序锁 / 解锁

1. 工件进入设备时，设备调用 `/api/interlock` 得到是否允许及原因；
2. FAIL 工件、被锁工件、程序不可信设备一律拒绝；
3. 人工解锁必须填写解锁原因并勾选确认，`unlock_logs` 永久留痕；
4. 解锁后工件状态回到“待测”，并记录人工放行时间，后续设备查询返回允许（`reason=人工解锁放行`）；若后续在新的测试项或新的设备上再次 FAIL，会重新锁定；同一测试项复测需使用新的测试项名称（受幂等键限制）。人工放行会在后续设备持续生效，请谨慎操作并确保解锁原因可追溯；
5. “前道关键设备”来自 `upstream_devices` 表，可在“工序锁”页面直接编辑，**不写死在代码里**。

### 系统边界

* 不对接甲方 MES；
* 不做 WMS/APS/SPC/TPM、不做工单/BOM/物料/排产；
* 不做戴手套操作工界面；
* 不做完整权限/登录体系，仅页面角色切换；
* 测试结果幂等键是 `(工件码, 设备, 测试项)`，同一设备同一测试项不会二次记数；若现场需要同工序多次复测，应把复测作为新的测试项（或在后续版本扩展幂等键）。

---

## 8. 页面说明

| 页面            | 说明                                                                                                                                                                                                            |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 📦 程序注册     | 顶部漂移告警；绑定关系可编辑表格（新增/修改/删除行后保存）；上传程序文件自动算 SHA256；拉取记录、状态上报记录；接口调用示例                                                                                     |
| 📊 测试数据看板 | 「设备页」卡片监控 + 「工序页」按工序统计；设备卡片有统计/失败详计/设备控制页签；两个同级折叠容器：监控设备管理、设置显示（顺序/每行卡片数/统计时间区间）；两页均 1 秒局部刷新且共用查询生效区间 |
| 🔎 产品查询     | 产品流转查询显示 ProductFlow 总览（托盘取最后测试上报）与追溯解绑；测试报告查询按产品型号 + 测试工序直查 db_1.db 等工序库，列表可勾选并展示报告总览/details                                             |
| 🛠️ 工位操作台   | 四个标签页：手动入站、入线状态、托盘解绑、产品解锁；产品型号后选择工序，按两者卡载具型号；同一流转托盘的多条码在一行展示；托盘解锁不进入产品查询 |
| 🔧 开放性变量   | 前缀筛选；变量表；新增变量表单；30 秒自动刷新；接口示例                                                                                                                                                         |

页面可直接通过 Repository 读写数据库（不写 SQL、不感知 SQLAlchemy），也可经 `ui/client.py` 以 HTTP 访问 FastAPI；两条路径复用同一套 domain/application/repositories，因此页面里的“放行状态自检”、看板统计与设备接口结果完全一致。

---

## 9. 验收标准对照

以下场景均可通过自动化测试复现（`pytest tests/test_acceptance.py`）：

| # | 验收标准                                                | 实现 / 验证                                                                                                                        |
| - | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1 | 修改绑定后 `GET /api/program` 返回新版本、URL、SHA256 | `test_acceptance_1_program_pull_returns_updated_binding`                                                                         |
| 2 | 设备上报版本不一致时程序页面顶部告警                    | `program_drift()` + 页面顶部 `st.error`；`test_acceptance_2_version_drift_alert`、`test_main_app_renders_with_drift_alert` |
| 3 | 前道无 PASS 拒绝；FAIL 工件后续设备拒绝                 | `test_acceptance_3_interlock_rules`                                                                                              |
| 4 | 解锁必须原因 + 勾选确认，解锁后放行恢复、记录可查       | `test_acceptance_4_unlock_requires_reason_and_confirm`、`test_interlock_unlock_from_page`                                      |
| 5 | 看板 1 秒内更新，校验和不匹配不计入合格率               | `st.fragment(run_every=1000)`；`test_acceptance_5_dashboard_excludes_untrusted`                                                  |
| 6 | 新增变量后设备读到初始值，设备写入后页面显示新值        | `test_acceptance_6_variables_roundtrip`、`test_variables_add_from_page`                                                        |
| 7 | 重复上报幂等                                            | `UNIQUE(workpiece, device_id, test_item)`；`test_acceptance_7_duplicate_report_is_idempotent`                                  |
| 8 | V1.3 整单上报：请求头校验、幂等、看板汇总、复测          | `POST /api/v1/test-results`；`test_upload_v1.py`（6 个用例）                                                                   |

手动验证示例（服务启动后）：

```powershell
# 验收 1：改绑定（也可在页面改）后拉取
curl.exe "http://127.0.0.1:8000/api/program?device_id=TEST-01&product=P-1001"

# 验收 3：前道无 PASS 被拒绝
curl.exe "http://127.0.0.1:8000/api/interlock?workpiece=DEMO-WP&device_id=TEST-02"

# 验收 6：新增变量后设备读取
curl.exe "http://127.0.0.1:8000/api/variable/line_mode"
```

也可以直接跑参考客户端：

```powershell
uv run python examples/device_client.py --device TEST-01 --product P-1001 demo
```

---

## 10. 测试

```powershell
uv run pytest
```

当前结果：**133 passed**，包括：

* 7 条验收标准 + V1.3 上传 6 条自动化用例；
* 接口边界（404/400/422、多产品歧义、静态文件下载、类型校验、变量前缀筛选）；
* 业务规则（漂移、可信性、前道规则、失败与解锁）；
* 4 个 Streamlit 页面的 AppTest 冒烟，以及页面内解锁/新增变量/只读角色交互。

---

## 11. 部署建议（内网）

1. **接口服务**绑定 `0.0.0.0:8000`，**页面**绑定 `0.0.0.0:8501`，设备与办公网通过 `http://<服务器内网IP>:端口` 访问；
2. 设置 `MES_API_PUBLIC_BASE=http://<服务器内网IP>:8000`，保证上传程序文件后生成的下载地址设备可达；
3. 放行 Windows 防火墙对应端口；
4. SQLite 使用 WAL 模式；FastAPI 主要给机台使用，Streamlit 作为内部工具可直接经 Repository 读写数据库（不写 SQL），也可经 HTTP 调 FastAPI。建议单机部署 + 定期备份 `data/`（停服复制，或 `sqlite3 mes.db "VACUUM INTO 'backup.db'"`）；
5. 程序文件默认存本地静态目录；若改用对象存储，只需把 `download_url` 指向对象存储地址并填写 SHA256，数据库结构不变；
6. 当前没有接口鉴权，仅适合内网使用；如需收紧，可在反向代理层加 IP 白名单或 Basic Auth。

---

## 12. 常见问题

**设备拿不到程序，返回 404？** 先确认该设备+产品已在“程序注册”页面保存绑定；若设备绑定了多个产品，请求必须带 `product`。

**设备用 `/api/v1/test-results` 上报后看板没更新？** 确认请求头三项齐全、`x-device-sn` 与 `barcode` 一致、响应 `code=0`；看板 1 秒局部刷新，只需等一个刷新周期。

**设备上报了测试数据，看板提示“不可信”？** 检查该设备是否调用了 `/api/program/status` 上报当前版本与 SHA256，以及上报值是否与绑定一致；版本漂移告警也会同时出现。

**解锁后为什么还拦截？** 解锁只解除工件锁；若设备本身程序不可信，仍会按规则 3 拒绝放行。先让设备重新加载并上报正确的程序版本。

**修改绑定后需要重启服务吗？** 不需要。页面通过 Repository 保存即写库，设备下次 `GET /api/program` 就拿到新值；Streamlit 和接口服务各自持有短连接，读到的是同一份数据。
