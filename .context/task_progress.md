# 任务进度

## 当前项目：my-mini-mes-pyhton
- **当前分支**：master
- **项目标题**：旁路式小型 MES
- [x] 已初始化 Context Sync
- [x] 梳理当前项目目标与范围
  - 已确认项目定位为设备乙方现场使用的轻量旁路 MES
  - 核心能力为程序下发、工序联锁、测试数据看板、开放变量与设备 HTTP 接口
  - 已明确不接入甲方 MES，不覆盖工单、BOM、物料、排产、WMS/APS/SPC/TPM、HMI 和完整权限体系
- [x] 实现“程序下发”页面的 Streamlit 占位 UI
  - 页面包含上传程序文件、程序运行列表、型号关联三个区块
  - 程序运行列表只允许切换版本，其他列全部只读
  - 程序类型根据 program_components 数量派生
  - 设备绑定已移除
  - 版本说明紧跟版本列，并根据所选历史版本联动
  - 程序列表列顺序已锁定，表头拖动不会换列；列宽仍可调整
  - 下载 URL 列宽 110px，关联型号数列宽 70px
  - 未接 FastAPI、数据库或 requests
- [x] 增加设备记录占位页面
  - 新增“设备拉取记录（最近 30 条）”和“设备状态上报记录（最近 30 条）”
  - 两类记录各提供 30 条 session-state 占位数据
  - 字段与正式页面保持一致，仅展示页面，不连接后端
- [x] 记录 gotchas / architecture
- [ ] 完成首次 /sync-save 与 /sync-load 验证

## 验证结果
- 程序下发页面测试：10 passed
- 完整测试套件：54 passed
- Agent API：程序运行列表的可编辑列仅为“版本”
- 列顺序与列宽拖拽的保护此前已通过 Playwright 验证
- 设备拉取记录与状态上报记录已在 AppTest 中验证各渲染 30 条
- 仅有 starlette.testclient 的 httpx 弃用警告，不影响当前功能
