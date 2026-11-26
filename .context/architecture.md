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

## 25. 产品型号-载具分配（2026-11-20）
- 新增主数据 `product_trays`：`product_model + traycode`（唯一约束），定义在 engine.py，读写 repo/master API/_common.MASTER_KEYS/master_seed 全链路接入；演示数据 P-1001→T02001/T02002，P-1002→T02003。
- 产品型号注册页新增区块5“为型号分配载具”：复用上方已选产品型号，多选启用载具（显示 载具码-载具名（型号）），保存写 product_trays；页面生产版+app_pages 镜像同步，测试区块断言更新为 5 个。

## 26. 产品型号注册拆分为两页（2026-11-20）
- 原 product_management.py 拆成两页：①`型号注册页`（product_management.py，url_path=products）保留区块1新增产品型号+区块2产品型号列表；②`工艺配置页`（process_config.py，url_path=process_config）含区块3产品型号工序流程+区块4为型号分配设备+区块5为型号分配载具，自带"选择产品型号"下拉框。
- 生产版(src/py_server/ui/pages/)与测试镜像(app_pages/)都同步拆分；根 streamlit_app.py 与生产 streamlit_app.py 导航都注册了 process_config 页（测试 AppTest 需 switch_page 能找到）。
- 测试同步：test_product_management.py 拆成2个渲染测试 + 新增 _open_process_page helper，route/device 测试全部改用 process 页；共 153 passed。

## 27. 组件注册表单改造（2026-11-20）
- 组件注册页（原产品型号注册）新增表单改为4字段：第一行 组件名称+组件号，第二行 备注+启用(文本下拉是/否)，第三行 添加组件按钮；去掉了测试程序名/测试程序路径。
- 组件列表列改为：组件号(disabled)/组件名称/启用(CheckboxColumn)/备注；主库 products 表加 enabled 列（Integer default 1），master_data.json 演示数据同步；数据库已重建。
- 注意：工艺配置页仍沿用 product_model/product_name 作为底层字段；启用字段影响后续工艺配置可选性（当前未过滤，后续可按需加）。

## 28. 程序下发页重构 + 工艺配置页扩展（2026-11-20）
- 程序下发页改为3块：①新增（程序名/版本/版本说明/文件/启用，去掉所属工序，风格同组件注册三行布局）②当前运行程序（每程序名一行 data_editor：版本/版本说明/启用/删除列；删除=删整个程序及型号关联）③历史程序（st.dataframe row selection 勾选程序→显示该程序所有版本，新→老，来自 program_versions；历史表可改版本说明/删版本）。
- 型号关联+设备读写记录从程序页移到工艺配置页（区块6/7）。
- 主库 programs 加 enabled 列（step_no 保留兼容但新增不再填写）；数据库已重建。
- 两套页面(src/py_server/ui/pages + app_pages)同步重写；test_program_ui.py 整体重写覆盖新UI（AppTest 用 session_state 设置 dataframe selection / data_editor edited_rows，不支持 set_value/select_row）。test_product_management.py 工艺配置区块断言更新为5块。151 passed。

## 29. 程序下发：勾选驱动历史 + hash/url（2026-11-20）
- 当前运行程序表加列：下发(CheckboxColumn)/程序名/版本/版本说明/SHA256/下载地址/启用/删除；勾选“下发”列后立即在下方历史程序显示该程序的所有版本（用 _sync_program_selection 每次 rerun 从 data_editor 当前值同步 program_selected_name，同时保留 on_change 回调 _on_program_editor_change 用于交互即时响应）。
- program_versions 表加 sha256/download_url 列（每个版本独立），master_data.json/engine/seed 同步；_upsert_version_description 增加 sha256/url 参数。切换版本后点保存，对应记录的 hash/下载地址/说明按版本记录刷新。
- 历史程序表去掉内置程序选择 dataframe，完全由上方勾选驱动；每行 hash/下载地址取各自版本记录。数据库已重建。151 passed。

## 30. 程序页勾选改为产品查询式 + 版本切换即时同步（2026-11-20）
- 当前运行程序列表改为 `st.dataframe(on_select="rerun", selection_mode="single-row", key="program_list_select")`，与产品查询一致；勾选行→program_selected_name→下方历史程序显示该程序版本。去掉了 data_editor 的"下发"勾选列/回调方案（data_editor 不支持行选择、on_change 回调在测试中不触发）。
- 选中程序后显示编辑区：版本 selectbox(edit_program_version)/SHA256 只读/下载地址/版本说明/启用/保存/删除；版本切换触发 rerun，SHA256/下载地址从 program_versions 对应版本记录即时刷新（_version_meta）。
- 当前运行程序 dataframe 列：程序名/版本/版本说明/SHA256/下载地址/启用。151 passed。

