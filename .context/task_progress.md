# 任务进度

## 当前项目：my-mini-mes-pyhton
- **当前分支**：master
- **项目标题**：旁路式小型 MES
- [x] 已初始化 Context Sync
- [x] 梳理当前项目目标与范围
- [x] 实现“程序下发”页面
- [x] 实现“工序注册”页面
- [x] 实现“设备注册”页面
  - 增加线体管理与 devices.line_id
  - 被设备引用的线体禁止删除
- [x] 实现“产品管理”页面
  - 产品、工序流程、设备分配均已实现
  - 设备分配已改为“选产品 → 选线体 → 选工序 → 选设备”
  - 线体只作为候选筛选条件，不写入 product_step_devices
  - 保存会覆盖该 product_model + step_no 的全部分配
  - 区块底部说明跨线体保存覆盖规则
- [x] 记录 gotchas / architecture
- [ ] 完成首次 /sync-save 与 /sync-load 验证

## 验证结果
- 产品管理测试：18 passed
- 完整测试套件：98 passed
- Agent API：L2 + 功能测试过滤出 TEST-02、TEST-02B，默认回显 TEST-02
- 仅有 starlette.testclient 的 httpx 弃用警告，不影响当前功能
