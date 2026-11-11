# 旁路式小型 MES

设备乙方内部使用的轻量工具：汇总整条产线的测试数据、向测试设备下发程序、用工序锁控制放行、提供开放性变量给机台之间交换数据。

**不对接甲方 MES**，不处理工单、BOM、物料、排产；只做设备乙方现场调试和监控需要的那部分能力。

---

## 1. 功能一览

| 模块 | 能力 |
| --- | --- |
| 程序下发 | 设备-产品-程序版本绑定；可编辑表格新增/修改/删除；设备拉取记录；版本漂移告警；上传程序文件自动计算 SHA256 |
| 工序锁 | 前道关键设备无 PASS 拒绝启动；FAIL 工件后续拦截；程序版本/校验和不一致时结果不可信且禁止放行；人工解锁留痕；前道设备列表可配置 |
| 测试数据看板 | 今日总数/PASS/FAIL/合格率；按设备合格率柱状图；FAIL 按测试项/设备分布；设备筛选；10 秒自动刷新；不可信数据排除出合格率 |
| 开放性变量 | 变量定义与当前值查看、前缀筛选；新增变量；30 秒自动刷新；设备读写接口 |
| 设备接口 | 程序拉取、程序状态上报、测试结果上报、放行查询、变量读写；测试结果幂等 |

技术栈：**Streamlit 1.67 + FastAPI + SQLite**。页面与接口是两个独立进程，共用同一个 SQLite 数据库。

```
                    ┌────────────────────────────┐
   浏览器 ─────────▶│ Streamlit :8501            │
                    │  4 个页面（st.navigation）  │
                    └─────────────┬──────────────┘
                                  │ SQLite (WAL)
                    ┌─────────────▼──────────────┐
   测试设备 ───────▶│ FastAPI :8000              │
   (HTTP/JSON)      │  设备侧 /api/* + /programs │
                    └─────────────┬──────────────┘
                                  │
                       data/mes.db + data/programs/
```

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

* 页面：<http://127.0.0.1:8501>
* 接口文档（Swagger）：<http://127.0.0.1:8000/docs>
* 健康检查：<http://127.0.0.1:8000/health>

演示数据包含：5 条程序绑定（TEST-01/02/03、AOI-01、TEST-04）、3 条前道规则、4 个开放变量；TEST-03 故意上报了旧版本，用于展示**版本漂移告警**。

> 角色只在页面左侧切换「工程师（可编辑）/ 只读」，不做登录鉴权，符合“初期只区分可编辑和只读”的定位。
>
> 如果 PowerShell 提示禁止运行脚本，可先执行 `Set-ExecutionPolicy -Scope Process Bypass`，或直接手动运行脚本里的 uvicorn / streamlit 命令。

---

## 3. 目录结构

```
py-server/
├─ src/py_server/
│  ├─ config.py            # 环境变量配置（数据目录、时区、对外地址）
│  ├─ db.py                # SQLite 连接、建表、时间工具
│  ├─ services.py          # 业务规则：程序可信性、工序锁、幂等上报、看板统计、变量
│  ├─ api.py               # FastAPI 设备侧接口
│  ├─ seed.py              # 演示数据初始化
│  ├─ streamlit_app.py     # Streamlit 入口（st.navigation）
│  └─ ui/                  # 四个页面 + 公共侧边栏/权限
├─ examples/device_client.py  # 设备侧参考客户端（续传/补传/幂等示例）
├─ scripts/                # Windows 启动脚本
├─ tests/                  # 7 条验收标准 + 接口边界 + UI 冒烟测试
└─ data/                   # 运行期数据（已 gitignore）
```

---

## 4. 配置项

全部通过环境变量覆盖，未设置时使用默认值。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MES_DATA_DIR` | `<项目>/data` | 运行期数据目录 |
| `MES_DB_PATH` | `$MES_DATA_DIR/mes.db` | SQLite 文件路径 |
| `MES_PROGRAM_DIR` | `$MES_DATA_DIR/programs` | 程序文件静态目录，挂在 `/programs` |
| `MES_TZ` | `Asia/Shanghai` | “今日”统计与页面展示使用的业务时区 |
| `MES_API_PORT` | `8000` | 接口服务端口（用于拼默认下载地址） |
| `MES_API_PUBLIC_BASE` | `http://<本机内网IP>:8000` | **设备可访问的接口地址**；部署到内网时建议显式设置 |
| `MES_API_HOST` | `0.0.0.0` | `python -m py_server.api` 时的监听地址 |
| `MES_MAX_FUTURE_SKEW_SECONDS` | `300` | 设备 `tested_at` 允许超前服务器时间的秒数，超出会钳制到服务器当前时间 |
| `MES_STALE_TOLERANCE_SECONDS` | `300` | 判断历史补传时的时钟偏差容差，避免轻微偏慢的时钟把新 FAIL 当旧数据处理 |

