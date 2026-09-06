# Autonomous Research Agent 最终架构设计

> 状态：实施前架构设计
>
> 本文只定义最终产品形态、系统边界、数据模型、编排方式和分阶段实施方案，不修改代码，不修改后端，不新增当前运行接口。

## 1. 结论先行：从页面串联升级为研究运行时

当前系统已经具备不少科研能力，但这些能力主要以独立页面和独立接口存在。前端通过 Copilot 页面依次调用 route、turn、plan、source、mapping、graph 等接口，页面本身承担了“下一步调用什么”的编排职责。

这会造成三个根本问题：

1. 用户被迫完成工程步骤，而不是提出科研问题。
2. 运行状态分散在前端状态和多个接口响应中，无法形成可信的研究运行记录。
3. 研究结果不能稳定沉淀为可复用的数据资产，尤其是 CSV、元数据、证据链和来源血缘。

最终架构应改为：

> 用户创建一次 Research Run，后端 `AutonomousResearchRunService` 负责自主推进，前端只负责呈现运行过程、展示阶段结果、接收必要确认和打开研究资产。

前端不再决定“下一步调用哪个模块”。后端编排器决定下一步，并将每个阶段的状态、输入、输出、风险、证据和阻塞原因写入 Run。

## 2. 当前仓库审计结论

### 2.1 已有可复用能力

以下能力已经存在，应组合和复用，而不是重新实现一套平行系统：

- v30 route、Copilot turn、memory、planner 及已有 session runtime。
- source registry、source discovery、source selection 相关接口和模型。
- `backend/app/sources/discovery` 中已有的 Europe PMC、GEO、BioSample 等发现能力。
- `backend/app/parsers/registry.py` 及 CSV、TSV、TXT、XLSX、HTML table、PDF text、JATS XML 解析器。
- schema pack、SchemaMatcher 和字段映射能力。
- `EvidenceBuilder` 对 `source_id`、`raw_field`、`raw_value`、confidence、status 的保留能力。
- graph project、finding explanation 和图谱展示能力。
- quality agent、quality gate、dataset builder、exporter 等旧的科研数据质量和导出能力。
- `ResearchAgentService` 及现有医疗科研数据处理链。
- Qwen session、API check、configuration 能力，能够在后端完成模型凭据生命周期管理。

这些能力应由新的研究运行时统一调用。它们不应继续由页面按固定流程直接串接。

### 2.2 当前关键缺口

审计结果表明，当前产品还不是自主科研工作空间：

- v31 左侧主要是流程节点，研究窗口和历史研究不是一等对象。
- `workspace-store` 和 `timeline-store` 主要是进程内或前端内存隔离，不能作为 Research Project / Run 的持久化模型。
- `session_id` 只承载有限的 goal、clarifications、constraints；没有完整的运行历史、阶段事件、资产和结果版本。
- v30 Planner 要求多项 clarification 完成后才进入规划，这与“风险驱动确认”相冲突。
- Source Discovery 当前主要是 registry projection 或候选发现，不等于真实的来源获取、数据下载和来源校验。
- `configs/v30/source_registry/astronomy.yaml` 中的天文学来源仍是 `catalog_only` 或 `planned`，没有可用于真实光变曲线产出的 astronomy adapter。
- 当前 v31 的 Ia 超新星路径没有生成可验收的真实观测级主表。
- PDF/图像理解当前更接近文字或分类理解；不应把图表识别结果直接当作精确观测数据。
- Evidence Graph 可以解释已有证据，但还没有和“研究运行产生的资产版本”形成闭环。
- 医疗 Integrate 仍是医疗域边界，不应为了展示自主运行而强行扩展为通用天文学集成。
- 当前 Qwen session 是模型凭据会话，不是研究会话，二者必须明确分离。

### 2.3 必须保持不变的边界

以下内容属于现有医疗数据安全边界和冻结接口，本架构不修改：