## 31. 设备注册：删所属工序、加设备型号（2026-11-20）
- 设备注册页列改为：设备编号/设备名称/设备型号/所属线体/启用/备注（去掉所属工序）；新增表单第一行4个文本框（编号/名称/型号/线体），第二行备注+启用下拉，第三行按钮；_validate_devices 不再校验 step_no，设备型号必填。
- engine.devices 加 device_model 列；step_no 列保留（工艺配置页仍按设备 step_no 过滤候选设备），新增设备不再写 step_no（为空），DB 已重建。
- master_data.json + 两套 _mock_program_data.py 初始设备都补 device_model；_mock_program_data.initialize_program_state 里 device["step_no"] 改成 .get() 以免新增设备缺列时报错。150 passed。

## 32. 全工程去掉线体（单线运行，2026-11-20）
- 删除 `lines` 主数据表/API/repo/master_seed/_common.KEYS/master_data.json/两套 _mock_program_data 的 lines 初始化；`config/device_config.json` 去 line_id/line_name。
- `devices` 去 line_id（列改为 device_id/device_name/device_model/step_no/enabled/remark）；设备注册页删「线体管理」整块、所属线体列/表单，页面重写为「设备管理 + 设备列表」两块。
- V1.3 上报彻底去 `linecode`：schemas_v1、upload_test_result_v1、engine.test_reports、seed 模板/报告 dict、report_details_store 的 report_index（DDL+迁移+insert SQL）、page_product_query 显示、MES上传接口文档、mesUploadTestDataFormat.json、README、test_upload_v1 全同步。
- ProductFlow 流转表 F_ 去 line_id 列；product_flow_store.upsert_flow 签名去 line_id；unlock/upload 调用去该参数；产品流转约定文档同步。
- 工艺配置「为型号分配设备」重写：去掉选择线体+按线体过滤，候选=全部启用设备，multiselect key 改为 assign_<产品>_<工序>；测试断言同步。
- 看板：去掉产线筛选、所属线体列、_line_step_names→_step_names，config 里不再存 line_id/line_name。
- 数据库全部删除重建（seed --reset --demo）。139 passed。

## 33. 工艺配置重构完成（2026-11-20）
- 新表 `processes`（工艺号/名称/启用/备注/来源工艺号）、`process_routes`、`process_step_resources`（每工序：program_name / device_models 逗号分隔 / tray_models 逗号分隔，按**型号**而非实例）；删 `product_routes/product_step_devices/product_trays/program_components`。
- `products` 加 `process_code`（一组件一工艺）；`product_query_repo.product_route` 改为按组件 process_code 查 process_routes。
- 工艺配置页重写三块：①新增工艺（空白/从已有工艺**深拷贝**派生，source_process_code 仅溯源）②工艺列表（st.dataframe 行选择，含来源工艺/引用组件数）③工艺详情（工序路线编辑器 + 工序资源表：程序下拉/设备型号 MultiselectColumn/载具型号 MultiselectColumn）；被组件引用的工艺禁止删除；删掉设备读写记录区块。
- 组件注册页加「绑定工艺」列/表单/校验；程序注册页清掉 program_components 残留；两套 mock data 换用新 key。
- 新文档 `design_data/DatabaseConventions/工艺配置数据库约定.md`；数据库全量重建；127 passed。

## 34. 工艺绑定组件方向反转 + 删除弹框（2026-11-20）
- 组件注册页彻底去掉「绑定工艺」列/表单/校验；products 表删 process_code 列。
- 改为工艺侧绑定：`processes` 加 `component_no`（一工艺绑一个组件号），工艺配置页新增表单可选、工艺列表加「绑定组件」SelectboxColumn 可改；`product_query_repo.product_route` 改为按 `processes.component_no == product_model` 反查工艺路线。
- 工艺删除：不再因「被组件引用」拦截；改为 @st.dialog 确认弹框（与设备/组件列表一致），弹框确认后一并删 processes/process_routes/process_step_resources。
- 程序注册列表最后一列删除按钮也改为 @st.dialog 确认弹框（cancel_delete_program / confirm_delete_program），删除时同步清 program_versions。
- app_pages 镜像改用「保留 render_page 函数包装 + 末尾 render_page()」的生成方式，避免模块级 dialog/回调定义顺序导致 NameError；app_pages/program.py 里遗留的 `from .. import client` 用 _StubClient 替代（新 UI 不调用）。
- 数据库全量重建；文档《工艺配置数据库约定》/README 同步；127 passed。

