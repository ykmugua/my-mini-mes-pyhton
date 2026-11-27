# 接口行为说明

### V1.3 上传接口要点（2026-11-18）

- 路径：`POST /api/v1/test-results`（机台）；旧 `/api/test-result` 保留供内部。
- 请求头必填：x-device-sn（须==payload.barcode）、x-timestamp、x-request-id（幂等键，重试复用）。
- 明细字段名是 `LowerValue`（JSON 示例为准）。
- 业务码：0 成功 / 40001 参数错误 / 40003 SN 不匹配 / 409 冲突 / 50000 内部错误。
- 服务端不解析数值/布尔/时间字符串（协议层）；内部入库仍复用 services.report_test_result 做可信性判定。

- Streamlit 工位操作台的手动入站标签采用按需渲染。控件离开渲染树时默认会丢弃 widget state，因此产品型号、每行数量、载具输入、动态条码输入和启用复选框均使用 `persist_state="session"`，以便切换标签后恢复现场输入。显式“清空输入”仍通过回调重置批次状态。

- 主数据种子文件支持环境变量 `MES_MASTER_SEED_FILE` 覆盖；测试用 `tests/fixtures/master_data.json`，生产/开发默认用 `src/py_server/master_data.json`。

- 新增只读设备接口 `/api/workpiece/check-in`：device router 接收严格小写字段 barcode/station/fixturecode/traycode；application/workpiece_check_in.py 编排只读校验；repositories/workpiece_checkin_repo.py 承载所有 SQL。业务失败为 HTTP 200 + success=false/code=400，参数格式错误 422，内部异常 500。复用 InterlockPolicy、ProgramTrustPolicy 和现有程序绑定/前道 PASS 规则。接口不写 active_products、不写 ProductFlow、不改测试报告。

- 测试报告上传的工序切换只由 `isfinalreport=true` 触发；`false` 只入报告/结果，不改变产品当前工序或流转状态。终态切换按 `process_routes.success_next_step/fail_next_step`，成功切到下一工序时 `active_products.current_step` 同步为下一工序；终态则自动解绑整盘。

- 最终报告 `isfinalreport=true` 才触发工序切换；成功后 `active_products.current_step` 更新为路线 `success_next_step`，同时按“新的当前工序”再查下一次成功下站写入 `next_step`。例如 MAX-TEST 工序 1 通过后应为 `current_step=2, next_step=END`；`isfinalreport=false` 不切换工序。

- 工件解锁不再无条件 upsert `active_products`：只有产品原本就在当前在制表中时才同步更新；已因 FAIL/LOCK/END 下线的工件解锁后仍保持不在制，只更新工件锁状态和 ProductFlow 历史。新增 `active_product_repo.get_active()` 精确查询。

- `product_flow_store.create_inbound()` 对已有 `product_overview.barcode` 改为更新而非重复插入，修复解锁后重新入站触发唯一索引 500。回归覆盖“失败下线 → 解锁 → 重新入站”。全量测试 136 passed。
