# 架构决策记录

## 1. ADR-001：项目定位与系统边界（2026-11-12）

**状态**：已确认

**决策**：项目定位为设备乙方在现场内部使用的“旁路式小型 MES”，目标是围绕单机设备侧调试、程序可信性、工序放行和测试数据可视化提供最小闭环，而不是替代甲方完整 MES。

**在范围内**：
- 程序可信性：设备-产品-程序版本绑定、文件上传与 SHA256、设备拉取与状态上报、版本漂移告警。
- 工序联锁：按产品和设备配置前道关键设备，仅可信 PASS 放行；FAIL、不可信结果或前道缺失时锁定；人工解锁必须填写原因、勾选确认并保留日志。
- 测试数据看板：按设备测试时间统计今日 PASS/FAIL/合格率，排除不可信数据出合格率，并展示 FAIL 分布。
- 开放变量：页面维护 int/str/bool 变量，设备通过 HTTP 读写，供工序间或机台间交换数据。
- 设备接口：FastAPI 提供拉取程序、上报状态/结果、联锁查询、变量读写、健康检查和程序文件下载。

**明确不在范围内**：
- 不对接甲方 MES，不实现工单、BOM、物料、排产或生产订单管理。
- 不实现 WMS、APS、SPC、TPM、HMI 等完整制造系统能力。
- 不提供完整登录、RBAC 或接口鉴权；当前仅通过页面角色切换区分编辑/只读，适用于可信内网。

**架构约束**：
- 技术栈为 Streamlit + FastAPI + SQLite（WAL），页面与接口是两个独立进程，共享同一 SQLite 数据库和程序文件目录。
- 当前部署模型是单机内网部署，而不是高可用或分布式多实例；数据库时间统一存 UTC，业务展示使用可配置时区。
- 页面与设备接口共用 `services.py` 中的业务规则，避免两套判定口径。
- 运行数据位于 `data/` 且不进入 Git；跨设备恢复项目上下文依赖仓库内 `.context/`，项目业务数据仍需单独备份或迁移。

## 2. ADR-002：程序下发页采用独立 session-state 原型入口（2026-11-12）

**状态**：已采用

**背景**：需要先验证程序下发页面的数据模型、编辑流程和校验体验，但本阶段明确不连接 FastAPI。

**决策**：
- 新增项目根目录的 `streamlit_app.py` 和 `app_pages/program.py` 作为独立前端原型。
- 原有的后端联调入口 `src/py_server/streamlit_app.py` 保持不变，避免影响现有四页面应用和接口测试。
- 原型的三组数据只存在于 `st.session_state`：`programs`、`program_components`、`program_bindings`；首次进入会话时从纯函数初始状态深拷贝注入。
- 页面只负责交互和校验；程序列表、型号关联和设备绑定保存前先构造完整候选结果，校验通过后再写回 session state。
- 后续接入 FastAPI 时，以这三个数据模型替换 session-state 读写边界，页面交互结构可保留。

**边界**：
- 不实现文件落盘、真实 SHA256 持久化、版本漂移、缓存清理或鉴权。
- 下载地址按 `MES_API_PUBLIC_BASE` 的占位规则生成，当前固定为演示内网地址。

## 3. ADR-003：程序下发改为按工序建模并由型号关联派生程序类型（2026-11-12）

**状态**：已采用，替代 ADR-002 中的程序模式与设备绑定部分

**决策**：
- `programs` 字段收敛为 `program_id`、`program_name`、`program_version`、`sha256`、`download_url`、`step_no`，不再保存 `program_mode`。
- 程序类型不再入库，完全由同一程序的 `program_components` 数量派生：0=未关联，1=单型号，多个=多型号。
- `line_steps` 作为 session-state 中的只读线体工序引用，上传和程序列表从中选择 `step_no`。
- 设备绑定不属于程序下发页，已从 mock session state、页面区块和相关交互中移除，后续归入“产品工序”页面。
- 新增 `program_data_version=2` 迁移标记；热重载遇到旧会话时，为旧程序补齐 step_no、移除 program_mode 和 program_bindings。

**影响**：
- 型号关联保存只校验同一程序内型号重复；0 个关联允许保存，但显示“无法被产品工序使用”的持久警告。
- 上传的新程序默认关联型号数为 0，程序类型显示“未关联”。

## 4. ADR-004：程序列表使用历史版本下拉选择（2026-11-12）

**状态**：已采用

**决策**：
- 新增 session-state 占位数据 `program_versions`，每项保存 program_id 与 program_version。
- 程序列表的“版本”列使用 `st.column_config.SelectboxColumn`，与“所属工序”相同，不再手工输入版本。
- 候选版本由 program_versions 与 programs 当前版本合并去重，保留配置顺序。
- 上传新程序时同步加入 program_versions，后续可继续选择该版本。
- session-state 结构版本提升为 3；旧会话迁移时补齐 program_versions，并将现有 programs 的版本加入候选。

**边界**：本次只改变版本选择交互和占位历史版本，不实现真实版本文件、SHA256 或下载 URL 的版本切换。

## 5. ADR-005：版本说明作为版本级元数据（2026-11-12）

**状态**：已采用