## 35. 工位操作台（2026-11-21）
- 产品型号通过 `processes.component_no` 倒查唯一启用工艺；工序路线首站作为入站 `current_step`，`tray_models` 取工艺资源中允许的载具型号。
- 载具载荷来自 `trays.capacity`；入站要求条码数量恰好等于载荷数量，并同时写 `workpieces` 与 ProductFlow `product_overview/flow_table`。
- 托盘解绑按 `traycode` 批量清空 `product_overview.traycode`，并为每个产品追加 `device=托盘解绑` 的流转留痕。
- 新接口：`GET /api/ui/workbench/recipe`、`POST /api/ui/workbench/inbound`、`POST /api/ui/workbench/tray-unbind`；页面入口 `ui/page_workbench.py`，导航 `url_path=workbench`。

## 36. 工位操作台标签页（2026-11-21）
- 工位操作台的三个操作改为 `st.tabs`：手动入站 / 托盘解绑 / 产品解锁，避免三个大区块纵向堆叠。
- 手动入站条码位按两列排布；工艺路线放入折叠区；“操作员”统一使用侧边栏 `mes_operator`，页面内不再重复输入。
- 产品解锁新增“解锁后所在工序”选择，默认“保持当前工序”；选中具体工序时传给 `unlock_workpiece(target_step=...)`，流转库按该工序落点。

## 37. 工位操作台扫码交互（2026-11-21）
- 手动入站改为单一常驻扫码框：首扫载具，后续连续扫产品条码；每扫一个自动推进计数，达到载具载荷后自动调用入站接口，不再要求点击按钮。
- 三个标签页改为 `on_change="rerun" + .open` 懒加载，避免隐藏页脚本和接口调用互相干扰。
- Streamlit 无原生 autofocus，使用作用域 `st.html` JS 按 `.st-key-workbench_*_scan_*` 保持当前扫码框焦点；每个扫码状态变化带唯一 marker，确保脚本重新执行。
- 产品解锁只要求扫描产品条码，锁定校验由页面检查；解锁原因自动写为“工位操作台扫码解锁”，confirmed=True，仍保留操作员与解锁后工序选择。

## 38. 手动入站卡片式布局（2026-11-21）
- 载具输入框常驻并保留值；输入一个有效新载具才递增条码批次 token、清空上一批卡片，同一载具不会重复清空。
- 条码按载具载荷生成卡片，每行数量由数字输入框控制（1~4）。每条码独立启用勾选，默认开启。
- 条码内容保存在独立 value key，widget key 按 enabled/disabled/submitted 切换，确保真正禁用且不丢值。
- 进度只统计启用卡片中已填写的数量；所有启用卡片完成后自动调用入站接口，保留本批卡片与载具值，并将焦点移回载具输入框以便扫描下一载具。
- 后端入站规则由“条码数必须等于载荷”改为“不得多于载荷”，允许禁用部分载荷。

## 39. 入线状态页面与删除边界（2026-11-21）
- 新增 `src/py_server/ui/tag_page.py`，导航 `url_path=tag_page`，以只读列表展示产品条码、型号、载具、状态、当前工序、最近设备/说明和更新时间，不提供启用列。
- 列表仅提供行内“删除”按钮和二次确认弹窗；只读角色不显示删除入口。删除调用 `DELETE /api/ui/product/flow?barcode=...`，移除 `product_overview` 当前状态和该产品的 ProductFlow 历史表，不删除 `workpieces` 档案或测试报告。
- 行按钮只携带行号，因此页面每次渲染都把当前展示顺序的条码暂存到 `tag_page_display_barcodes`，回调再按行号映射到条码，避免列表排序后误删。
- 工位操作台与入线状态专项测试：8 passed；真实 Streamlit 页面 `/tag_page` 已验证可加载。

## 40. 入线状态并入工位操作台（2026-11-21）
- 移除独立导航 `url_path=tag_page`，工位操作台改为四个标签：手动入站、入线状态、托盘解绑、产品解锁。
- `ui/tag_page.py` 改为提供 `render_content(read_only=...)`，由 `page_workbench.py` 在“入线状态”标签中调用；标题、闪消息和只读提示统一由工位操作台管理。
- 入线状态列表仍只允许删除，不显示启用列；删除确认与接口行为不变。
- 调整后工位操作台专项测试 8 passed，运行页面已确认左侧无独立入口且四标签正常显示。

