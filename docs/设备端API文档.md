# 设备端 API 文档

本文档只描述设备端需要调用的 FastAPI 接口。`/api/ui/*` 是 Streamlit 页面专用接口，不应由设备端调用。

服务默认地址：`http://<MES服务器IP>:8000`。Swagger：`/docs`。

---

## 1. 设备端接口总览

| 分类 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 连通性 | GET | `/health` | 检查 API 服务是否在线 |
| 程序下发 | GET | `/api/program` | 获取程序元数据和下载地址 |
| 程序下发 | GET | `/programs/{filename}` | 下载程序文件 |
| 程序状态 | POST | `/api/program/status` | 上报设备当前程序版本、SHA256、自检结果 |
| 测试上报 | POST | `/api/v1/test-results` | 上传 V1.3 整单测试报告 |
| 进站校验 | POST | `/api/workpiece/check-in` | 扫描产品后的只读进站资格校验 |
| 开放性变量 | GET | `/api/variable/{name}` | 读取开放变量 |
| 开放性变量 | POST | `/api/variable/{name}` | 写入开放变量 |
| 设备状态 | GET | `/api/device/enable` | 查询设备是否允许开启 |
| 设备状态 | POST | `/api/device/heartbeat` | 周期性上报设备在线心跳 |
| 设备状态 | POST | `/api/device/test-start` | 上报测试开始，让看板显示测试中 |

所有响应均为 JSON；除程序文件下载外，错误由 FastAPI 标准响应或业务信封返回。

---

## 2. 通用约定

- Content-Type：`application/json; charset=UTF-8`。
- 内网免认证，不携带 `Authorization`。
- 上传测试报告不再使用 `x-device-sn`、`x-timestamp`、`x-request-id` 三个自定义请求头。
- 设备号统一用 `device_id` 或 `station` 表达；它们不是工件条码 `barcode`。
- 空字符串统一传 `/`。服务端按字符串原样接收，不做数字、布尔或时间解析。

---

## 3. 连通性

### GET `/health`

检查 API 服务是否在线，同时返回当前主库路径。

响应示例：

```json
{
  "status": "ok",
  "time": "2026/11/27 09:00:00.000",
  "database": "E:\\personal\\xqk\\my-mini-mes-pyhton\\data\\mes.db"
}
```

---

## 4. 程序下发

### 4.1 GET `/api/program`

按设备号拉取程序元数据。若设备绑定多个产品，必须传 `product`。

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `device_id` | query | 是 | 设备号 |
| `product` | query | 否 | 产品型号；设备绑定多个产品时必填 |

响应示例：

```json
{
  "device_id": "TEST-01",
  "product": "P-1001",
  "program_version": "v1.2.0",
  "download_url": "http://192.168.1.50:8000/programs/TEST-01_v1.2.0.zip",
  "sha256": "64位SHA256",
  "last_pull_at": "2026/11/27 09:00:00.000",
  "server_time": "2026/11/27 09:00:01.000"
}
```

主要错误：

- `400`：参数为空，或设备绑定多个产品但未指定 `product`
- `404`：设备/产品没有程序绑定

### 4.2 GET `/programs/{filename}`

下载程序文件。`filename` 取 `/api/program` 返回的 `download_url` 文件名部分。

响应：二进制文件流，`Content-Disposition` 带原文件名。

主要错误：

- `404`：程序文件不存在

### 4.3 POST `/api/program/status`

设备下载/加载程序后上报当前程序状态。可信性判定依赖此接口；V1.3 测试报告本身没有 SHA256 字段。

请求体：