数据库时间统一存 UTC ISO 字符串，页面展示时转换为业务时区。

---

## 5. 数据模型

| 表 | 用途 |
| --- | --- |
| `program_bindings` | 设备-产品-程序绑定；含下载 URL、SHA256、最后拉取时间、设备上报版本/校验和、可生产状态 |
| `program_pull_logs` | 设备拉取记录 |
| `program_status_logs` | 设备程序状态上报记录（含不可信原因） |
| `workpieces` | 工件当前状态：PASS/FAIL/待测、当前设备、锁定原因/时间、解锁人/原因/人工放行时间 |
| `test_results` | 测试结果；`UNIQUE(workpiece, device_id, test_item)` 保证幂等；`trusted` 标记数据是否可信 |
| `unlock_logs` | 解锁留痕（工件、解锁人、原因、锁定原因、时间） |
| `variables` | 开放变量：名称、类型（int/str/bool）、当前值、最后写入设备、更新时间 |
| `upstream_devices` | 前道关键设备配置；产品留空表示对所有产品生效 |
| `settings` | 预留的键值配置表 |

---

## 6. 设备侧接口

所有接口返回 JSON。Swagger 文档见 `/docs`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/program?device_id=&product=` | 拉取程序元数据（同时写拉取记录） |
| POST | `/api/program/status` | 上报已加载版本与校验结果 |
| POST | `/api/test-result` | 上报测试结果（幂等） |
| GET | `/api/interlock?workpiece=&device_id=` | 查询工件能否在本设备操作（`device_id` 建议必传） |
| GET | `/api/variable/{name}` | 读取开放变量 |
| POST | `/api/variable/{name}` | 写入开放变量 |
| GET | `/health` | 健康检查 |
| GET | `/programs/{filename}` | 程序文件下载（静态目录） |

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

### 6.3 上报测试结果（幂等）

```http
POST /api/test-result
Content-Type: application/json

{"workpiece": "WP-0001", "device_id": "TEST-01", "test_item": "上电电流",
 "result": "PASS", "measured_value": "1.02A", "program_version": "v1.2.0",
 "program_sha256": "0430e7...", "tested_at": "2026-11-12T08:30:00+08:00"}