- `configs/canonical_schema.yaml`。
- `configs/medical_rules.yaml`。
- `configs/quality_rules.yaml`。
- `docs/06_评测指标与SDTI.md` 中的公式和指标定义。
- 医疗 schema、medical rules、adapters、SchemaMatcher、EvidenceBuilder、Quality Gate 和现有 `ResearchAgentService`。

若未来确实需要修改冻结内容，必须先创建 `CHANGE_REQUEST.md`，说明理由、影响、迁移方案和测试方案。

## 3. 最终产品形态

### 3.1 用户看到的是 Research Workspace

产品不是八步科研表单，也不是把 Planner、Source Discovery、Mapping、Graph 作为主导航。

用户打开首页后只需要提供一句研究问题，例如：

> 我想研究 Ia 型超新星光变曲线。

系统随后创建一个 Research Run，并自动推进：

1. 理解研究对象与问题边界。
2. 形成工作假设和研究目标。
3. 规划检索和数据路径。
4. 发现论文、数据库和数据表。
5. 选择有明确可访问性和证据等级的来源。
6. 获取允许使用的数据。
7. 生成领域字段体系。
8. 映射、解析和规范化记录。
9. 建立证据链和来源血缘。
10. 执行质量检查。
11. 产出科研数据资产。

用户可以查看过程、追问原因、修改方向、暂停或取消，但不需要逐步确认正常路径上的每一个节点。

### 3.2 三栏工作区

左侧是研究窗口，中间是研究运行，右侧是研究摘要。

#### 左侧：Research Workspace

- 新建研究。
- 当前 Research Project。
- 该项目下的运行历史。
- 其他研究项目，例如 HER2 耐药机制、Ia 型超新星光变曲线。
- 运行状态：进行中、已暂停、待确认、已完成、失败、已取消。
- 最近更新时间和最近产出资产。

左侧不展示八步流程，不把内部模块名称作为用户的主导航。

#### 中间：Research Run

中间区域展示研究叙事，而不是聊天气泡或表单：

- 原始问题。
- AI 理解。
- 工作假设。
- 研究计划。
- 当前自动运行阶段。
- 已完成阶段结果。
- 来源选择理由。
- 字段和数据预览。
- 证据链、质量结果和产出资产。
- 用户追问入口。

#### 右侧：Research Summary

右侧保持稳定、简短、可扫描：

- 研究对象。
- 研究目标。
- 当前阶段。
- 已确认内容。
- 当前约束。
- 下一步自动动作。
- 待用户确认的风险事项。

`route`、`retrieval_status`、`constraints`、`evidence` 等工程细节进入可折叠 Drawer，不暴露为主流程。

## 4. 正式领域模型

最终系统需要区分 Research Project、Research Run、Session 和 Asset。不能继续用一个 session 承担所有含义。

### 4.1 Research Project

代表一个长期研究窗口，例如“HER2 耐药机制”或“Ia 型超新星光变曲线”。

建议字段：

- `research_id`：稳定的研究项目标识。
- `title`：用户可读标题。
- `domain`：oncology、astronomy 或未来领域插件标识。
- `summary`：当前研究摘要。
- `created_at`、`updated_at`。
- `archived_at`。

Project 负责承载长期上下文、历史 Run 列表和研究摘要，不直接等于一次执行。

### 4.2 Research Run

代表用户针对一个问题发起的一次自主研究执行。

建议字段：

- `run_id`：一次运行的稳定标识。
- `research_id`：所属研究项目。
- `session_id`：本次运行与对话上下文的绑定标识。
- `question`：用户原始问题，不被模型改写覆盖。
- `interpreted_goal`：AI 对问题的结构化理解。
- `plan`：当前计划及其版本。
- `status`：queued、running、paused、waiting_for_confirmation、completed、failed、cancelled。
- `current_stage`：当前用户可读阶段。
- `internal_stage`：后端内部阶段，仅用于运行诊断。
- `progress`：阶段进度，不宣称数据精度。
- `constraints`：用户约束和系统约束。
- `risk_flags`：需要确认或需要人工复核的风险。
- `started_at`、`updated_at`、`completed_at`。
- `failure`：结构化失败原因和恢复建议。