## 41. 入线状态、LOCK/END 与托盘自动解绑（2026-11-21）
- V1.3 上报按 `result + isfinalreport` 映射板状态：FAIL → `lock`，PASS 且最终报告 → `final`；下一站相应写 `LOCK` / `END`。
- `product_flow_store.upsert_flow` 在任一产品写入 `lock/final` 时，对当前有效 `traycode` 执行整盘自动解绑，同时给盘内每个产品追加 `device=托盘自动解绑` 的流转记录。
- 入线状态列表只显示仍具有 `traycode` 的当前绑定产品，以及所有 `lock/final` 终态产品；界面状态显示为 `NORMAL/LOCK/END`，并增加“托盘状态”（已绑定/已解绑）。
- 对规则上线前遗留的 `LOCK` 托盘 `T02010` 已执行一次性自动解绑清理。
- 工位操作台 + V1.3 上报定向测试：20 passed；8000/8501 已重启并验证页面。

## 42. 入线状态仅保留在制托盘（2026-11-21）
- 入线状态列表只筛选 `traycode` 非空的产品，不再展示已自动解绑的 LOCK/END 产品。
- 标题改为“正在流转的托盘”，移除冗余“托盘状态（已绑定/已解绑）”列；无在制托盘时显示“暂无正在流转的托盘”。
- 自动解绑规则不变：任一产品进入 LOCK/END 后整盘解绑，解绑后立即从该列表消失。
- 工位操作台专项测试 12 passed；运行页面已确认空态与新标题。

## 43. 工位入站按产品型号 + 工序校验托盘（2026-11-21）
- 手动入站第一行改为：产品型号 / 工序 / 每行条码数量；工序下拉位于产品型号后，选中型号后才加载该产品启用工艺的工序。
- `workbench_recipe` 的 `steps/routes` 增加每个工序独立的 `tray_models`；UI 只列出配置了载具型号的工序。
- `POST /api/ui/workbench/inbound` 新增必填 `step_no`；服务端用“产品型号 → 唯一工艺 → 指定工序资源”的载具型号白名单校验实际托盘型号，并按所选工序写入 `current_step` 和该工序 `success_next_step`。
- 切换产品会清空工序和扫码批次；切换工序会清空托盘与条码批次，避免旧批次继续使用。
- 工位操作台专项测试 13 passed；运行页面已验证产品型号后方出现工序下拉。

## 44. 入线状态按托盘聚合（2026-11-21）
- UI 将 `traycode` 相同的产品聚合为一行：条码数量、产品条码、型号、状态、工序、设备/说明均去重合并，更新时间取最大值。
- 条码单元格用 `、` 拼接同一托盘内的全部产品条码，避免同一托盘重复占多行。
- 行内删除改为整盘删除；新增 `DELETE /api/ui/product/tray-flow?traycode=...`，在同一事务中删除该托盘全部 `product_overview` 行和各自流转表，保留工件档案与测试报告。
- 工位操作台专项测试 13 passed；8000/8501 服务重启且 OpenAPI 已验证新接口。

## 45. 托盘操作与产品查询结果隔离（2026-11-23）
- 托盘手动解绑与 LOCK/END 自动解绑只清除 `product_overview.traycode`，不再向产品流转明细写“托盘解绑/托盘自动解绑”事件，也不覆盖 `last_report_device` / `last_report_note`。
- 产品查询结果因此只保留测试结果与“手动解锁”等产品解锁事件；托盘操作只在工位操作台的入线状态中表现为托盘消失。
- 新增 `POST /api/ui/product/repair-tray-report-fields`，用于清理历史数据中被托盘动作覆盖的字段和流转明细；本次已修复 10 条历史记录。
- 工位操作台专项测试 13 passed；运行接口确认产品查询中托盘相关记录数为 0。

## 46. 产品查询托盘取最后测试上报（2026-11-23）
- 产品查询结果中的 `traycode` 不再取当前工位绑定，改由 `/api/ui/product/report-traycodes` 按每个条码返回最后测试上报的托盘码。
- 查询条件中的托盘下拉选项与筛选也按测试上报托盘码处理；工位操作台“正在流转的托盘”仍使用当前绑定关系，两者互不混淆。
- 新增产品查询展示回归测试；全量测试 143 passed。