**决策**：
- `programs` 与 `program_versions` 都增加 `version_description`。
- 上传程序时新增“版本说明”输入，可选填写；说明同时写入当前程序和 program_versions。
- 程序列表列顺序固定为“版本”后紧接“版本说明”，版本说明使用可编辑 TextColumn。
- 修改版本说明时同步更新 program_versions 中对应 program_id + program_version 的说明。
- 切换到历史版本时自动读取该历史版本自己的说明；没有历史说明时回退到列表当前输入值。
- session-state 结构版本提升为 4；迁移旧会话时补齐程序和版本候选的说明字段。

**边界**：版本说明是当前占位层元数据，真实持久化、审计历史和 API 同步留待后端接入。

## 6. ADR-006：程序列表固定列顺序但允许调整列宽（2026-11-12）

**状态**：已采用

**背景**：Streamlit 1.67 的 st.data_editor 底层使用 Glide Data Grid，默认允许拖动表头改变列顺序；公开 API 只有 column_order，用于设置初始顺序，没有“锁定列顺序”参数。

**决策**：
- 为程序列表容器设置 key=`program_list_panel`，生成作用域 `.st-key-program_list_panel`。
- 使用 st.html(unsafe_allow_javascript=True) 注入作用域 JS，只附着到该列表的 `.dvn-scroller`。
- 在表头区域记录 pointerdown；拖动超过阈值时拦截 pointermove，pointerup 仍交给 Glide 完成状态复位，并抑制拖动后的 click。
- 当表头光标为 `col-resize` 时视为列宽调整，不拦截，因此原生列宽拖动保持可用。
- 下载 URL 宽度=110px，关联型号数宽度=70px。

**边界**：这是对 Streamlit 前端 DOM 的定点兼容处理，不是 Streamlit 公共参数；升级 Streamlit 后应复查 `.dvn-scroller`、表头高度和 col-resize 行为。

## 7. ADR-007：程序运行列表只开放版本切换（2026-11-12）

**状态**：已采用

**决策**：
- 区块名称由“程序列表”改为“程序运行列表”。
- st.data_editor 的 disabled 列集合包含除“版本”以外的全部业务列。
- 程序名、所属工序、版本说明、SHA256、下载 URL、关联型号数和程序类型均只读。
- 用户只能通过版本下拉选择历史版本，再点击“保存程序修改”写回 session state。
- 切换版本时仍由后端占位逻辑带出对应版本说明。

**原因**：程序运行记录用于选择已发布版本，不允许在运行列表中修改程序元数据，避免绕过程序发布与型号关联流程。

## 8. ADR-008：设备记录先以 session-state 占位展示（2026-11-13）

**状态**：已采用

**决策**：
- 程序下发占位页新增“设备拉取记录（最近 30 条）”和“设备状态上报记录（最近 30 条）”。
- 两类记录分别保存于 session-state 的 `program_pulls` 与 `program_status_logs`，各提供 30 条模拟数据。
- 展示字段沿用正式页面的时间、设备、产品、程序版本、SHA256、可信状态和原因。

**边界**：当前阶段只实现页面，不连接 FastAPI、数据库或 services 层；后续接入真实数据时再替换 session-state 数据源。

## 9. ADR-009：工序主数据与产品工序实例分离（2026-11-13）

**状态**：已采用

**决策**：
- 全厂工序主数据存放在 session-state `steps`，字段固定为 `step_no`、`step_name`、`enabled`、`remark`。
- 工序注册页负责新增、删除、启停和备注维护；不包含 device_id、seq、required。
- `step_no` 和 `step_name` 均校验唯一，避免跨产品引用歧义。
- 停用工序只影响新配置下拉，不删除历史数据；程序运行列表仍按全部 steps 解析既有 step_no。
- 程序下发上传的“所属工序”只读取 enabled=true 的工序；没有启用工序时阻止上传并提示先维护工序注册。

**后续衔接**：产品注册页应只从 enabled=true 的 steps 选择工序实例，再在产品侧保存顺序、设备、程序、关键性等属性。

**迁移**：state schema 6 将旧 `line_steps` 转换为 `steps`，保留工序号和名称，默认启用，并移除 device_id。

## 10. ADR-010：工序注册采用独立新增表单和受限列表编辑（2026-11-13）

**状态**：已采用

**决策**：
- 工序注册页分为“新增工序”和“工序列表”两个 bordered container，与程序下发页结构保持一致。
- 新增通过 expander + form 完成，不做表格动态增行；保存成功后追加 steps 并 rerun。
- 工序列表使用固定行数 data_editor，只开放“启用”列；工序号、工序名、备注只读。
- 删除使用 ButtonColumn。点击回调只把目标 step_no 写入 pending_step_delete，不在回调中直接删除。
- 确认弹窗读取 pending 状态，显示待删工序并提供取消/确认删除；确认后才从 session state 移除。
- 删除不会修改历史程序记录，历史引用可能显示为“未配置工序”。

**原因**：新增属于创建流程，删除属于破坏性操作，应与日常启停编辑分离并提供明确确认。

## 11. ADR-011：设备注册采用一对多工序引用（2026-11-13）

**状态**：已采用

**决策**：
- session-state `devices` 字段为 device_id、device_name、step_no、enabled、remark。
- 每台设备只引用一个工序；工序来源为 steps 中 enabled=true 的记录。
- 新增设备使用独立 expander + form；设备编号和名称必填且设备编号唯一。
- 设备列表固定行数，只开放“所属工序”和“启用”两列；设备编号、名称、备注只读。
- 删除使用 ButtonColumn 写入 pending_device_delete，下一次 rerun 调用 st.dialog 确认；取消不清除设备。
- 无启用工序时页面顶部 warning，工序下拉为空且“添加设备”按钮 disabled。