Run 是自动执行和资产生成的边界。一个 Research Project 可以有多个 Run，一个 Run 不得跨 Project 污染上下文。

### 4.3 Session

Session 是对话和模型交互上下文，不是研究项目，也不是模型 API key session。

建议字段：

- `session_id`。
- `research_id`。
- `run_id`。
- `conversation_history`。
- `memory_snapshot`。
- `last_route`、`last_turn`。
- `created_at`、`expired_at`。

当前 v30 memory store 可以作为过渡层，但不能成为最终持久化方案。

### 4.4 Asset

Asset 是研究运行的可复用结果，必须可追溯到 Run、来源和处理版本。

核心资产类型：

- `dataset.csv`：结构化数据主表。
- `metadata.json`：字段、单位、类型、来源、许可、生成方式和版本。
- `quality_report`：质量检查、未解决问题和门禁结果。
- `source_lineage`：来源、下载、解析、映射和转换链路。
- `evidence_graph`：发现、证据、字段和结论之间的关系。
- `raw_artifact_manifest`：原始文件或原始响应的清单、hash 和访问记录。
- `review_queue`：无法自动安全决定的记录或字段。

每个 Asset 至少包含：

- `asset_id`。
- `run_id`。
- `asset_type`。
- `version`。
- `status`：draft、validated、needs_review、published、rejected。
- `created_at`。
- `source_ids`。
- `schema_version`。
- `lineage_id`。
- `quality_summary`。

## 5. AutonomousResearchRunService

### 5.1 职责边界

`AutonomousResearchRunService` 是后端研究运行时的统一入口，负责：

- 接收一次研究问题。
- 创建 Run、Session 和初始事件。
- 调度领域插件和现有科研服务。
- 管理阶段状态和重试边界。
- 将中间结果写入 Run，而不是只返回给页面。
- 根据风险策略决定继续、暂停、待确认或失败。
- 生成并登记科研资产。
- 将追问、改方向、暂停、取消转化为可审计事件。

它不是新的“万能 Agent”。它是一个受状态机、领域插件、工具权限、质量门禁和证据规则约束的研究编排器。

### 5.2 编排原则

1. 前端不能根据阶段名称自行拼接下一次 API 调用。
2. 每个阶段必须有明确输入、输出、证据、风险和完成条件。
3. 每次工具调用必须记录调用者、参数摘要、来源、结果状态和耗时。
4. 失败必须可区分为可重试、需用户介入、来源不可用、数据不合格或系统错误。
5. 运行状态以服务端为准，前端只订阅和呈现。
6. 允许自动运行不等于允许模型自由生成事实数据。
7. 任何进入主数据表的值都必须能回到真实来源或明确的派生规则。

### 5.3 阶段状态机

用户可见的阶段保持简洁，内部步骤可以更多，但不能暴露为八步主导航。

| 用户可见阶段 | 编排职责 | 成功条件 | 可能的阻塞 |
|---|---|---|---|
| 正在理解 | 解析问题、对象、目标、范围和隐含约束 | 形成结构化研究目标 | 目标歧义达到高风险 |
| 正在形成方向 | 生成工作假设和候选研究方向 | 方向可继续且没有明显越界 | 存在互斥的关键解释 |
| 正在规划 | 选择领域插件、检索策略、数据路径 | 有可执行计划和工具权限 | 缺少必要能力或权限 |
| 正在发现来源 | 检索论文、数据库、数据表 | 来源有可验证身份和用途 | 无可访问来源 |
| 正在选择来源 | 按权威性、可访问性、数据完整性和许可排序 | 形成来源集合 | 来源冲突或许可风险 |
| 正在获取数据 | 下载或读取允许使用的真实数据 | 原始数据可校验 | 来源不可用、需登录、条款不明 |
| 正在构建字段 | 生成领域 schema 和映射 | 字段含义、单位和类型明确 | 字段语义不足 |
| 正在解析与校验 | 解析表格/附件/图像并保留原始值 | 每条记录有 provenance 或进入 review | 表格/图像无法可靠解析 |
| 正在建立证据链 | 构建 source lineage 和 evidence graph | 关键字段可回溯 | 证据冲突或链路断裂 |
| 正在执行质量门禁 | 检查完整性、重复、单位、来源和安全规则 | 资产达到发布门禁 | 需要人工复核 |
| 已生成研究资产 | 发布 CSV、metadata、quality、lineage、graph | 资产可下载、可查看、可复现 | 资产仅部分完成 |