## 47. 产品查询按产品型号 + 测试工序直查分库（2026-11-23）
- 产品查询页新增“测试报告筛选（按工序库）”，支持产品型号、测试工序、条码、托盘、结果筛选。
- 测试工序选项由 `db_*.db` 和 steps 主数据生成；选择工序后通过 `/api/ui/product/report-query` 直接读取对应 `db_<工序>.db` 的 `report_index`，结果增加 `step_no` 与 `source_db` 列。
- 原有产品流转查询与追溯/解绑保持不变；全量测试 144 passed。

## 48. 产品查询标签页化与报告行详情（2026-11-23）
- 产品查询页改为两个标签：产品流转查询、测试报告查询；所有筛选控件与结果留在同一页面。
- 测试报告查询结果首列为 barcode，并启用 `on_select="single-row"`；选中一行后在下方显示该报告总览字段和对应 details，交互方式与原产品查询的测试履历一致。
- 报告详情读取时使用结果行携带的 `step_no`，因此明细仍从对应 `db_<工序>.db` 查找。
- 全量测试 144 passed。

## 49. 测试报告勾选详情修复（2026-11-23）
- 报告结果表勾选后先用本次 `event.selection` 直接渲染详情，并在 key 变化时 `st.rerun()`；下次 rerun 从 `pq_report_current` 恢复详情，避免 Streamlit 表格勾选状态在重跑时未及时可读导致详情消失。
- 新增回归测试覆盖选中后显示报告总览和 details；全量测试 144 passed。

## 50. 测试报告查询条件对齐产品流转查询（2026-11-23）
- 测试报告查询页的筛选排版改为与产品流转查询一致：两行三列，英文标签 `barcode` / `componentcode` / `traycode` / `board_status` / `current_step` / `last_report_device`。
- 额外增加 `step_no` 选择框用于指定要查询的工序库，如 `db_1.db`；另保留英文 `result` 筛选。
- 后端报告查询支持 `board_status` / `current_step` / `last_report_device` 过滤，其中 board_status 由测试 result/isfinalreport 映射。
- 全量测试 144 passed。

## 51. 架构决策：测试报告跨库查询逻辑归入 repositories/report_query_store.py
2026-11-23 整理后端时确认：`api/routers/product_query.py` 不应负责 `db_*.db` 引擎扫描、report_index 明细拼接、筛选、latest traycode 聚合。这些逻辑已统一到 `repositories/report_query_store.py`，路由只保留参数声明和 service/repository 调用。新增结构测试 `test_report_query_orchestration_lives_in_repository` 防止路由层回退到内联 SQL/扫描。

## 52. 架构决策：UI guards/sidebar 薄封装已删除
`src/py_server/ui/guards.py` 和 `sidebar.py` 仅 re-export `common.can_edit` / `common.render_sidebar`，仓库内无使用点。整理后端时删除这两个空壳，权限与侧边栏统一由 `ui/common.py` 提供；测试 `test_no_unused_ui_thin_wrappers` 防止回退。

## 53. 架构决策：删除旧 app_pages 原型前端与过时 UI 测试
2026-11-23 清理多余文件：仓库根目录 `app_pages/` 与 `streamlit_app.py` 是被 `src/py_server/ui/pages/` + `src/py_server/streamlit_app.py` 完全替代的旧原型前端（注释中明确“暂未连接 FastAPI”）。依赖它的 `tests/test_device_registration.py`、`test_product_management.py`、`test_program_ui.py`、`test_step_registration.py` 断言旧原型字段/布局，与新页面不一致，已随旧前端一并删除；剩余 AppTest 覆盖新入口与新 UI 页面。清理同时删除了运行期 `logs/`、`.pytest_cache/` 与大部分 `.pytest_tmp*/`，但部分历史临时目录因 Windows 权限（Access is denied）无法删除，已在 .gitignore 中忽略，不影响项目运行。

## 54. 架构决策：测试报告数据库从按工序分库改为单一 TestReport.db
2026-11-23 把 db_1.db/db_2.db/db_3.db 合并为一个 data/TestReport.db。合并时保留 30 条 report_index（每工序 10 条）和 10 张按条码命名的 SN_ 明细表；新增 report_index.step_no 字段保存原工序归属（按 station TEST-01/02/03 回填 1/2/3）。代码调整：config.report_db_path() 与 engine.get_report_engine() 统一返回 details_db_path / details engine；report_query_store 不再扫描 db_*.db；seed/upload 写 overview 时显式写 step_no；product_query_repo、page_dashboard、report_details_store 同步改为单库与 step_no 过滤。验证：全量测试 113 passed；API 查询 product=L120201091&step_no=1 返回 1 行，source_db=TestReport.db，step_no=1。

