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