**边界**：设备与产品的绑定由后续“产品注册”页面承担，本页只维护设备主数据。

**迁移**：state schema 7 为现有会话补充 4 条设备占位数据。

## 12. ADR-012：产品工序流程与可选设备范围分离（2026-11-13）

**状态**：已采用

**决策**：
- `products` 保存产品型号、名称、测试程序信息与备注，product_model 唯一。
- `product_routes` 保存产品工序节点：当前工序、成功下站、失败下站、是否关键。成功下站可为 END 或步骤；失败下站可为 END、LOCK 或步骤。
- `product_step_devices` 独立保存产品-工序-设备分配，表示某型号在某道工序允许使用的设备范围。旧 `product_step_configs` 已废弃并清除。
- 删除产品时级联删除 product_routes 和 product_step_devices。
- 工序流程保存校验工序重复及下站目标必须存在于当前产品流程；成功路径成环仅 warning，不阻断保存。
- 设备分配使用 multiselect，只展示当前产品、当前工序且 enabled=true 的设备。

**边界**：required 只存配置；本页不实现放行判定，也不决定本次生产具体选中哪台设备。

**迁移**：state schema 8 增加产品数据，并为每道工序补充至少两台启用设备占位数据。

## 13. ADR-013：线体作为设备主数据维度（2026-11-13）

**状态**：已采用

**决策**：
- session-state `lines` 保存 line_id、line_name；line_id 必填唯一，线体无启停状态。
- devices 增加必填 line_id；设备归属一条线体和一道工序。
- 设备注册页调整为三个区块：线体管理、新增设备、设备列表。
- 线体删除采用 ButtonColumn + pending state + 确认弹窗；确认时统计引用设备，有引用则阻止并显示数量。
- 新增设备和设备编辑均校验 line_id 存在于 lines。
- 没有线体时页面顶部 warning，新增设备线体下拉为空且提交按钮禁用。

**迁移**：state schema 9 增加 L1/L2 占位线体，并为旧 devices 按工序补齐 line_id。

## 14. ADR-014：产品设备分配采用线体筛选但按型号+工序保存（2026-11-13）

**状态**：已采用

**背景**：产品设备分配新增线体条件。需要确认同一型号同一工序是否按线体独立保存。

**决策**：
- product_step_devices 不增加 line_id，联合键仍为 product_model + step_no + device_id。
- line_id 只用于筛选当前可勾选设备：device 必须同时匹配当前线体、当前启用工序且 enabled=true。
- multiselect 的 widget key 包含 product_model、line_id、step_no，因此切换线体或工序时正确回显候选分配。
- 保存时校验选中设备仍在当前候选集合内，然后先删除 product_model + step_no 的全部旧记录，再写入新记录。
- 这意味着同一型号同一工序跨线体保存会覆盖其他线体的既有分配，产品页面已明确 caption 说明。
- 流程工序在当前线体下无设备时显示 warning；不阻断保存。

**边界**：如果未来要求型号×工序×线体独立设备范围，需要升级表结构，增加 line_id 并同步迁移。

## 15. ADR-015：产品工序流程使用显式节点删除与并排设备筛选（2026-11-13）

**状态**：已采用

**决策**：
- `product_routes` 移除 `required`（关键工序）字段；当前流程节点字段为 product_model、step_no、success_next_step、fail_next_step。
- 成功下站和失败下站均使用 `SelectboxColumn`，都可选择启用工序；成功额外支持 END，失败额外支持 END/LOCK。
- 编辑器中的下站值统一序列化为字符串；保存时再转回整数工序号或 END/LOCK 终端标记，避免混合类型列被自动禁用。
- 流程表使用 `num_rows="add"`，保留新增行，不显示左侧整行删除/选择控件。
- 删除列使用 `ButtonColumn`：点击只写入 pending_product_route_delete，rerun 后弹出 st.dialog；确认后仅删除对应 product_model + step_no 节点。
- 设备分配的“选择线体”“选择工序”使用 `st.columns(2)` 并排显示；候选设备仍按产品、线体、工序、启用状态过滤。
- state schema 提升为 10，旧会话中的 product_routes.required 自动移除。

**边界**：删除流程节点不会级联删除 product_step_devices；只会在引用失效时由保存校验提示重新配置。

## 16. ADR-016：采用分层系统设计框架文档（2026-11-13）

**状态**：已采用（目标架构，当前 Streamlit 原型尚未接后端）

**文档位置**：
- [系统框架设计](../system_design_framework/manual.md)
- [架构图 Draw.io](../system_design_framework/System_Architecture_Diagram.drawio)

**目标调用链**：测试机台 → FastAPI；工位操作员 → Streamlit → FastAPI；FastAPI → Repository → SQLAlchemy Engine → SQLite（未来可换 PostgreSQL）。

**核心原则**：
- FastAPI 是所有机台和 Streamlit 数据访问的唯一入口，负责参数校验、错误处理和日志。
- Repository 是唯一编写 SQL 的层，使用 SQLAlchemy Core 并提供事务边界。
- Streamlit 只负责界面，通过 HTTP 调 FastAPI，不直接访问数据库或 Repository。
- 测试机台保持只读；修改操作仅由操作员通过 Streamlit 触发。
- 数据库更换只影响连接配置与 Repository 内部实现，上层接口保持稳定。