```json
{
  "device_id": "TEST-01",
  "product": "P-1001",
  "program_version": "v1.2.0",
  "sha256": "64位SHA256",
  "sha256_ok": true
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `device_id` | string | 是 | 设备号 |
| `product` | string | 否 | 产品型号 |
| `program_version` | string | 否 | 当前加载版本；兼容 `version` / `reported_version` |
| `sha256` | string | 否 | 当前程序 SHA256；兼容 `program_sha256` / `reported_sha256` |
| `sha256_ok` | bool | 否 | 自检结果；兼容 `checksum_ok` / `verified` |
| `reported_at` | datetime | 否 | 上报时间；兼容 `timestamp` / `loaded_at` |

响应示例：

```json
{
  "device_id": "TEST-01",
  "product": "P-1001",
  "trusted": true,
  "can_produce": true,
  "reason": "",
  "binding_version": "v1.2.0",
  "binding_sha256": "64位SHA256",
  "reported_version": "v1.2.0",
  "reported_sha256": "64位SHA256",
  "checked_at": "2026/11/27 09:00:02.000"
}
```

---

## 5. 测试报告上传

### POST `/api/v1/test-results`

上传 V1.3 整单测试报告。接口不再使用自定义请求头。

业务幂等键：

```text
barcode + testexecutetime + station + testlongtime
```

客户端超时重试时必须复用同一组字段值；服务端用该组合去重。

字段顺序与 `docs/MesFormat/mesUploadTestDataFormat.json` 保持一致：

```json
{
  "barcode": "71202011752609010004567V8083",
  "componentcode": "L120201091",
  "station": "39C0-L2-1F-DIP16-FCT01",
  "fixturecode": "F1002",
  "traycode": "T02001",
  "programname": "TEST-DUT-001",
  "programversion": "V0.0.2",
  "testexecutetime": "2025/4/22 13:55:35.123",
  "testlongtime": "00:00:06.300",
  "result": "FAIL",
  "details": [
    {
      "TestItem": "测试温度",
      "TestStep": "SOC_HW_ID1",
      "StandardValue": "1.10",
      "UpperValue": "1.20",
      "LowerValue": "0.90",
      "MeasureValue": "1.12",
      "TestResult": "true",
      "TestBeginTime": "13:55:35.123",
      "TestEndTime": "13:55:37.123"
    }
  ],
  "isfinalreport": "false"
}
```

顶层字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `barcode` | string | 是 | 工件条码 |
| `componentcode` | string | 是 | 产品型号/组件号 |
| `station` | string | 是 | 工位/测试站编号，也是设备号 |
| `fixturecode` | string | 是 | 测试针床码；无值时传 `/` |
| `traycode` | string | 是 | 载具码；无值时传 `/` |
| `programname` | string | 是 | 测试程序名称 |
| `programversion` | string | 是 | 测试程序版本 |
| `testexecutetime` | string | 是 | 测试开始时间，`yyyy/M/d HH:mm:ss.SSS` |
| `testlongtime` | string | 是 | 总耗时，`HH:mm:ss.SSS` |
| `result` | string | 是 | 整单结论，`PASS` / `FAIL` |
| `details` | array | 是 | 测试明细，至少 1 条 |
| `isfinalreport` | string | 是 | 是否最终报告，`true` / `false` |

明细字段：

| 字段 | 说明 |
| --- | --- |
| `TestItem` | 测试项目名称 |
| `TestStep` | 测试步骤/子项名称 |
| `StandardValue` | 标准值，字符串原样 |
| `UpperValue` | 上限值，字符串原样 |
| `LowerValue` | 下限值，字符串原样 |
| `MeasureValue` | 实测值，字符串原样 |
| `TestResult` | 单项判定，`true` / `false` |
| `TestBeginTime` | 步骤开始时间 `HH:mm:ss.SSS` |
| `TestEndTime` | 步骤结束时间 `HH:mm:ss.SSS` |

成功响应信封：

```json
{
  "success": true,
  "code": "200",
  "message": "测试报告上次成功",
  "data": null
}
```

失败响应信封：

```json
{
  "success": false,
  "code": "400",
  "message": "测试报告上传失败",
  "data": null
}
```

业务码：

| code | 含义 | 是否重试 |
| --- | --- | --- |
| `"200"` | 成功 | 否 |
| `"400"` | 上传失败；参数错误、明细非法或服务端异常 | 否，修正数据后重传 |

更完整的字段约束见 [MES上传接口文档.md](MesFormat/MES上传接口文档.md)。

---

## 6. 放行判定

### 6.1 POST `/api/workpiece/check-in`

设备扫描产品条码后调用。本接口只查询和校验，不执行真正进站：不修改 `active_products`，不写流转历史，不改变产品工序，不修改托盘绑定或测试报告。

请求体：

```json
{
  "barcode": "71202011752609010004567V8083",
  "station": "39C0-L2-1F-DIP16-FCT01",
  "fixturecode": "F1002",
  "traycode": "T02001"
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `barcode` | string | 是 | 产品条码 |
| `station` | string | 是 | 当前工位编号 |
| `fixturecode` | string | 是 | 当前治具编号 |
| `traycode` | string | 是 | 当前托盘编号 |

成功响应：

```json
{
  "success": true,
  "code": "200",
  "message": "产品允许进站",
  "data": {
    "processcode": "MAX-TEST",
    "stepon": "1"
  }
}
```

失败响应（业务校验失败仍使用 HTTP 200）：

```json
{
  "success": false,
  "code": "400",
  "message": "产品进站失败：当前治具F1002的型号为LITE，与工序要求的型号LITE-ICT不匹配",
  "data": null
}
```

参数格式错误返回 HTTP 422；MES 内部异常返回 HTTP 500 且 `success=false`。

校验顺序：参数检查 → 产品/在制信息 → 工艺配置 → 当前工序/工艺路线 → 工序资源 → 工位设备型号 → 治具型号（工序配置了针床型号时才检查） → 托盘型号（工序配置了载具型号时才检查） → 既有锁定/FAIL/前道放行规则。空值按 `/` 上报；工序未配置针床/载具型号时，不检查对应主数据。

## 7. 开放性变量

### 7.1 GET `/api/variable/{name}`

读取变量。传入 `device_id` 时会记录 READ 日志。

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | path | 是 | 变量名 |
| `device_id` | query | 否 | 读取设备号；建议传 |

响应示例：

```json
{
  "name": "line_mode",
  "type": "str",
  "value": "AUTO",
  "updated_at": "2026/11/27 09:00:00.000"
}
```

### 7.2 POST `/api/variable/{name}`

写入变量。

请求体：

```json
{
  "value": "MANUAL",
  "device_id": "TEST-01"
}
```

`device_id` 为必填；兼容别名 `device` / `writer`。响应同读取变量。

---

## 8. 设备状态接口

### 8.1 GET `/api/device/enable`

查询设备是否开启。状态来自 `config/device_config.json`，设备端不应直接读取配置文件。

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `device_id` | query | 是 | 设备号 |

响应示例：

```json
{
  "device_id": "TEST-01",
  "enabled": true
}
```

### 8.2 POST `/api/device/heartbeat`

周期上报设备在线心跳。看板超过 30 秒未收到心跳会把设备显示为离线，建议每 10~20 秒调用一次。

请求体：

```json
{
  "device_id": "TEST-01"
}
```

响应示例：

```json
{
  "device_id": "TEST-01",
  "last_seen_at": 1764212400
}
```

### 8.3 POST `/api/device/test-start`

放行通过后、实际测试开始前调用，让看板把设备状态切换为“测试中”。

请求体：

```json
{
  "device_id": "TEST-01",
  "workpiece": "W-001"
}
```

`workpiece` 可选。响应示例：

```json
{
  "device_id": "TEST-01",
  "status": "测试中",
  "status_since": 1764212400
}
```

---

## 9. 推荐调用顺序

```text
1. GET  /health                         确认服务在线
2. GET  /api/device/enable             确认设备允许开启
3. POST /api/device/heartbeat           启动后及周期上报在线
4. GET  /api/program                   获取程序元数据
5. GET  /programs/{filename}           下载程序文件
6. POST /api/program/status             上报当前程序版本/SHA256/自检结果
8. POST /api/device/test-start         放行通过后开始测试
9. GET/POST /api/variable/{name}       按需读写开放变量
10. POST /api/v1/test-results          上传整单测试结果
```

终端测试结果（`LOCK` / `END`）会自动清除当前在制状态；测试报告和流转历史不会被删除。

---

## 10. 不在设备端范围内的接口

以下接口属于 Streamlit UI 或管理页面，设备端不应调用：

- `/api/ui/master`
- `/api/ui/bindings`
- `/api/ui/program/*`
- `/api/ui/product/*`
- `/api/ui/interlock-check`
- `/api/ui/workbench/*`
- `/api/ui/variables/*`
- `/api/ui/dashboard`
- `/api/ui/stations/*`
- `/api/ui/unlock`
- `/api/ui/upstream`

这些接口用于注册配置、产品查询、工位操作台、看板展示和页面管理。