### 5.4 事件和结果

前端需要消费的是统一的 Run 事件，而不是猜测多个旧接口的隐含状态。

事件至少应包含：

- `event_id`。
- `run_id`。
- `event_type`：stage_started、stage_completed、source_selected、asset_created、risk_raised、confirmation_required、run_paused、run_failed 等。
- `stage`。
- `message`：用户可读说明。
- `data_ref`：指向中间结果或 Asset 的引用，而不是把大型数据塞进事件。
- `evidence_refs`。
- `risk_level`。
- `created_at`。
- `sequence`。

事件是审计日志；Run snapshot 是当前状态；Asset 是可复用结果。这三个概念不能混为一谈。

## 6. 自动推进与风险驱动确认

### 6.1 自动完成

在没有高风险歧义时，以下步骤自动完成：

- 研究对象识别。
- 目标和初步方向归纳。
- 默认检索计划。
- 来源发现和候选排序。
- 低风险来源选择。
- 允许范围内的数据获取。
- 领域字段体系生成。
- 确定性字段映射。
- 表格解析和标准化。
- 证据链构建。
- 质量检查。
- 资产生成和页面展示。

### 6.2 必须确认

只有以下情况才暂停等待用户：

- 研究目标存在互斥解释，会明显改变检索和数据资产。
- 需要扩大研究范围，例如从一种对象扩展到多个疾病、样本或观测项目。
- 来源许可、付费墙、登录权限或数据使用条款不清楚。
- 高权威来源存在无法自动解释的冲突。
- 数据需要对主键、时间尺度、单位或实体进行高风险合并。
- 图像或 PDF 表格需要不确定的 OCR/数字化才能进入主表。
- 医疗规则或质量门禁无法安全通过。
- 用户要求覆盖自动识别出的关键约束。

普通的“是否继续”“请选择下一步”“是否开始规划”不应再出现。

### 6.3 用户追问不打断主运行

用户可以在 Run 内追问：

- 为什么选择这个来源？
- 为什么采用这个字段？
- 修改研究方向。
- 只保留某个观测波段。
- 不使用某个来源。

默认行为是保留当前 Run 结果并创建一个新的计划版本或分支事件。修改方向不能静默覆盖原有资产，必须产生新的 Run revision 或新 Run，具体由持久化阶段确定。

## 7. Ia 型超新星最小领域插件

Ia 型超新星不能只作为前端演示文案。它必须成为第一个可验收的真实领域插件。

### 7.1 当前状态

当前 astronomy registry 只有 catalog/planned 级别描述，没有可完成真实观测数据获取的 adapter。因此 Phase B 必须新增明确的 astronomy 数据绑定、适配器、字段映射和测试夹具；不能把 LLM 生成的示例数据伪装成观测数据。

### 7.2 推荐的最小真实来源

首选使用 CDS VizieR 中已经公开、可识别、带有观测级光变曲线表的 Type Ia 超新星目录：

- CfA4 Type Ia light curves：目录 `J/ApJS/200/12/table6`，包含 SN、滤镜、MJD、测光误差、星等等字段。
- 作为第二个独立来源或小规模 smoke test，可选 SN 2021aefx 的 KSP photometry：目录 `J/ApJ/959/132/table1`，包含 MJD、Band、mag、error 和信噪比等字段。

正式实施时必须将 catalog ID、表名、论文/DOI、访问 URL、许可/致谢要求和抓取方式固定在 source binding 中，并通过实际 HTTP/VOTable/TSV 夹具验证；禁止由模型自由拼接来源 URL。

