# 接口行为说明

### V1.3 上传接口要点（2026-11-18）

- 路径：`POST /api/v1/test-results`（机台）；旧 `/api/test-result` 保留供内部。
- 请求头必填：x-device-sn（须==payload.barcode）、x-timestamp、x-request-id（幂等键，重试复用）。
- 明细字段名是 `LowerValue`（JSON 示例为准）。
- 业务码：0 成功 / 40001 参数错误 / 40003 SN 不匹配 / 409 冲突 / 50000 内部错误。
- 服务端不解析数值/布尔/时间字符串（协议层）；内部入库仍复用 services.report_test_result 做可信性判定。
