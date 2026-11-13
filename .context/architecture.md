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