**边界**：当前所有页面仍使用 `st.session_state` 占位数据；上述分层是后续 FastAPI/Repository/数据库接入的设计约束。

## ADR-017：旁路 MES 分层改造（2026-11-16，进行中）

**状态**：已采用，分阶段实施

**目标架构**：FastAPI 独占数据库；Streamlit 只走 HTTP；domain/ 纯 Python；repositories/ 唯一写 SQL；application/ 仅 3 个用例（report_test_result / unlock_workpiece / report_program_status）持有事务边界。

**关键决策**：
- 保持 SQLite 表结构逐字不变（列名/类型/唯一约束/索引），SQLAlchemy Core Table 元数据与现有 SCHEMA 对齐；init_schema() 只用 metadata.create_all。
- 兼容层：repositories/base.py 提供 with_conn()/with_read_conn()，conn 为轻量 adapter，支持 conn.execute(stmt, params) 接受 SQLAlchemy 语句；repo 函数接受外部 conn。
- services.py 暂时保留为兼容层（测试/seed 仍直接调用），内部编排逐步委托 repository + domain + application；最终 UI 通过 HTTP client 访问。
- 领域错误 DomainError 由 services.ServiceError 继承，保证 FastAPI 异常处理与既有测试无变化；reason 文案保持现有中文字符串以免破坏断言。
- 指纹优先级：测试结果字段优先于 status 上报，两者无则 NO_REPORT。
- 人工放行记录在 interlock 中先于前道检查、后于 FAIL 检查。

## 17. ADR-018：接入 app_pages 主数据页面（2026-11-16，进行中）

**状态**：已采用，执行中

**需求**：用 app_pages 的 4 个页面（程序下发、工序注册、设备注册、产品管理）替换现有程序下发页，并新增 3 个主数据页；保留现有看板、变量页；移除工序锁页。数据全部走 HTTP。

**数据模型映射**（state key → 表）：
- steps → steps(step_no PK, step_name, enabled, remark)
- lines → lines(line_id PK, line_name)
- devices → devices(device_id PK, device_name, line_id, step_no, enabled, remark)
- programs → programs(program_id PK, program_name, program_version, version_description, sha256, download_url, step_no)
- program_versions → program_versions(program_id, program_version, version_description, PK(program_id,program_version))
- program_components → program_components(program_id, component_no, PK)
- products → products(product_model PK, product_name, test_program_name, test_program_path, remark)
- product_routes → product_routes(product_model, step_no, success_next_step, fail_next_step, PK)
- product_step_devices → product_step_devices(product_model, step_no, device_id, PK)

约束：不改已有 9 张表；新增 9 张主数据表；表定义仍用通用类型；repository 唯一写 SQL；页面只 import ui/client。保留看板/变量/现有验收测试不变。

## 变量三层结构（2026-11-16）

**决策**：开放性变量支持最多三层的 `组.子组.键` 点分路径（第一层组名任意），对应 JSON 树 `{组:{子组:{键:值}}}`。
- 底层不变：仍存扁平 variables 表，完整点分路径即变量名；设备 API `/api/variable/{name}` 完全兼容（旧扁平变量照常）。
- 新增 services.split_variable_name/variables_tree + `/api/ui/variables/tree` + client.variables_tree。
- 页面：层级视图（st.json + 递归展开）+ 平铺列表；新增表单按三层输入（第一层必填，二三层可选）。
- 超过三段的变量名：第三段及之后合并为第三段，保证最多三层。
- 138 passed，真实 HTTP 往返验证通过。

## 18. ADR-019：工站监控看板数据源改为 station_summary（2026-11-17）

**决策**：看板只读 SQLite 汇总表 station_summary（+ station_fail_detail），不读 Redis、不算业务逻辑、不操作原始流水表。
- 前端只展示；状态/计数由后端接收报文时维护汇总表。
- 设备显示清单来自 config/device_config.json；新增设备从设备注册页 devices 表选择（enabled=true），按产线/工序筛选。
- 定时刷新用 `@st.fragment(run_every=1000)` 只刷卡片区，避免设备管理/删除弹窗被全局刷新打断。
- 失败明细单独存表，供卡片「失败详计」tab 展示。

## ADR-020：设备 ID 统一（2026-11-17）

演示环境的 station_summary / station_fail_detail / config 设备 ID 统一为设备注册页的 TEST-xx（早期用 D01-D06，已废弃）。

## 19. ADR-021：产品查询页只读+受控解绑（2026-11-17）

追溯全部只读（workpieces/test_results/product_routes/unlock_logs）；工序解绑复用现有 unlock 用例（状态回 PENDING、写 unlock_logs、不原始测试记录），保留原因必填+勾选确认约束。不新建业务表。

## 20. ADR-022：图层卡片刷新用 fragment 局部刷新（2026-11-17）

全局 st_autorefresh 每秒重建整页，导致删除确认弹窗闪烁。改为 @st.fragment(run_every=1000) 只刷卡片区，设备管理/弹窗不重建。sort_items 自定义组件 key 需含设备列表指纹，避免增删设备后组件缓存旧状态。

### ADR-023：MES V1.3 整单上传接口（2026-11-18）