## 55. 架构决策：单库内按工序分总览表/明细表
用户明确要求：不同工序使用不同总览 table，只是数据都放在同一个数据库。实现：`report_index_1`、`report_index_2`、`report_index_3` 等每工序一张总览表；SN 明细表名也加工序前缀，如 `SN_1_<barcode>_<hash16>`，hash 由 `step_no:barcode` 计算，确保同一条码不同工序指向不同 details。`report_details_store` 统一负责表名生成与访问；`list_overview(step_no=...)` 只读对应工序表，`query_reports(step_no=...)` 不再依赖单张大表字段过滤。重建演示数据后验证 step_no=1 报告详情只有 S1_01~S1_10，全量测试 113 passed。

## 56. 架构决策：入站状态删除只释放当前占用，不删除测试数据
2026-11-23：删除 ProductFlow 入站状态时，同时删除 mes.db.workpieces 中无测试数据的占位工件；如果条码已有 test_results 或任一 report_index_* 报告，则保留工件档案/测试数据，不删除测试报告。手动入站占用判定改为只查 ProductFlow 当前总览，不再用 workpieces 是否存在判断占用，因为 workpieces 也会由测试上报产生。验证：删除 SN202611180001 入站状态后报告数 before=3、after=3，delete status=200；全量测试 115 passed。

## 57. 架构决策：注册页统一骨架与跨层常量
2026-11-24：设备/载具/工序/组件四类注册页统一复用 `ui/pages/registry_helpers.py` 与 `ui/pages/constants.py`，共享空值清洗、权限判断、启用值转换、DataFrame 生成、删除 pending state、保存提示等逻辑。新增 `src/py_server/constants.py` 集中跨层业务常量（PASS/FAIL、normal/lock/final、LOCK/END、true/false、全部、变量类型、权限等），application/repository/ui 逐步替换散落字符串。批量补全 src/py_server 下所有函数/类 docstring（AST 检查缺失数为 0）。新增 docs/CODEBASE_GUIDE.md，详细说明框架、分层、关键函数、数据库、设计模式、关键流程、魔术值清理与注释规范。

## 58. 架构决策：删除旧兼容接口与旧测试语义
2026-11-24：按用户要求删除全部旧兼容。删除 /api/test-result 单条上报接口与 TestResultIn schema；删除只测旧接口的测试，保留业务规则测试并迁移到 V1.3 helper；examples/device_client.py 改为 V1.3 整单上报；删除 config.report_db_path 兼容别名、db.py 原始 sqlite 连接兼容函数、ui/client.py 未使用 _FALLBACK、repositories/base.py 旧 _tx 别名；更新 README/CODEBASE_GUIDE 移除旧单条上报描述。V1.3 内部单条上报改为用 TestItem 作为测试项、用解析后的 ISO 时间作为 tested_at、可信性改用设备 /api/program/status 指纹。全量测试 110 passed。

- 产品流转当前态与历史分离：当前态存 `product_overview`，历史存每产品 `F_<barcode>_<hash>` 表。托盘解绑写历史并删除当前态，允许重新入站。

- FastAPI 路由按调用方分目录：routers/device、routers/ui、routers/common；旧顶层路由文件仅 re-export，避免外部 import 中断。
- `active_products` 是 mes.db 中当前在制产品表；ProductFlow.db 继续维护 product_overview 与每产品历史表。

## 59. 架构决策：domain 只保留纯且稳定的业务规则
2026-11-25：明确 domain 层不是万能校验层，只表达不依赖 FastAPI、Streamlit、SQLAlchemy、sqlite3、配置文件或数据库的稳定业务不变量；当前保留程序可信性、联锁放行、工件状态机三块。请求头校验放 API/Pydantic schema；设备 SN 是否注册、设备是否启用、载具占用、设备使用次数超限等依赖外部状态的流程卡控放 services/application；request_id/UUID/测试项重复等幂等和查重放 application/repositories/数据库约束。代码相应调整：ProgramTrustPolicy.evaluate 增加 self_check_failed 入参；application/report_program_status.py 新增 evaluate_program_status 复用 domain 策略并保留既有中文文案；services.report_program_status 删除重复判定；services.manual_inbound 的托盘占用和条码重复入站改为以 mes.db.active_products 为准。验证：全量 109 passed。

