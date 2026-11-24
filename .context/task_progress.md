# 当前进度

- README.md 已按当前架构重写。
- 测试报告数据库统一为 data/TestReport.db，按工序拆为 report_index_1/2/3 多张总览表和工序隔离的 SN 明细表。
- 测试履历 tag 页只显示当前选中产品实际有测试数据的工序页签。
- 删除入站状态释放 ProductFlow 与无测试数据的工件占位，已有测试数据保留。
- 组件号/程序名/工艺号支持修改，主键改名在 API 层同步关联引用。
- 四类注册页统一复用 registry_helpers.py 与 constants.py；跨层 constants.py 清理魔术字符串；所有函数/类已补 docstring。
- 新增 docs/CODEBASE_GUIDE.md，说明函数职责、框架、数据库、设计模式和流程。
- UI 已强制只通过 FastAPI 访问 repositories/数据库，架构测试锁定 ui/ 不直连数据层。
- 已删除旧兼容：/api/test-result、TestResultIn、旧分库路径别名、db.py 原始 sqlite 兼容函数、旧 _tx 别名、旧测试语义；设备示例改用 V1.3。
- 全量测试 110 passed。
- 本轮清理尚未 `/sync-save`，尚未提交 git。
