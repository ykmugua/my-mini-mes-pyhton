# 当前进度

- README.md 已按当前架构重写。
- 测试报告数据库统一为 data/TestReport.db，按工序拆为 report_index_1/2/3 多张总览表；每张报告使用工序隔离的 SN 明细表。
- 测试履历 tag 页只显示当前选中产品实际有测试数据的工序页签。
- 删除入站状态释放 ProductFlow 与无测试数据的工件占位，已有测试数据保留。
- 组件号/程序名/工艺号支持修改，主键改名在 API 层同步关联引用。
- 四类注册页统一复用 registry_helpers.py 与 constants.py；新增跨层 constants.py 清理魔术字符串；所有函数/类已补 docstring。
- 新增 docs/CODEBASE_GUIDE.md：函数职责、设计模式、框架、数据库和测试说明。
- 全量测试 116 passed。
- 本轮注释/注册页统一/文档任务尚未 `/sync-save`，尚未提交 git。