### 7.3 最小字段合同

目标观测级表至少包含：

- `sn_id`。
- `observation_time`。
- `band`。
- `magnitude` 或 `flux`。
- `error`。
- `redshift`。
- `source_id`。
- `raw_field`。
- `raw_value`。

其中 `observation_time` 必须注明时间尺度和转换规则。MJD 不得在没有记录规则的情况下静默转换为普通日期。

如果某个目录的光变表不含 `redshift`，可以从同一目录发布的、具有稳定 SN 标识的元数据表补充；但必须：

- 仅进行确定性的 SN identifier join。
- 记录两个表和两个字段的来源。
- 在 lineage 中标出 join 规则、匹配数和未匹配数。
- 对未匹配记录保留空值或进入 review，不得猜测。

不得把不同研究的对象在没有明确实体匹配规则时自动合并。

### 7.4 Astronomy adapter 的职责

adapter 负责：

1. 访问固定的官方公开目录。
2. 校验响应类型、目录身份、表名和内容 hash。
3. 保留原始文件或原始响应清单。
4. 将原始列映射为领域字段。
5. 为每条记录生成 source_id、raw_field、raw_value。
6. 记录单位、时间尺度、滤镜标准和缺失值语义。
7. 输出不确定性、未匹配、异常值和质量警告。
8. 生成可供 EvidenceBuilder、Quality Gate 和 Asset exporter 使用的中间记录。

adapter 不负责：

- 生成没有来源的天文观测值。
- 用语言模型补全缺失观测。
- 将论文叙述中的代表值伪装成逐观测记录。
- 把图中肉眼看到的曲线点直接写入主表。
- 在没有确定性规则时进行跨研究自动合并。

### 7.5 Ia 最小验收标准

必须同时满足：

- 至少一个真实公开来源可重复获取。
- 输出真实观测级表，而不是演示 mock。
- 每行可回溯到 catalog/table/source_id。
- 主字段保留 raw_field/raw_value。
- CSV 和 metadata 能说明单位、时间尺度、缺失值和字段来源。
- quality_report 能报告行数、缺失、重复、异常和未映射字段。
- source_lineage 能还原发现、获取、解析、映射和导出的顺序。
- evidence_graph 能把来源、字段、数据和研究结论关联起来。
- 来源不可用时运行进入 blocked/review，而不是降级为伪造数据。

## 8. 多模态数据链路

多模态不是在页面上放一个“理解图片”按钮，而是四层可审计管线：

1. Parser：识别文件类型并读取可解析结构。
2. Extraction：从表格、文本、图像或 PDF 中提取候选内容。
3. Validation：检查字段、单位、范围、重复和语义一致性。
4. Provenance：记录原文件、页码/区域/表格、方法、置信度和版本。

当前已有的 CSV、TSV、XLSX、HTML、PDF text、JATS parser 可以作为 Parser 层基础。PDF 表格如果无法稳定解析，必须进入 review；不能因为存在 OCR 结果就自动发布为主表。

图像能力需要区分：

- figure understanding：识别标题、坐标轴、图例、实验对象和图意。
- reliable digitization：把曲线或散点转成观测级数值，并记录坐标变换、像素区域、误差和人工复核。

前者可以自动进入研究叙事，后者只有在数字化质量和 provenance 达标后才可以进入主数据资产。

## 9. 结果资产页面

资产页面是 Research Workspace 的终点，不是旧流程中的附属页面。

### 9.1 CSV

展示：

- 行数、字段数、版本和更新时间。
- 可预览表格。
- 字段过滤和异常标记。
- 下载入口。
- 每个字段的来源和 raw value 入口。

CSV 不能独立展示，必须和 metadata、quality、lineage 绑定。

### 9.2 Metadata

展示：

- 研究问题和数据集用途。
- schema version。
- 每个字段的类型、单位、允许值、缺失语义和转换规则。
- 来源目录/论文/数据集 ID。
- 生成时间、版本、许可和致谢要求。
- 生成方式：原始、映射、派生或人工复核。