## 60. 架构决策：MES 业务术语与 UI 文案统一
2026-11-25：确认术语规范：业务对象统一称“工件”，输入/列表字段统一称“工件条码”，“产品”只用于产品型号语境；业务对象统一称“载具”，字段称“载具号”，UI 动作称“载具解绑”，不在使用“托盘”作为业务名（旧接口/数据库字段兼容保留）；动作统一称“入站”，当前状态称“在制产品”，历史称“流转历史”，不再使用“入线状态”；载具层面用“绑定/解绑”，工件锁层面用“锁定/解锁”，设备启动判定用“放行”。本轮先改 Streamlit 用户可见文案，不改 API 路径、数据库字段、Python 变量名和测试断言；必要时同步文档术语说明。

## 61. UI 术语改名边界确认
第二轮确认：顶部导航“产品查询”保持不变；工位操作台页签改为“工件入站 / 在制产品 / 载具解绑 / 工件解锁”；产品查询内部页签改为“工件流转查询 / 测试报告查询”；“工序解绑”统一改为“工件解锁 / 执行解锁 / 解锁成功，工件可重新判定放行”；V1.3 协议字段（TestItem、TestResult、isfinalreport、SHA256 等）与 st.dialog/session_state 的 key 保留不改。

## 62. 架构决策：设备端 API 最小集
2026-11-25：确认设备端最小 API 集为：1) GET /health（连通性检查）；2) GET /api/program（拉取程序元数据）；3) GET /programs/{filename}（下载程序文件；与元数据合起来构成“下载测试程序”业务动作）；4) POST /api/program/status（上报程序版本/SHA256/自检结果，V1.3 无 SHA 字段，可信判定依赖此接口）；5) GET /api/interlock（放行判定/工站进站校验，不新增重复接口）；6) POST /api/v1/test-results（唯一 V1.3 整单测试报告上传入口，不恢复旧单条上报）；7) GET/POST /api/variable/{name}（开放性变量读写，设备之间交换 line_mode/target_qty/alarm_enabled 等状态）；8) 新增只读 GET /api/device/enable（查询设备开启状态，来自 config/device_config.json，设备端不直接读配置文件）。UI 接口不暴露给设备端。

## 63. 架构决策：设备配置移除 ip/port 字段
2026-11-25：确认 config/device_config.json 只是看板监控设备列表与设备开启开关配置，不是设备注册表；历史连接字段没有任何代码读取。最终决定彻底删除现有配置、看板保存代码和测试中的相关字段与断言，不保留过滤或兼容逻辑。新增监控设备时只写 device_id/name/step_no/step_name/enable；架构测试用字段白名单校验配置结构。

## 64. 架构决策：流式卡片状态模型
2026-11-25：确认流式卡片状态优先级为 disable > offline > testing > PASS/FAIL > idle。enable=false 显示禁用且不显示时间；设备心跳超时或无心跳显示离线且不显示时间；设备显式调用 POST /api/device/test-start 后显示测试中，时间从测试开始到现在；最近测试报告/测试结果在时间阈值内显示通过或失败并显示测试耗时，超过阈值显示空闲，时间从最近报告到现在。新增 POST /api/device/heartbeat 记录设备心跳，/health 仅表示 FastAPI 服务健康。心跳超时阈值与结果空闲阈值分别放 constants.py，推荐 30 秒与 300 秒。测试开始与测试结果继续使用 station_summary.status_since 作为状态起始时间，不新增列。

## 65. 架构决策：看板放大改为独立全屏页面
2026-11-25：右侧大抽屉放大体验不佳，改为独立 Streamlit 页面 /dashboard_focus。主看板“放大显示”使用 st.link_button 新标签页打开，URL 参数携带当前视图（devices/steps）与已生效统计区间（range_mode/start/end），放大页按参数恢复时间筛选并只渲染当前监控区域，不显示设备管理、时间设置和普通页签栏。放大页保留左侧导航并提供返回看板按钮；删除右侧 dialog 放大实现，避免两套方案并存。

## 66. 架构决策：取消看板放大显示功能
2026-11-25：用户评估右侧抽屉与独立全屏页面后决定不保留放大显示功能。已移除主看板“放大显示”按钮、/dashboard_focus 页面注册、render_focus、URL 参数透传逻辑及相关 imports；保留设备页/工序页的局部刷新、状态条刷新、图表按签名变化刷新等既有行为。

