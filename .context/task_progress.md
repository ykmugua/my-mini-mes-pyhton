# 任务进度

## 当前项目：my-mini-mes-pyhton

- **当前分支**：master
- **项目标题**：旁路式小型 MES

- [X] 已初始化 Context Sync
- [X] 梳理当前项目目标与范围
- [X] 实现“程序下发”页面
- [X] 实现“工序注册”页面
- [X] 实现“设备注册”页面
  - 增加线体管理与 devices.line_id
  - 被设备引用的线体禁止删除
- [X] 实现“产品管理”页面
  - 产品、工序流程、设备分配均已实现
  - 设备分配已改为“选产品 → 选线体 → 选工序 → 选设备”
  - 线体和工序筛选并排显示
  - 线体只作为候选筛选条件，不写入 product_step_devices
  - 保存会覆盖该 product_model + step_no 的全部分配
- [X] 调整产品工序流程
  - 去掉关键工序字段与左侧整行删除/选择控件
  - 成功下站、失败下站均可选择启用工序
  - 新增行保持可用，使用 num_rows="add"
  - 增加逐行删除 ButtonColumn + 确认弹窗
  - 确认删除只移除对应流程节点
- [X] 新增系统设计框架文档
  - `system_design_framework/manual.md`
  - `system_design_framework/System_Architecture_Diagram.drawio`
  - 目标分层：测试机台/Streamlit → FastAPI → Repository → SQLAlchemy Engine → SQLite/PostgreSQL
- [X] 记录 gotchas / architecture
- [X] 完成 /sync-save 与 /sync-load 验证

## 验证结果

- 产品管理测试：20 passed
- 完整测试套件：100 passed
- Agent API：产品页 ready；流程编辑器为 add-only；线体/工序位于同一双列布局
- 浏览器：流程删除按钮可弹出确认框，确认后流程行由 3 行变为 2 行
- 服务端控制台无新增警告或异常
- 仅有 starlette.testclient 的 httpx 弃用警告，不影响当前功能