### 9.3 Quality Report

展示：

- 完整性。
- 重复记录。
- 类型与单位一致性。
- 关键字段缺失。
- 实体和时间匹配。
- provenance 覆盖率。
- 未解决记录。
- 是否通过发布门禁。

质量报告必须区分“数据本身不合格”和“当前工具无法证明数据合格”。后者进入 review，不得显示为通过。

### 9.4 Evidence Graph

保留现有 Graph 能力，但图节点需要与 Run 和 Asset 关联：

- Research question。
- Hypothesis。
- Source。
- Source table/file。
- Field。
- Observation/data record。
- Transformation。
- Finding。
- Quality issue。

用户点击一条结论时，应能看到支持它的来源、字段、记录或计算规则。

### 9.5 Source Lineage

以时间顺序和数据血缘展示：

发现来源 → 选中来源 → 获取原始文件 → 校验 hash → 解析 → 映射 → 清洗/转换 → 质量检查 → 资产版本。

每个节点至少展示：执行时间、工具版本、输入引用、输出引用、状态和失败原因。

## 10. API 与服务边界规划

本节是未来实施的接口设计，不代表本轮新增接口。

### 10.1 现有能力的过渡复用

短期可以在 `AutonomousResearchRunService` 内部调用现有 v30 能力：

- route / copilot turn / memory / plan。
- registry / discover / source selection。
- schema pack / match。
- graph / why / figure understand。
- integration preview / prepare / execute（仅在其支持的医疗范围内）。

前端不再直接把这些内部接口当作产品流程入口。

### 10.2 未来统一 Run API

建议在后端编排器稳定后提供统一资源接口：

- 创建 Research Project。
- 列出和切换 Research Project。
- 创建 Research Run。
- 获取 Run snapshot。
- 获取增量事件或订阅运行流。
- 暂停、恢复、取消 Run。
- 提交追问或修改方向。
- 获取 Run 的 Asset 列表。
- 获取 CSV、metadata、quality report、source lineage、evidence graph。
- 获取单个字段/记录的证据详情。

统一 API 的返回对象必须包含明确的 `run_id` 和 `research_id`，不能让前端根据一个全局 session 猜测当前上下文。

### 10.3 暂不改变的旧 API

现有 `/api/v30/*` 和 `/api/agent/*` 接口在过渡期继续保留。它们可以作为内部能力或兼容入口，但不应继续扩展为新的前端主流程。

## 11. API Key 与模型配置

模型凭据和研究上下文必须分离。

当前已有 Qwen session、API check 和 configuration 能力，未来应复用这些能力：

- 前端只提交到后端安全入口。
- API key 不进入 localStorage、conversation log、事件 payload、错误信息、Git 或源码。
- 后端只返回不可逆的连接状态、provider、模型和检查时间，不返回 secret。
- Qwen session 的 TTL 和容量限制继续由现有 registry 管理，不能误当作 Research Project 持久化。
- 如果没有可用模型配置，系统可以进入 deterministic demo/fallback mode，但 UI 必须明确标注“未配置模型”或“演示模式”。
- 演示模式可以运行确定性的路由、字段映射、来源 registry、质量和图谱展示，不得暗示真实 LLM 已完成推理。

当前公开能力主要支持 Qwen。Provider 选择器只有在后端 schema 和连接能力实际支持后才能开放，不能在前端提供虚假的通用 provider/API key 配置。

## 12. 前端信息架构落地原则

### Home

- 一个科研问题输入框。
- 最近研究窗口。
- 新建研究。
- 模型连接状态。
- 示例问题入口。

### Workspace

- 左侧 Research Workspace。
- 中间 Research Run。
- 右侧 Research Summary。
- Run 内部阶段以时间线/卡片形式展示。
- 自动运行中只显示当前动作和已产出结果，不要求确认。
- 风险暂停时显示原因、证据和用户选项。

### Assets