```

* `workpiece` 也兼容 `workpiece_code` / `workpiece_id`；`tested_at` 兼容 `timestamp` / `ts`；
* 工件第一次上报时会确定产品型号，之后该工件即为该产品；后续上报的 `product` 若与工件产品不一致，直接返回 `400`，避免跨产品串数据；
* 同一 `(工件码, 设备, 测试项)` 重复上报只记一次，重复请求返回 `"duplicate": true`，不会重复计数；
* 如果重复上报的判定结果与已记录结果**不一致**（例如先 PASS 后又报 FAIL），返回 `409` 并说明冲突，不会静默改数据；现场复测请使用新的测试项名称；
* 离线补传更早的历史结果时（`tested_at` 早于该工件已有的最新测试时间），只入库保留记录，**不改变工件状态、不锁定**，返回 `"stale": true`；工件状态按测试时间最新的一条结果推进；
* 设备时间只作为参考：`tested_at` 超前服务器时间超过 `MES_MAX_FUTURE_SKEW_SECONDS`（默认 300 秒）会被钳制到服务器时间并返回 `"tested_at_adjusted": true`，防止未来时间让后续真实 FAIL 被误判为旧数据；历史补传比较保留 `MES_STALE_TOLERANCE_SECONDS`（默认 300 秒）容差。设备端建议开启 NTP 对时；
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

产品隔离：工件已记录产品时，前道 PASS 必须是**同产品**的记录；请求的 `product` 与工件产品不一致时直接拒绝并说明原因。同一设备绑定多个产品时，各产品的测试记录互不满足前道条件。

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
5. “前道关键设备”来自 `upstream_devices` 表，可在“工序锁”页面直接编辑，**不写死在代码里**；
6. 工件状态按**测试时间最新**的一条结果推进；离线补传的旧结果只入库，不会把已经 PASS 的工件改回 FAIL 或重新锁定（看板“今日”同样按 `tested_at` 统计，口径一致）。

### 系统边界

* 不对接甲方 MES；
* 不做 WMS/APS/SPC/TPM、不做工单/BOM/物料/排产；
* 不做戴手套操作工界面；
* 不做完整权限/登录体系，仅页面角色切换；
* 测试结果幂等键是 `(工件码, 设备, 测试项)`，同一设备同一测试项不会二次记数；若现场需要同工序多次复测，应把复测作为新的测试项（或在后续版本扩展幂等键）。

---

## 8. 页面说明

| 页面 | 说明 |
| --- | --- |
| 📦 程序下发 | 顶部漂移告警；绑定关系可编辑表格（新增/修改/删除行后保存）；上传程序文件自动算 SHA256；拉取记录、状态上报记录；接口调用示例 |
| 🔒 工序锁 | 当前锁定工件列表；人工解锁表单（原因必填 + 勾选确认）；解锁留痕；前道关键设备配置；放行状态自检 |
| 📊 测试数据看板 | 今日总数/PASS/FAIL（按设备测试时间统计，含全部上报）/合格率（仅可信数据）；按设备合格率柱状图；FAIL 按测试项/设备分布（含不可信数据）；设备筛选在侧边栏；`st.fragment(run_every=10)` 自动刷新；不可信数据提示 |
| 🔧 开放性变量 | 前缀筛选；变量表；新增变量表单；30 秒自动刷新；接口示例 |

页面与接口共用 `services.py`，因此页面里的“放行状态自检”、看板统计与设备接口结果完全一致。

---

## 9. 验收标准对照

以下场景均可通过自动化测试复现（`pytest tests/test_acceptance.py`）：

| # | 验收标准 | 实现 / 验证 |
| --- | --- | --- |
| 1 | 修改绑定后 `GET /api/program` 返回新版本、URL、SHA256 | `test_acceptance_1_program_pull_returns_updated_binding` |
| 2 | 设备上报版本不一致时程序页面顶部告警 | `program_drift()` + 页面顶部 `st.error`；`test_acceptance_2_version_drift_alert`、`test_main_app_renders_with_drift_alert` |
| 3 | 前道无 PASS 拒绝；FAIL 工件后续设备拒绝 | `test_acceptance_3_interlock_rules` |
| 4 | 解锁必须原因 + 勾选确认，解锁后放行恢复、记录可查 | `test_acceptance_4_unlock_requires_reason_and_confirm`、`test_interlock_unlock_from_page` |
| 5 | 看板 10 秒内更新，校验和不匹配不计入合格率 | `st.fragment(run_every=10)`；`test_acceptance_5_dashboard_excludes_untrusted` |
| 6 | 新增变量后设备读到初始值，设备写入后页面显示新值 | `test_acceptance_6_variables_roundtrip`、`test_variables_add_from_page` |
| 7 | 重复上报幂等 | `UNIQUE(workpiece, device_id, test_item)`；`test_acceptance_7_duplicate_report_is_idempotent` |

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

当前结果：**44 passed**，包括：

* 7 条验收标准的自动化用例；
* 接口边界（404/400/422、多产品歧义、静态文件下载、类型校验、变量前缀筛选）；
* 业务规则（漂移、可信性、前道规则、失败与解锁）；
* 4 个 Streamlit 页面的 AppTest 冒烟，以及页面内解锁/新增变量/只读角色交互。

---

## 11. 部署建议（内网）

1. **接口服务**绑定 `0.0.0.0:8000`，**页面**绑定 `0.0.0.0:8501`，设备与办公网通过 `http://<服务器内网IP>:端口` 访问；
2. 设置 `MES_API_PUBLIC_BASE=http://<服务器内网IP>:8000`，保证上传程序文件后生成的下载地址设备可达；
3. 放行 Windows 防火墙对应端口；
4. SQLite 使用 WAL 模式，页面和接口可以同时读写；建议单机部署 + 定期备份 `data/`（停服复制，或 `sqlite3 mes.db "VACUUM INTO 'backup.db'"`）；
5. 程序文件默认存本地静态目录；若改用对象存储，只需把 `download_url` 指向对象存储地址并填写 SHA256，数据库结构不变；
6. 当前没有接口鉴权，仅适合内网使用；如需收紧，可在反向代理层加 IP 白名单或 Basic Auth。

---

## 12. 常见问题

**设备拿不到程序，返回 404？** 先确认该设备+产品已在“程序下发”页面保存绑定；若设备绑定了多个产品，请求必须带 `product`。

**设备上报了测试数据，看板提示“不可信”？** 检查该设备是否调用了 `/api/program/status` 上报当前版本与 SHA256，以及上报值是否与绑定一致；版本漂移告警也会同时出现。

**解锁后为什么还拦截？** 解锁只解除工件锁；若设备本身程序不可信，仍会按规则 3 拒绝放行。先让设备重新加载并上报正确的程序版本。

**修改绑定后需要重启服务吗？** 不需要。页面保存即写库，设备下次 `GET /api/program` 就拿到新值；Streamlit 和接口服务各自持有短连接，读到的是同一份数据。