## 67. 架构决策：支持无载具产品流转
2026-11-25：确认无载具对象统一称“无载具工件 / 无载具入站 / 无载具工序”，不使用“没有托盘的产品”。载具能力按产品型号对应工艺的工序配置，process_step_resources 增加 tray_mode（必须载具 / 载具可选 / 不允许载具），默认必须载具保持兼容。无载具入站不要求扫描载具，active_products.traycode 与 product_overview.traycode 写空字符串，不创建虚拟载具号。tag_page 保留“当前已绑定载具”只显示 traycode 非空记录；新增“当前在制工件”列表显示无载具工件并提供“工件下线”，下线写流转历史、删除 active_products 当前在制记录，不删测试报告/测试数据。产品查询中 traycode 为空显示“无载具”。V1.3 traycode 保持可选，不改协议。

## 68. 架构决策：取消 tray_mode 配置列
2026-11-25：用户明确工序资源不需要单独的载具模式列；转运载具型号为空即代表该工序按无载具处理。已移除 process_step_resources.tray_mode 字段、init_schema 补列逻辑、constants 中 TRAY_MODE_* 常量、工艺配置页“载具模式”列、workbench_recipe/manual_inbound 与工位操作台的 tray_mode 判断。工位入站现在按 route.tray_models 是否为空决定是否显示载具扫描框；为空则不要求载具，非空则必须扫描允许型号的载具。

## 69. 架构决策：无载具使用固定数据库标记 no traycode
2026-11-25：无载具工件在数据库统一写 `no traycode`，UI 仍显示“无载具”，兼容旧数据中的空字符串。无载具入站提交一次后不进入锁定态，而是递增 token、清空 submitted 并把焦点指向下一批第一个工件条码框，支持连续扫码。工位操作台“当前在制工件”区块套 border 容器，并按空字符串或 no traycode 识别无载具记录。产品查询同样把 no traycode 显示成“无载具”。

## 70. 架构决策：载具缺失值统一为斜杠
2026-11-26：用户确认不再使用 `no traycode` 表示无载具；数据库和界面统一使用 `/`。为兼容历史数据，空字符串、`no traycode`、`/` 都通过 constants.is_missing_traycode 识别为载具缺失。新入站写 `/`；当前已绑定载具列表过滤载具缺失值；当前在制工件列表显示无载具工件；产品查询显示 `/`；工件下线允许空字符串、`no traycode`、`/` 三类历史/新数据。GLOSSARY 更新为“载具缺失值”。

## 71. 架构决策：新增针床注册
2026-11-26：注册配置页新增“针床注册”标签页，使用与载具注册一致的主数据注册骨架。新增 needle_beds 表，字段：needle_bed_no、needle_bed_name、product_model、step_no、enabled、remark；UI 支持新增、从原有模板中新建、列表编辑、保存、删除。主数据快照/读取/保存接口加入 needle_beds，种子数据默认空列表。

## 72. 架构决策：针床注册字段调整
2026-11-26：针床注册字段最终定为 needle_bed_code（针床码）、needle_bed_name（针床名称）、needle_bed_number（针床编号）、needle_bed_model（针床型号）、enabled、remark；去掉 needle_bed_no/product_model/step_no。新增表单排版与载具注册一致：第一行五列（针床码、针床名称、从原有模板中新建、针床型号、针床编号），第二行备注+启用，第三行新增按钮。完整补齐 needle_beds 表、仓储、API、快照、种子数据与 UI。

## 73. 架构决策：模板新建改为补齐表单空值
2026-11-26：所有“从原有模板中新建”统一改为：选择模板时不操作文本框；点击新增时用模板补齐表单中为空的文本字段，不覆盖用户已输入内容；不再自动生成 COPY 主键或给名称加“副本”。主键仍为空时保留为空并由各页校验要求填写。已覆盖工艺配置、设备注册、工序注册、载具注册、组件注册、针床注册，registry_helpers 新增 fill_missing_text_values，并补测试。

## 74. 架构决策：一个产品型号允许多个工艺并由工位显式选择
2026-11-26：允许多个启用工艺绑定同一个产品型号/组件，工艺号仍唯一，不再要求 component_no 唯一。工位操作台工件入站第一行改为：产品型号 → 工艺 → 工序 → 每行工件条码输入框数量。选择产品型号后拉取启用工艺列表；只有一个工艺自动选中，多个工艺需用户选择；切换产品型号或工艺清空工序和扫码批次。GET /api/ui/workbench/recipe 与 POST /api/ui/workbench/inbound 支持 process_code；多个工艺且未指定工艺时返回“请选择工艺”；最终写入 componentcode 仍为产品型号。
