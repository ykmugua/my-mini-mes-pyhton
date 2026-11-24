# 接口行为说明

### V1.3 上传接口要点（2026-11-18）

- 路径：`POST /api/v1/test-results`（机台）；旧 `/api/test-result` 保留供内部。
- 请求头必填：x-device-sn（须==payload.barcode）、x-timestamp、x-request-id（幂等键，重试复用）。
- 明细字段名是 `LowerValue`（JSON 示例为准）。
- 业务码：0 成功 / 40001 参数错误 / 40003 SN 不匹配 / 409 冲突 / 50000 内部错误。
- 服务端不解析数值/布尔/时间字符串（协议层）；内部入库仍复用 services.report_test_result 做可信性判定。

- Streamlit 工位操作台的手动入站标签采用按需渲染。控件离开渲染树时默认会丢弃 widget state，因此产品型号、每行数量、载具输入、动态条码输入和启用复选框均使用 `persist_state="session"`，以便切换标签后恢复现场输入。显式“清空输入”仍通过回调重置批次状态。

- 主数据种子文件支持环境变量 `MES_MASTER_SEED_FILE` 覆盖；测试用 `tests/fixtures/master_data.json`，生产/开发默认用 `src/py_server/master_data.json`。