- CSV。
- Metadata。
- Quality Report。
- Source Lineage。
- Evidence Graph。
- 版本和下载。

### Drawer

以下内容只在需要时打开：

- route。
- retrieval_status。
- constraints。
- raw response 摘要。
- 工具调用和版本。
- evidence refs。
- review queue。

## 13. 分阶段实施路线

当前不写代码。下面定义以后每个实施阶段的边界、产物、测试、回滚和验收。

### Phase A：Autonomous Run Orchestrator

目标：先把“前端串接口”改成后端 Run 编排模型。

新增/修改范围：

- 新增 Run、事件、状态机和 orchestrator 领域模型。
- 增加 `AutonomousResearchRunService` 或等价服务。
- 复用现有 route、planner、source、schema、graph、quality 能力。
- 前端只接入 Run 状态和事件，不再决定下一步接口。

API：

- 优先在服务内部复用现有接口。
- 稳定后再提供统一 Run API。

测试：

- 正常路径状态机测试。
- 失败、重试、暂停、取消测试。
- 同时运行两个 Run 的隔离测试。
- 事件顺序和幂等性测试。
- 不满足条件时不得伪造完成的测试。

回滚：

- 保留 v31 旧路由和旧页面作为兼容入口。
- 通过 feature flag 或路由开关回退到原 Copilot，不删除旧能力。

验收：

- 用户输入一句问题即可创建 Run。
- 正常路径不要求连续确认。
- Run 可以完整显示状态和阶段结果。
- 前端刷新后不会凭空改变 Run 当前阶段。

### Phase B：Ia Supernova Minimal Domain Plugin

目标：用真实公开数据证明自主运行不是 UI 假象。

新增/修改范围：

- astronomy source binding。
- VizieR adapter。
- Ia schema、字段映射、时间/单位规则。
- 原始数据清单、hash、lineage。
- astronomy 质量规则和 review queue。

API：

- adapter 作为 Run 工具由 orchestrator 调用。
- 不在前端写专用 source fetch 链。

测试：

- 固定响应夹具测试。
- schema 和字段映射测试。
- 时间尺度、滤镜、误差、缺失和重复测试。
- source_id/raw_field/raw_value 保留测试。
- 许可/来源元数据测试。
- 可选的真实网络 smoke test；离线 CI 不依赖实时网络。

回滚：

- 关闭 astronomy plugin binding，Run 明确显示“该领域暂不可用”。
- 不回退为虚拟观测数据。

验收：

- 生成真实观测级 `dataset.csv`。
- 生成 metadata、quality_report、source_lineage、evidence_graph。
- 数据不可用时进入 blocked/review。

### Phase C：Research Project / Run / Asset Persistence

目标：让研究历史和多任务切换成为真正的一等能力。

新增/修改范围：

- Project、Run、Session、Asset 持久化模型。
- 版本、分支和归档。
- 研究历史索引。
- 旧 workspace-store/timeline-store 的迁移适配。

测试：

- 多项目并行隔离。
- 切换项目不污染 conversation、memory、timeline、summary。
- Run 版本和 Asset 版本一致性。
- 归档和恢复。

回滚：

- 读取旧 v30 session。
- 新模型写入失败时不删除旧 session。

验收：

- HER2 和 Ia 两个研究可并行存在。
- 每个研究拥有独立 session、memory、conversation、timeline、summary。
- 关闭并重新打开后研究历史可恢复。

### Phase D：Autonomous Workspace Frontend

目标：完成 ChatGPT Workspace + Elicit 的产品形态。

新增/修改范围：

- Home、Workspace、Assets 信息架构。
- Research Workspace 左侧历史。
- Research Run 中间叙事。
- Research Summary 右侧摘要。
- 统一事件流和风险确认卡。
- 工程细节 Drawer。

测试：

- 一句话启动到 Run。
- 自动阶段视觉变化。
- 追问不污染 Run。
- 修改方向生成新计划版本。
- 资产页面与 Run 资产引用一致。

回滚：

- 保留旧 Copilot 页面只作为 legacy route。
- 新首页可通过 feature flag 关闭。