- 新增 `POST /api/v1/test-results`：机台主上传接口，整单 payload（station/linecode/testtime/barcode/result/testlongtime/details[]/programname/programversion）+ 三请求头（x-device-sn/x-timestamp/x-request-id）。
- 字段 `LowerValue`（按 mesUploadTestDataFormat.json），不是文档里的 littleValue。
- 响应统一信封 `{success,message,code,result}`；result 可为 null。
- 旧接口 `/api/test-result` 保留，仅供内部/测试使用（用户选 B：不物理删除）。
- V1.3 上报后维护 station_summary / station_fail_detail；复测判定=同一 barcode 在 test_results 已有记录。
- 幂等键 x-request-id → upload_requests 表。
- 架构冲突处理：方案 A——看板继续走 Streamlit → station_repo → Engine 直读，design_data/system_design_framework/manual.md 的措辞已改为“FastAPI 是机台上传和业务写入的唯一入口，只读看板是例外”。

- **关联**：[ADR-022](architecture.md#adr-022)

### ADR-024：架构定位修正——FastAPI 主给机台，Streamlit 可经 Repository 读写（2026-11-18）

- 用户明确：FastAPI 主要给机台使用；Streamlit 作为内部工具**可以直接通过 Repository 读写数据库**（看板已如此），也可经 HTTP 调 FastAPI。
- 作废之前 ADR-023 / README / manual 里"FastAPI 是写入唯一入口"的措辞。
- 正确表述：**Repository 是唯一写 SQL 的地方**；上层（FastAPI 和 Streamlit）都不写 SQL、不感知 SQLAlchemy，都经 Repository 访问数据库。
- 已同步更新：README.md（技术栈/取舍/ASCII 图/部署/FAQ）、design_data/system_design_framework/manual.md、System_Architecture_Diagram.drawio。
- 结论：V1.3 实现代码不变（仍复用 services/report_test_result），只是文档/架构图的定位描述纠正。

- **关联**：[ADR-023](architecture.md#adr-023)

### ADR-025：V1.3 整单上报主子表建模（2026-11-18）

- 按用户设计：新增 `test_reports`（整单主表，request_id 唯一做幂等）+ `test_report_details`（明细子表，自增 id + report_id 关联）。
- 删除原 `upload_requests` 幂等表；幂等直接用主表 request_id 唯一键。
- 旧 `test_results` 单条表保留，继续服务 `/api/test-result` 和可信性/联锁；V1.3 上报仍逐条调 `services.report_test_result` 保持联锁链路。
- 产品查询测试履历：优先返回新主子表整单（顶层字段 + details 列表），无则回退旧 test_results 单条表格。
- 前端测试履历：整单顶层字段用只读 text_input 显示，details 用 dataframe 列表。
- seed 演示数据新增一单 SN202611170001（两条明细），供页面立即展示。

- **关联**：[ADR-023](architecture.md#adr-023)，[ADR-024](architecture.md#adr-024)

### ADR-026：V1.3 JSON 字段变更（componentcode / testexecutetime）2026-11-18

- 用户修改 mesUploadTestDataFormat.json：新增 `componentcode`（型号码），`testtime` 改名 `testexecutetime`；字段顺序改为 linecode/station/componentcode/barcode/programname/programversion/testexecutetime/testlongtime/result/details。
- 同步：schemas_v1、engine.test_reports、upload 用例、seed 派生 10 份、测试、README、协议文档。
- 产品查询展示按用户明确要求：JSON 顶层字段每个用只读 text_input（9 个），details 用 dataframe 10 列（含子表自增 id + 9 个明细字段）。

- **关联**：[ADR-025](architecture.md#adr-025)

### ADR-027：生产明细独立库 + 每产品一张明细表（2026-11-18）

- 用户要求：生产数据几十万级，details 必须和主表/其他部分分离；格式稳定，换项目只改 Details 部分；每个产品独占一张明细表，id 从 1 开始。
- 新增独立 SQLite 库 `data/details.db`（环境变量 `MES_DETAILS_DB_PATH`），主库 `mes.db` 仍存 test_reports 主表/业务数据。
- 新增 repositories/report_details_store.py：按 barcode 哈希生成表名 `d_<hash16>`，每个产品一张表；id 自增从 1 开始，含 report_id + 9 个 JSON 明细字段；按 report_id 索引。
- report_repo.insert_report 写主表到主库，明细到独立库；list_reports 按 report_id 从独立库读明细。
- engine.py 删除共享 test_report_details 表；get_details_engine() 管理独立库 Engine；reset_for_tests 清两套缓存。
- seed 重置调 drop_all_tables() 清空独立库；conftest 给测试隔离 MES_DETAILS_DB_PATH。
- 验证：10 个产品 = 10 张 d_* 表，每张 id 从 1 开始；全量 151 passed。

- **关联**：[ADR-026](architecture.md#adr-026)

### ADR-028：details.db 总览表 report_index + isfinalreport（2026-11-18）

- 用户再改 JSON：新增 `isfinalreport`（是否最终报告）。
- 设计定稿：details.db 里新增总览表 `report_index`，列：id / linecode / station / componentcode / barcode / programname / programversion / testexecutetime / testlongtime / details_table / isfinalreport / failed_step。每次整单上报一行；details_table 存 `d_<hash>` 表名指向该产品的明细表；failed_step 存失败项 TestStep（成功为空）。
- 原 details.db 每产品明细表 d_<hash> 不变（每行一条明细，id 从 1 开始，report_id 关联）。总览表提供全局/产品级快速查询入口。
- 主库 test_reports 也加 isfinalreport 列；schemas_v1、上传用例、seed、测试、README、协议文档同步。
- 验证：overview 10 行、detail tables 10 张；全量 pytest 152 passed。

- **关联**：[ADR-027](architecture.md#adr-027)

### ADR-029：TestReport.db 表结构与查询交互定稿（2026-11-18）

- 用户 6 点要求全部落地：
  1. 明细表名去掉 d_ 前缀，改为 `SN_<条码safe>_<hash16>`（如 SN_SN202611180001_d6e753570391a815）；
  2. 明细表去掉 report_id 列和索引；
  3. 独立库从 details.db 改名 TestReport.db（MES_DETAILS_DB_PATH）；
  4. 明细表/总览表不用 AUTOINCREMENT（id INTEGER PRIMARY KEY），重置时 DROP sqlite_sequence；验证无 sqlite_sequence；
  5. 产品查询去掉时间筛选；
  6. 测试履历分两块：上块 report_index 总览表（按条码筛选、点行选中），下块按选中行 details_table 显示对应明细表（10 列，无 report_id）。
- 新增 API：/api/ui/product/report-index、/api/ui/product/report-details（校验 SN_ 表名格式防注入）。
- 验证：10 SN_ 表 + report_index，无 sqlite_sequence；AppTest 0 异常、datetime_input 0；全量 152 passed。

- **关联**：[ADR-028](architecture.md#adr-028)

### ADR-030：数据库约定文档（2026-11-18）

- 用户要求先把约定的测试报告数据库、产品流转数据库写成文档，代码暂不改。
- 新增 design_data/DatabaseConventions/测试报告数据库约定.md：按工序分库 db_<工序号>_<工序名>.db；report_index + SN_<条码safe>_<hash16> 明细表；工序注册限制英文/数字；修改序号/名称时重命名库；上报路由规则（待实现）。
- 新增 design_data/DatabaseConventions/产品流转数据库约定.md：ProductFlow.db；product_overview（条码/型号/板状态/当前工序/设备/时间/flow_table）+ 每产品 F_<条码safe>_<hash16> 流转表（id/板状态/所在工序/下站工序/线体/设备/时间）。
- manual.md 增加“数据库约定（补充）”引用小节。
- 当前代码尚未完全按上述约定实现；文档作为后续实现依据。

- **关联**：[ADR-029](architecture.md#adr-029)

### ADR-031：按工序分测试库 + ProductFlow 首版实现（2026-11-18）

- 用户确认“改工序名为英文数字 + 产品流转放产品查询页 tab”后开始实现。
- config/engine：新增 report_db_path(step_no, step_name) → db_<工序>_<工序名>.db；product_flow_db_path() → ProductFlow.db；engine 增加 get_report_engine / get_product_flow_engine 及多库缓存。
- master_data.json 工序名改为 S1/S2/S3/S4；step_registration._validate_steps 限制工序名只能 [A-Za-z0-9]+。
- report_route.py：按 station 查 devices.step_no + steps.step_name，决定工序报告库；未注册设备回退 TestReport.db。
- report_details_store 支持传入 Engine；report_repo.insert_report/list_reports 支持 report_engine。
- upload_test_result_v1 上报写入对应工序库 + ProductFlow；unlock_workpiece 解锁写 ProductFlow（手动解锁）。
- product_flow_store.py：ProductFlow.db 总览表 + 每产品 F_<条码safe>_<hash16> 流转表。
- API 增加 report-index/details 的 step_no 参数；新增 flow-overview/flow-details；client 同步；产品查询页新增“产品流转”tab。
- seed 演示数据路由到注册设备对应工序，生成 db_1_S1.db / db_2_S2.db / db_3_S3.db 与 ProductFlow.db；保留 TestReport.db 兼容旧数据。
- 验证：全量 152 passed；API/UI 重启；data/ 运行时库 = mes.db + ProductFlow.db + 3 个工序库 + TestReport.db（兼容）。

- **关联**：[ADR-030](architecture.md#adr-030)

### ADR-032：ProductFlow 时间与状态规范化（2026-11-18）

- changed_at/updated_at 统一为业务时区 `YYYY-MM-DD HH:MM:SS`（normalize_time）。
- product_overview.current_device 改名 last_report_device；新增 last_report_note。每产品流转表新增 note；上报写 test pass/test fail，解锁写 note 或 unlock。
- 状态枚举改英文：normal / lock / final（当前上报按 PASS/FAIL 写 normal/lock；解锁写 normal）。
- 产品查询页删除“解锁记录”tab；产品流转总览显示最后一次上报设备/备注。
- 工序解绑表单新增“切换到的工序”选择（来自 /api/ui/product/step-options）和上报备注；unlock API/services/usecase/client 传 target_step/note，并写 ProductFlow。
- 验证：ProductFlow 列与格式正确；全量 152 passed；重启服务。

- **关联**：[ADR-031](architecture.md#adr-031)

### ADR-033：产品查询筛选/测试履历分工序（2026-11-18）

- 工序解绑去掉“解绑原因”，只保留目标工序 + 备注；备注同时作为 reason 与流转 note，写入 ProductFlow。
- 查询条件改为全部下拉框：产品型号、工件码、工件状态、板状态、当前工序、测试工序；选项来自两个总览表（product_overview + report_index 跨工序库）。
- /api/ui/product/workpieces 增加 board_status/current_step/test_step 筛选；product_query_repo.list_workpieces 合并 workpieces + test_reports + ProductFlow 总览字段后过滤。
- 测试履历按工序拆 tab：测试履历-1/2/3/4 + 产品流转 + 工序解绑；每个测试履历 tab 只显示对应工序库的 report_index/details。
- AppTest：0 异常；selectbox 7 个；tabs 6 个；全量 152 passed。

- **关联**：[ADR-032](architecture.md#adr-032)

### ADR-034：测试履历独立成页面块（2026-11-18）

- 用户要求：测试履历与查询结果同级，不再作为追溯详情内的 tab；详情 tab 去掉按工序拆分的测试履历，只保留产品流转/工序解绑。
- 查询条件合并“当前工序/测试工序”为一个“工序”下拉框（内部仍传 test_step）。
- 页面结构：查询条件 → 查询结果 → 测试履历（独立 container，按工序 S1/S2/S3/S4 分 tab） → 追溯详情（基本信息/工艺路线 + 产品流转/工序解绑 tabs）。
- AppTest：0 异常；selectbox 6 个；subheaders 顺序正确；tabs 含测试履历工序 tab 与详情 tab；全量 152 passed。

- **关联**：[ADR-033](architecture.md#adr-033)

### ADR-035：详情区精简（2026-11-18）

- 产品流转总览只展示当前条码对应的一行（frame.head(1)），不做行选择。
- 板状态筛选固定为 全部/normal/lock/final（支持 final）。
- 追溯详情区去掉 tabs，按顺序直接展示：产品流转 → 工序解绑。
- 去掉追溯详情 basic metrics（状态/产品型号/当前设备/锁定）与锁定原因提示；保留工艺路线折叠区。
- AppTest：0 异常；subheaders 查询条件/查询结果/测试履历/追溯详情；markdown 包含产品流转/工序解绑；全量 152 passed。

- **关联**：[ADR-034](architecture.md#adr-034)

### ADR-036：查询条件与流转表头调整（2026-11-18）

- 查询条件顺序改为：工件码 → 产品型号 → 设备 → 查询按钮（第一行末尾），下一行：板状态 → 工序。
- 去掉“工件状态”，改为“设备”筛选；后端 /api/ui/product/workpieces 与 product_query_repo.list_workpieces 增加 device 参数，按 current_device/last_report_device 过滤。
- product_overview 展示表头改为数据库字段名（id/barcode/componentcode/board_status/current_step/last_report_device/last_report_note/updated_at）。
- AppTest：0 异常；全量 152 passed。

- **关联**：[ADR-035](architecture.md#adr-035)

### ADR-037：查询结果改用产品流转总览（2026-11-18）

- 产品查询页“查询结果”数据源从 workpieces/test_reports 混合列表改为 ProductFlow.db 的 product_overview。
- /api/ui/product/flow-overview 支持 barcode/componentcode/device/board_status/current_step 过滤；client.product_flow_overview 同步。
- 查询结果列名直接用数据库字段名：id/barcode/componentcode/board_status/current_step/last_report_device/last_report_note/updated_at；点行取 barcode 作为 pq_current。
- 查询条件选项也从 product_overview 派生（条码=barcode，型号=componentcode，设备=last_report_device）。
- AppTest：0 异常；全量 152 passed。

- **关联**：[ADR-036](architecture.md#adr-036)

### ADR-038：看板设置显示 + 统计时间区间（2026-11-18）

- 测试数据看板两个同级折叠容器：监控设备管理 / 设置显示。
- 设置显示：先调整卡片顺序，后“调整统计时间区间”。
- 时间控件使用可空文本输入框，格式 YYYY-MM-DD HH:MM:SS（Streamlit 原生 datetime_input 不支持秒与空值+该格式）。
- 三个并行控件：开始时间 / 结束时间 / 清空；下方单独“查询”按钮。只有点击查询才把区间写入 applied_stat_range 并影响卡片统计。
- 默认规则：结束空→当前时间；开始空→结束当天 0 点；两者空→今天 0 点到现在。清空按钮把开始/结束都置空。
- 统计按生效区间扫描各工序测试库 report_index（按 station + testexecutetime 过滤），计算 total/first_pass/retest_pass/fail 并覆盖卡片统计值。
- 验证：全量 152 passed；AppTest 看板 0 异常；默认区间输出 2026-11-18 00:00:00 ~ now。

- **关联**：[ADR-037](architecture.md#adr-037)

### ADR-039：测试数据看板新增工序页 tab（2026-11-18）

- 设备页同级新增“工序页” tab；按监控设备列表 config/device_config.json 的 step_no/step_name 分组统计。
- 工序页显示：工序号、工序名、监控设备数、测试总数、一次通过、复测通过、失败、合格率；并画分组柱状图。
- 统计值复用“设置显示”里的生效时间区间 applied_stat_range：有区间时按各工序库 report_index 统计，无区间时读 station_summary 汇总。
- 工序页用 @st.fragment(run_every=1000) 局部刷新。
- AppTest 0 异常；全量 152 passed；UI 重启。

- **关联**：[ADR-038](architecture.md#adr-038)

## 21. ProductFlow.db product_overview 增加 traycode（2026-11-19）
- `product_overview` 在 `componentcode` 后新增 `traycode TEXT NOT NULL DEFAULT ''`（逻辑顺序；SQLite 已有库 ALTER 只能追加到末尾，物理位置在最后，页面/查询按代码控制的顺序显示）。
- 写入来源：V1.3 上报 `traycode` 可选字段（schemas_v1.py 默认 ''），`upload_test_result_v1.execute()` 透传给 `product_flow_store.upsert_flow(traycode=...)`；seed 演示数据按产品生成 `T{2000+i:05d}`。
- 解锁场景 `traycode=None` → UPDATE 不覆盖已有值；新建行写 ''。
- 查询链路全加 `traycode` 参数：`product_flow_store.list_overview` → API `/api/ui/product/flow-overview` → `ui.client.product_flow_overview` → 产品查询页面（`pq_traycode` 下拉，第一行 4 列：barcode/componentcode/traycode/board_status；结果表与追溯总览表均在 componentcode 后显示 traycode）。
- 主库 `test_reports` 不加该列（避免改动主表 schema），只在 flow 库留档。

## 22. 产品流转约定文档同步（2026-11-19）
- `design_data/DatabaseConventions/产品流转数据库约定.md`：总览表字段补 `traycode`/`last_report_note`，修正旧名 `current_device`→`last_report_device`，板状态枚举改为英文 normal/lock/final（与代码一致），去掉“尚未实现”过时说明。
- README：ProductFlow.db 表说明补 traycode；V1.3 请求体 JSON 示例加 `traycode` 字段。

### ADR-040：report_index 列按上传 JSON 顺序重排，result/traycode 入库，details 保持 hash 表（2026-11-19）
- 决策：各工序测试库 `db_<工序号>.db` 的 `report_index` 列顺序按 `design_data/MesFormat/mesUploadTestDataFormat.json` 的键顺序排列：`id, linecode, station, componentcode, traycode, barcode, programname, programversion, testexecutetime, testlongtime, result, isfinalreport, details_table`。
- 变更：新增 `traycode`、`result` 两列；移除派生列 `failed_step`（失败判定统一用顶层 `result`，从 V1.3 请求原样落库）。列顺序决定 UI 展示列顺序。
- 向后兼容：检测到旧 schema（无 `result` 列）时 `ensure_overview_table` 自动重建 `report_index`（演示数据可重新 seed）；旧行不迁移。
- `details` 仍按 hash 方式：每产品一张 `SN_<条码safe>_<hash16>` 表，`details_table` 指向该表；明细表结构不变。
- 接口文档 V1.3 同步：3.1 结构 / 3.2 顶层字段 / 3.4 示例统一按 JSON 键顺序；`traycode` 标记为上报可选字段。
- UI 同步：产品查询“测试报告总览”按新列顺序中文表头展示；看板时间区间统计改用 `result` 判定失败。
- 关联：ADR-028 / ADR-030 / ADR-038
- **关联**：[ADR-028](architecture.md#adr-028)，[ADR-030](architecture.md#adr-030)，[ADR-038](architecture.md#adr-038)

## 23. 测试报告库 report_index 按 JSON 顺序重建（2026-11-19）
- `design_data/MesFormat/mesUploadTestDataFormat.json` 顶层字段顺序：linecode/station/componentcode/traycode/barcode/programname/programversion/testexecutetime/testlongtime/result/details/isfinalreport。
- `report_index` 物理列顺序改为：id/linecode/station/componentcode/traycode/barcode/programname/programversion/testexecutetime/testlongtime/result/isfinalreport/failed_step/details_table（新增 traycode、result；系统列 id 在前，failed_step/details_table 内部列在后）。
- `report_details_store.py`：`OVERVIEW_COLUMNS`、CREATE DDL、insert_overview SQL 全部按新顺序；`ensure_overview_table()` 增加自动迁移：检测列不符时 ALTER RENAME 旧表 → 按新 DDL 重建 → SELECT 迁移（缺失列填空串）→ DROP 旧表。
- 主库 `test_reports` 无 traycode 列：upload/seed 写主表时须剔除 traycode，仅 insert_overview 写该列。
- 演示数据 seed：`report` dict 带 traycode/result；新增逻辑在重建前清空每个 `db_*.db` 分库的 report_index 与 SN_ 明细表（原 drop_all_tables() 只清默认 TestReport.db，导致旧行残留）。
- UI 产品查询的测试履历总览表改用数据库字段名、按 JSON 顺序显示（去掉中文表头）。
- 文档同步：MES上传接口文档.md（3.1/3.2/3.4 按 JSON 顺序加 traycode）、测试报告数据库约定.md 总览表字段表、README 请求体示例。

## 24. 载具注册页面与 trays 主数据（2026-11-19）
- 新增主数据 `trays`（载具/托盘）：字段 traycode(PK)/tray_name/capacity(载荷数量=一个托盘放几块板)/enabled/remark；定义在 `engine.py`，读写在 `master_data_repo.list_trays/replace_trays` 并纳入 `snapshot()`，master API(`/api/ui/master/{key}`) 与 `_common.MASTER_KEYS` 同步加 key。
- 新页面 `src/py_server/ui/pages/tray_registration.py`：导航注册在设备注册下方（url_path=trays）；风格同设备注册的设备管理（外层 container + 新增载具 expander + form border=False + data_editor 列表带删除列 + 左下保存按钮 + 删除确认 dialog）。
- 演示数据：master_data.json 加 trays（T02001~T02003），master_seed.seed_master_data 整体替换写入。