验收：

- 用户感知是一个研究工作空间，不是流程表单。
- 正常路径无连续确认。
- Evidence、Graph、Source lineage 仍可访问。

### Phase E：Model Configuration and API Key Onboarding

目标：复用现有 Qwen session 能力完成安全模型配置。

新增/修改范围：

- 配置状态页面和连接检查。
- secret 生命周期、TTL 和断开。
- deterministic fallback 的明确提示。

测试：

- secret 不出现在前端存储、日志、事件和错误响应。
- 连接失败状态。
- session 过期状态。
- 无模型时的可用演示路径。

回滚：

- 使用既有 Qwen session API。
- 关闭新配置入口不影响已有后端配置。

验收：

- 用户知道当前是否使用真实模型。
- 系统不要求把 API key 粘贴到研究问题或浏览器 localStorage。

### Phase F：Demo / E2E / Asset Acceptance

目标：形成可比赛、可演示、可复核的闭环。

新增/修改范围：

- Ia 端到端演示脚本。
- medical 不变量回归。
- 资产下载和 lineage 展示。
- 失败和降级演示。

测试：

- Ia 真实来源路径。
- HER2 既有安全规则回归。
- 双研究切换隔离。
- 刷新/恢复。
- source unavailable、parse uncertain、quality fail。
- 完成资产接受测试。

回滚：

- demo 级 feature flag。
- 保留可审计的失败结果，不用 mock 成功替代。

验收：

- 用户一句问题启动。
- 系统自动推进并展示过程。
- 最终产出真实可解释资产。
- 任何关键数据都可回溯到来源或明确的转换规则。

## 14. 可信性与安全性原则

### 14.1 事实与推理分离

研究对象理解、假设和计划可以由模型生成，但观测值、患者字段、实验结果和关键元数据不能由模型凭空生成。

### 14.2 来源优先

每个关键值必须具有来源引用。来源冲突不能仅根据模型偏好自动选边；必须显示冲突并按风险策略暂停或进入 review。

### 14.3 原始值不可丢失

标准化后保留 `raw_field`、`raw_value`、`source_id` 和转换规则。派生字段必须标注计算过程和版本。

### 14.4 质量不是装饰

Quality Gate 的结果影响 Asset 状态。未通过门禁的结果可以作为 draft 或 review asset 展示，但不能标记为 validated/published。

### 14.5 医疗规则继续生效

医疗研究仍必须遵守：

- HER2 IHC 2+ 不得直接自动判为 HER2 Positive。
- ERBB2 CNA amplification 不等同于 HER2 IHC positive。
- 低置信度患者/样本关联进入 unresolved/review。
- 高权威来源不可解释冲突不得自动选边。
- 细胞系 AUC/IC50 与患者 pCR/response 必须区分 `response_domain`。

### 14.6 失败必须诚实

来源访问失败、解析不确定、字段缺失、图表无法可靠数字化或质量门禁失败时，系统应展示真实阻塞原因和可选恢复方式。禁止用示例数据、模型补全或“已完成”文案掩盖失败。

## 15. 架构决策门

进入编码前，必须确认以下决策：

1. 是否接受 `AutonomousResearchRunService` 作为后端编排边界。
2. 是否接受 Research Project / Run / Session / Asset 四层模型。
3. 是否接受风险驱动确认，而不是步骤驱动确认。
4. 是否将 VizieR CfA4 目录作为 Ia 第一真实来源。
5. 是否允许第二个 Ia 来源只用于独立对照和 lineage，不做无规则自动合并。
6. 是否接受 Phase A 先改运行时，再改前端页面。
7. 是否接受当前 Qwen session 只作为凭据会话，不能代替 Research Project 持久化。
8. 是否接受当前冻结医疗配置保持不变。

本文件确认后，下一步应先实施 Phase A 的后端 Run 编排设计和测试契约，再进入前端 Workspace 页面改造。当前不应继续在 Copilot 页面上增加更多确认按钮或流程节点。
