# v3.0 升级架构设计

- 产品版本：3.0
- 目标形态：通用科研数据发现与可信整合智能体
- 依据：`PROJECT_AUDIT_REPORT.md`
- 设计日期：2026-09-05
- 设计原则：增量叠加，不重构 Adapter / Schema / Quality，不把新逻辑继续堆进 `ResearchAgentService`
- 本文性质：架构设计，不是实施授权，不含代码

现有 `/api/v3/research/*` 继续作为肿瘤规划兼容面。v3.0 新编排入口使用 `/api/v30/*`，避免与已挂载的 v3 路由冲突。

---

# 0. 设计约束与一句话定义

v3.0 不是重写 Agent 操作系统，而是在现有“可信数据工厂”外包一层通用科研编排。

```text
新智能层负责：判断任务、形成通用合同、发现候选、抽取多模态、登记证据关系
旧内核负责：官方取数、字段对齐、身份隔离、医学规则、质量门、评测口径
```

硬约束：

1. 不修改 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`docs/06_评测指标与SDTI.md`。
2. 不重构现有 Adapter、SchemaMatcher、Quality V2 / Quality Gate。
3. 新模块不得直接写入 CanonicalRecord，不得生成患者/样本行。
4. 肿瘤任务必须能回落到现有 Frozen Research Contract 与 `ResearchAgentService`。
5. 证据图的边不得表示跨研究患者身份。
6. 无文本层 PDF、低置信度图像读数，默认 REVIEW，不得入库为主表事实。

---

# 1. 新架构图

## 1.1 分层总图

```text
用户
  │  自然语言 / 文件 / 已有合同约束
  ↓
前端
  ├─ 规划工作台（继续走现有五阶段，后续只换调用入口）
  └─ 高级工作台（继续展示工具、质量门、溯源；溯源改为读证据图）
  ↓
API 门面
  ├─ /api/v30/*                  v3.0 新编排（本文新增）
  ├─ /api/v3/research/*          现有肿瘤规划（保留）
  ├─ /api/agent/tasks            现有肿瘤执行引擎（保留）
  ├─ /api/adapters/*             现有官方 Adapter（保留，不改）
  ├─ /api/v2/schema|entity|quality 现有治理能力（保留，不改）
  └─ /api/evaluation/*           现有评测（保留，公式不改）
  ↓
v3.0 智能编排层（新增，旁路）
  ├─ Router Agent                 任务分流与学科判断
  ├─ Scientific Planner           通用研究契约与计划草稿
  ├─ Data Discovery Agent         开放候选发现
  ├─ Multimodal Extraction Agent  文件/PDF/表/图注抽取
  └─ Evidence Graph               统一证据关系，不存患者身份边
  ↓
适配编译层（新增，薄）
  ├─ OncologyContractCompiler     通用合同 → 现有 FrozenResearchContract
  ├─ ExecutionBridge              发现结果 → 现有 SourceBroker / Agent 工具参数
  └─ ExtractionBridge             抽取结果 → 现有 ParsedRecord / ParserRegistry
  ↓
现有治理内核（冻结，不重构）
  ├─ ResearchAgentService         肿瘤/已配置癌种执行引擎
  ├─ 官方 Adapter 族              GDC / GEO / cBioPortal / AACT / CIViC / DepMap / Discovery
  ├─ ParserRegistry               CSV / Excel / HTML / JATS / PDF 文本层
  ├─ SchemaMapper + Matcher       冻结 Canonical Schema
  ├─ PatientSampleLinker          低置信度 unresolved
  ├─ EvidenceBuilder              source_id + raw_field + raw_value
  ├─ medical_rules + SafetyLayer
  ├─ CriticAgent + Quality V2 + Quality Gate
  └─ ClosedLoopService            两轮防空转
  ↓
输出
  ├─ 主科研数据集 / companion 表
  ├─ 质量门 PASS / REVIEW / FAIL
  ├─ 证据图快照与导出包
  └─ 现有 Gold Set / 公开基准继续有效
```

## 1.2 运行时角色图

```text
                         ┌──────────────────────────┐
                         │        用户输入           │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │      Router Agent        │
                         │ 闲聊 / 澄清 / 规划 / 取数 │
                         └────────────┬─────────────┘
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                  ▼
            仅对话/概念问答     Scientific Planner    已有冻结合同
                    │                 │                  │
                    │                 ▼                  │
                    │        Frozen General Contract     │
                    │                 │                  │
                    │                 ▼                  │
                    │        Data Discovery Agent        │
                    │                 │                  │
                    │                 ▼                  │
                    │      SourceBroker（旧，只做组合）   │
                    │                 │                  │
                    │                 ▼                  │
                    │     需要解析文件？──是──► Extraction │
                    │                 │                  │
                    └─────────────────┼──────────────────┘
                                      ▼
                         领域 = oncology ?
                         ├─ 是 → ResearchAgentService（旧执行引擎）
                         └─ 否 → 通用表整合旁路
                                      │
                                      ▼  一律进入
                         Schema / Entity / Evidence / Quality（旧内核）
                                      │
                                      ▼
                         Critic + ClosedLoop（旧）
                                      │
                                      ▼
                         Evidence Graph 登记全程关系
```

## 1.3 权限边界图

```text
允许 LLM / 新 Agent 做的事              禁止新 Agent 做的事
--------------------------------        --------------------------------
判断是否进入科研数据链                  生成患者/样本行
提出澄清问题和通用合同                  修改 canonical_schema / medical_rules
发现候选来源和补充材料                  把目录摘要当成已解析字段
从文件抽出候选表/图注                   无把握 PDF/图像读数入库
解释为什么进入 REVIEW                   跨研究按同名编号合并
建议下一轮合法工具                      用自评把质量门改成 PASS
把通用合同编译成旧合同                  绕过 Adapter 直接写主表
```

---

# 2. 新增模块设计

五个新模块都是**旁路服务**。它们通过编译层调用旧内核，不替换旧内核。

每个模块统一遵守四条契约：

- 输入输出必须可序列化、可哈希、可按 `task_id` 隔离。
- 所有外部事实必须带 `source_id`；没有来源的内容只能是假设或澄清问句。
- 置信度低于阈值只进 REVIEW，不进主表。
- 不持有“全链路写权限”。

## 2.1 Router Agent

### 作用

把用户输入分成任务类型，并决定激活哪些下游模块。它是 v3.0 的唯一默认入口，用来解决审计中“前端规则分流 + Intent 词典 + 未接入的 Orchestrator 并存”的问题。

### 输入

| 字段 | 含义 |
|---|---|
| message | 用户原话 |
| session_id | 研究会话 |
| has_frozen_contract | 是否已有合同 |
| attached_files | 用户上传文件清单 |
| user_constraints | 只要公开数据、不要细胞系等 |

### 输出

| 字段 | 取值 |
|---|---|
| route | `CHAT` / `CONCEPT_QA` / `CLARIFY` / `PLAN` / `DISCOVER` / `EXTRACT` / `INTEGRATE` / `LITERATURE_ONLY` |
| domain | `oncology` / `biomedicine` / `general_science` / `unknown` |
| data_granularity | `patient` / `sample` / `study` / `file` / `unknown` |
| next_agents | 下游模块名列表 |
| reason | 可审计的路由理由 |
| fallback | 是否仅用确定性规则，未调用模型 |

### 决策规则（设计，不是代码）

1. 无研究对象、无结局、无数据意图：`CHAT` 或 `CONCEPT_QA`，不启动取数。
2. 有研究意图但缺人群/暴露/结局：`CLARIFY`，进入 Planner，不进入 Adapter。
3. 已有冻结合同且用户说“开始找数据”：`DISCOVER` 或 `INTEGRATE`。
4. 用户只上传 PDF/Excel：`EXTRACT`，先抽取再决定是否整合。
5. `domain=oncology` 且要患者级主表：最终 `INTEGRATE` 必须走现有 `ResearchAgentService`。
6. 现有 `ResearchOrchestrator` 不再作为生产路由；其阶段顺序可降级为 Router 的确定性兜底表。

### 智能边界

Router 可以调用小模型做分类，但必须有词典/规则兜底，保证无千问时仍能区分“闲聊”和“科研任务”。它不检索数据，不改合同。

### 与旧模块关系

- 收编前端规划工作台的本地分流。
- 收编 `ResearchIntentAgent` 的领域词典，作为确定性回退。
- 不替换 `ResearchAgentService`。

---

## 2.2 Scientific Planner

### 作用

把科研问题变成**与领域无关**的研究契约，再按学科编译到具体规则包。它解决“所有任务默认乳腺癌患者字段”的问题，同时保证肿瘤任务不丢失现有合同精度。

### 输入

- 用户问题或已澄清主题
- 文献 Evidence Pack（可空）
- 用户约束
- Router 给出的 domain / granularity

### 输出：General Research Contract

| 区块 | 内容 | 说明 |
|---|---|---|
| 研究问题 | 规范化问题句 | 必须可被用户确认 |
| 对象 | 人群、物种、材料、星体等 | 不预设一定是患者 |
| 暴露 / 处理 | 基因、药物、干预、条件 | 可空，空则标 unresolved |
| 结局 | 响应、生存、产率、通量等 | 必须带定义来源 |
| 单位与时间窗 | 单位、基线/治疗后、随访 | 缺失则 REVIEW |
| 数据模态 | api / table / pdf / image / file | 决定是否唤醒抽取 |
| 目标粒度 | patient / sample / study / dataset | 决定禁止哪些 Join |
| schema_pack_id | 默认肿瘤用现有冻结包 | 不改冻结文件，只选择加载 |
| rule_pack_id | 肿瘤用 medical_rules | 通用任务只用溯源规则 |
| 成功标准 | 必选字段覆盖、结局域匹配 | 供 Critic 复用 |
| 停止条件 | 预算、轮次、无新合法方法 | 交给现有 ClosedLoop |
| 待澄清问题 | 最多若干条 | 没有足够信息时停在这里 |

### 编译规则

| 条件 | 编译目标 | 不得做的事 |
|---|---|---|
| domain=oncology | 现有 FrozenResearchContract + 现有字段角色 | 不得放宽 HER2 / response_domain |
| domain=其他且只要溯源表 | 通用表合同，rule_pack=provenance_only | 不得套用乳腺癌示范队列 |
| Evidence Pack 为空 | 合同状态 = DRAFT，generation=GENERIC_FALLBACK | 不得当作已证实事实 |

### 智能边界

Planner 可以建议字段和指标，但不能创造数据。没有论文证据时，必须明确标记兜底。肿瘤任务的字段名继续映射到现有 Canonical 字段，不另起一套 HER2 语义。

### 与旧模块关系

- 门面覆盖 `RequirementAgent`、`ResearchContractBuilder`、`ResearchPlanningV2`。
- 肿瘤路径内部仍调用这些旧服务，不复制合同逻辑。
- 不写 CanonicalRecord。

---

## 2.3 Data Discovery Agent

### 作用

在开放资源中**产生候选**，不负责最终选源组合，也不负责下载后的字段证明。它解决“发现等于从种子目录打分”的问题。

### 输入

- 已冻结的 General Contract 或 Oncology Contract
- 论文中已出现的 accession / DOI / 补充材料链接
- Critic 或 Collection 给出的字段缺口
- 来源预算

### 输出：Discovery Candidate Set

每个候选至少包含：

| 字段 | 含义 |
|---|---|
| candidate_id | 稳定编号 |
| resource_kind | official_api / repository / paper / supplement / local_file / catalog |
| locator | URL、GSE、NCT、DOI、文件名 |
| source_id | 发现记录自身的来源 |
| discovered_from | 论文 / 目录 / 用户 / 种子 |
| field_hypotheses | 可能覆盖哪些合同字段 |
| verification_status | unverified / catalog_only / fetched |
| join_risk | 是否可能诱发非法患者 Join |
| next_action | fetch_via_adapter / parse_file / request_upload / reject |

### 工具分层

第一批只包装已有能力，不新写 Adapter：

1. GEO 目录检索
2. Europe PMC 与 accession harvest
3. 现有种子目录中的肿瘤来源
4. 用户上传文件登记

第二批才允许增加“论文补充材料链接收集”“通用仓库元数据检索”。新增的是发现器，不是事实 Adapter。

### 与 SourceBroker 的分工

```text
Discovery Agent     产生候选，标记假说和发现证据
SourceBroker（旧）  按覆盖、权威、成本做集合覆盖，输出 Join 策略
Adapter（旧）       运行时核验字段是否真的存在
```

Discovery 不得把“目录摘要提到 pCR”写成“已覆盖 pCR”。

### 与旧模块关系

- `SourceDiscovery`、`search_geo_catalog`、`accession_harvest`、Europe PMC 作为其工具。
- `SourceBroker` / `WeightedSetCoverOptimizer` 保持原接口。
- 肿瘤 INTEGRATE 时，选中的官方 API 候选仍交给现有工具名：`search_geo`、`search_cbioportal` 等。

---

## 2.4 Multimodal Extraction Agent

### 作用

按文件类型选择解析器，输出统一的抽取候选。它解决 PDF 只有文本层、图像只有图注、补充表无法进入同一契约的问题。

### 输入

- source_id（必须事先存在）
- 文件或全文
- 期望字段（来自合同，可空）
- 允许的模态：text / table / caption / image_candidate

### 输出

继续使用现有 `ParsedRecord` 超集，不另建事实通道：

| 字段 | 要求 |
|---|---|
| source_id / source_file / source_location | 必须 |
| raw_field / raw_value | 必须 |
| modality | text / table / caption / image_candidate |
| parse_confidence | 0 到 1 |
| status | PARSED / REVIEW / FAILED |
| inferred_semantic_type | 现有解析器语义 |

### 解析策略

| 模态 | 第一优先级 | 回退 | 入库规则 |
|---|---|---|---|
| CSV / Excel / HTML 表 | 现有 ParserRegistry | 无 | 高置信度可进对齐 |
| JATS 全文表 | 现有 JATS 解析器 | 无 | 与现在相同 |
| JATS 图注 | 现有 figure caption | 无 | 只作解释，不作主表 |
| PDF 有文本层 | 现有 PdfTextParser | 章节摘录 | 表结构不确定则 REVIEW |
| PDF 疑似表 | 新增版面表候选（后期） | 文本层 | 未校准前默认 REVIEW |
| 图像 | 只提取图注/轴标签文字（后期） | 无 | 禁止像素读数进主表 |
| 无文本层 PDF | 不猜测 | 空记录 + REVIEW | 保持现有禁令 |

### 智能边界

抽取 Agent 可以“提出哪里可能是表”，不能“补全看不清的数字”。`extract_paper_assets` 作为肿瘤论文工具保留，成为该 Agent 的一个后端，而不是被替换。

### 与旧模块关系

- 直接扩展调用 `ParserRegistry`。
- 不改现有五个解析器的成功语义。
- 新解析能力以新 parser 插件形式加入注册表，旧测试继续有效。

---

## 2.5 Evidence Graph

### 作用

成为全程唯一的关系层：问题为什么选这个来源、标准值从哪来、质量门为什么阻断。它解决“规划图、比赛对齐图、前端溯源图各做各的”问题。

### 节点类型

| 节点 | 来源 | 含义 |
|---|---|---|
| UserMessage | Router | 用户原话 |
| ResearchQuestion | Planner | 规范化问题 |
| Contract | Planner / 旧合同 | 冻结或草稿契约 |
| Paper | Literature / Discovery | 论文 |
| File | Extraction | 文件或补充材料 |
| Dataset | Adapter / Discovery | GSE、study、项目 |
| Table | Extraction / Dataset Builder | 一张可定位的表 |
| Field | Schema / 合同 | 目标字段或原始列 |
| RecordFact | EvidenceBuilder | 带 raw 的标准值单元格 |
| QualityFinding | Critic / Quality | 缺口、冲突、REVIEW |
| RepairAction | Repair / ClosedLoop | 已执行或被拒绝的修正 |
| ToolCall | 主 Agent | 一次官方工具调用 |

### 边类型（允许）

- `FORMULATES`：主题 → 问题
- `CONSTRAINED_BY`：问题 → 合同
- `HAS_EVIDENCE_CANDIDATE`：问题 → 论文
- `DISCOVERED`：论文/目录 → 数据集候选
- `FETCHED_BY`：数据集 → 工具调用
- `EXTRACTED_FROM`：表/图注 → 文件或论文
- `MAPPED_TO`：原始列 → 规范字段
- `SUPPORTED_BY`：规范值 → Evidence / raw_value
- `FLAGGED_BY`：字段或数据集 → 质量发现
- `TRIGGERED`：质量发现 → 闭环动作

### 边类型（禁止）

- 禁止 `SAME_PATIENT`
- 禁止 `JOINED_ACROSS_STUDY`
- 禁止用图查询结果自动合并身份
- 禁止把模型摘要节点连成“证明”

### 查询

前端和导出只问三类问题：

1. 这个标准值为什么成立？
2. 这个来源是怎么被发现和核验的？
3. 为什么质量门是 REVIEW / FAIL？

### 与旧模块关系

- 吸收 `ScientificGraphStore` 的规划图。
- 吸收比赛对齐里的来源-字段-反馈图。
- 吸收前端 lineage 展示数据。
- `EvidenceBuilder` 仍是事实单元格权威；图只引用 evidence_id，不复制可改写值。

---

# 3. 新旧模块映射

## 3.1 保留不动（内核）

| 旧模块 | v3.0 角色 | 是否改内部实现 |
|---|---|---|
| GDC / GEO / cBioPortal / AACT / CIViC / DepMap Adapter | 官方事实入口 | 否 |
| DiscoveryAdapter 现有方法 | 发现与论文抽取工具 | 否，仅被新 Agent 调用 |
| ParserRegistry 现有五解析器 | 文件解析内核 | 否 |
| canonical_schema.yaml | 肿瘤目标契约 | 否 |
| SchemaMapper / Matcher V2 | 字段对齐 | 否 |
| PatientSampleLinker / Entity Matcher | 身份候选 + 安全门 | 否 |
| EvidenceBuilder | 字段级证据 | 否 |
| medical_rules.yaml / SafetyLayer / RulePackEngine | 医学与发布规则 | 否 |
| Quality V2 / QualityAgent / QualityGate | 准入 | 否 |
| CriticAgent | 合同诊断 | 否 |
| ClosedLoopService | 两轮防空转 | 否 |
| 评测 / Gold Set / SDTI 公式 | 成绩口径 | 否 |
| ResearchAgentService | 肿瘤执行引擎 | 否，只增加外部调用，不在其中长新策略 |

## 3.2 新模块如何“包住”旧模块

| 新模块 | 调用的旧模块 | 旧模块继续单独对外吗 |
|---|---|---|
| Router Agent | ResearchIntentAgent（兜底）、前端分流逻辑上收 | 旧 Intent API 可保留 |
| Scientific Planner | RequirementAgent、ResearchPlanningService、ResearchPlanningV2、ResearchContractBuilder | `/api/v3/research/*` 保留 |
| Data Discovery Agent | SourceDiscovery、GEO catalog、Europe PMC、accession harvest | SourceBroker API 保留 |
| SourceBroker（旧） | 种子目录、加权集合覆盖 | 是，职责更纯 |
| Multimodal Extraction Agent | ParserRegistry、extract_paper_assets | `/api/v3` 解析接口保留 |
| ExecutionBridge | ResearchAgentService、现有 tool 名 | `/api/agent/tasks` 保留 |
| Evidence Graph | ScientificGraphStore、EvidenceBuilder、Competition lineage | 前端改为读新图，旧图接口可只读兼容 |

## 3.3 明确废弃或降级的方向

| 旧对象 | v3.0 处理 | 原因 |
|---|---|---|
| ResearchOrchestrator 作为生产总控 | 降级为 Router 兜底表，不再独立扩展 | 审计确认未接生产 |
| 前端本地闲聊规则作为唯一路由 | 降级为 Router 未配置模型时的回退 | 避免前后端各判一次 |
| 把新策略写入 ResearchAgentService | 禁止 | 防止主过程继续膨胀 |
| 用通用 Agent 重写 Adapter | 禁止 | 失去官方事实边界 |
| 为通用学科改冻结 Canonical Schema | 禁止 | 用 schema_pack 选择，不改肿瘤冻结文件 |

## 3.4 肿瘤任务兼容映射

```text
v3.0 对象                         现有对象
--------------------------------  --------------------------------
General Contract + oncology       FrozenResearchContract
schema_pack=oncology_canonical    configs/canonical_schema.yaml
rule_pack=medical_rules           configs/medical_rules.yaml
Discovery 官方 API 候选           Qwen / SearchPlanner 的 tool_calls
Extraction 论文表                 extract_paper_assets
ExecutionBridge.run               ResearchAgentService.run / start
QualityFinding                    QualityGateReport + CriticReport
Evidence Graph RecordFact         EvidenceCell
```

肿瘤回归验收：同一道乳腺癌示范题，v3.0 入口与直接打旧 API 相比，不得改变医学规则结果，不得减少 source_id / raw 保留，不得把 REVIEW 自动变成 PASS。

---

# 4. 数据流设计

v3.0 有三条合法数据流。它们在质量门之前汇合，不允许第三条“模型直写主表”的暗流。

## 4.1 流 A：肿瘤完整科研数据任务（主兼容流）

```text
用户问题
  → Router：INTEGRATE，domain=oncology
  → Planner：生成 General Contract
  → OncologyContractCompiler：编译为 FrozenResearchContract
  → Discovery：论文 accession + GEO 目录 + 种子队列
  → SourceBroker：覆盖矩阵与禁止 Join
  → ExecutionBridge：调用 ResearchAgentService
        → 现有工具（GDC/GEO/cBioPortal/…）
        → DatasetBuilder 选主表 / companion 表
        → Schema / Entity / Evidence
        → Critic / Quality / 可选 ClosedLoop
  → Evidence Graph：登记问题、工具、来源、字段、质量发现
  → 导出与前端展示
```

关键不变点：主表仍然只从现有 DatasetBuilder 能解析的队列产生。Discovery 不能因为“论文提到 METABRIC”就要求跨库拼患者。

## 4.2 流 B：通用文件 / 论文表整合（新旁路）

```text
用户问题或上传文件
  → Router：EXTRACT 或 DISCOVER
  → Planner：通用合同，rule_pack=provenance_only
  → Discovery：补充材料 / 本地文件 / 论文表
  → Extraction：ParserRegistry 产出 ParsedRecord
  → 通用表对齐（复用 SchemaMatcher 算法，不改肿瘤冻结 schema 文件）
  → Quality：只执行来源、原始值、重复、低置信度规则
  → Evidence Graph
  → 导出 REVIEW 数据包
```

这条流用于证明“通用科研数据”能力，但**不得**宣称拥有乳腺癌医学安全语义。没有对应规则包，就不能做 HER2 级裁决，只能做溯源级裁决。

## 4.3 流 C：只规划或只文献（不取患者表）

```text
宽泛主题
  → Router：CLARIFY 或 LITERATURE_ONLY
  → Planner 或 LiteratureAgent
  → Evidence Graph 只登记论文与候选问题
  → 停止
```

没有冻结合同，不得调用 Adapter 建患者主表。这保持现有“无 Evidence 则为 GENERIC_FALLBACK”的诚实口径。

## 4.4 闭环如何接回新层

现有 ClosedLoop 仍只改下一轮 `AgentTaskRequest`，不重写成通用规划器。v3.0 的接法是：

```text
Quality / Critic 诊断
  → 写入 Evidence Graph（QualityFinding）
  → 若仍在肿瘤执行引擎内：沿用 ClosedLoop / GoalLoop
  → 若缺口属于“候选来源不足”：回传 Discovery Agent 再产生新候选
  → 若缺口属于“文件未解析”：回传 Extraction Agent
  → 新候选仍须经 SourceBroker 与 Adapter 核验
```

第一期不把 GoalLoop 里的乳腺癌示范 GSE 策略搬进 Discovery。那些策略继续留在旧执行引擎，作为肿瘤 fallback。

## 4.5 对象生命周期

```text
Message
  → RouteDecision          可过期，不进导出包
  → GeneralContract        用户确认后冻结
  → DiscoveryCandidate     未核验
  → SourceItem             Adapter 核验后
  → ParsedRecord           抽取后
  → CanonicalRecord        仅旧整合内核写出
  → EvidenceCell           仅 EvidenceBuilder 写出
  → QualityDecision        仅质量门写出
  → GraphSnapshot          引用上述 ID，不另存可改写事实
```

谁写出 CanonicalRecord，谁就必须走旧整合管道。新 Agent 只允许写到 DiscoveryCandidate、ParsedRecord 候选和 Graph 节点。

---

# 5. API 设计

## 5.1 版本策略

| 前缀 | 状态 | 说明 |
|---|---|---|
| `/api/v30/*` | 新增 | v3.0 编排入口 |
| `/api/v3/research/*` | 保留 | 肿瘤澄清与冻结合同 |
| `/api/agent/*` | 保留 | 肿瘤任务执行与导出 |
| `/api/adapters/*` | 保留 | 单源调试，不作为产品主入口 |
| `/api/v2/*` | 保留 | Matcher / Quality / 检索能力层 |
| `/api/evaluation/*` | 保留 | 公式与考卷入口不改 |

前端规划工作台后续可改为先打 `/api/v30/route`，再按 route 调用旧接口；第一期也允许新旧入口并存。

## 5.2 新接口一览

### 路由

- `POST /api/v30/route`
  - 输入：message、session_id、约束、附件清单
  - 输出：route、domain、next_agents、reason
  - 副作用：写一条 Router 节点到证据图

### 规划

- `POST /api/v30/plan`
  - 输入：问题、可选 topic_id、可选已检索论文
  - 输出：General Contract、待澄清问题、是否 fallback
- `POST /api/v30/contracts/{contract_id}/freeze`
  - 输入：confirmed=true
  - 输出：冻结后的通用合同；若 domain=oncology，同时返回已编译的旧合同 ID
- `GET /api/v30/contracts/{contract_id}`
  - 输出：通用合同 + 编译映射

肿瘤用户仍可直接使用现有：

- `POST /api/v3/research/clarify`
- `POST /api/v3/research/contracts`
- `POST /api/v3/research/contracts/{id}/freeze`

### 发现

- `POST /api/v30/discover`
  - 输入：contract_id、预算、是否允许非种子来源
  - 输出：候选列表、发现证据、建议 next_action
- `POST /api/v30/discover/{set_id}/select`
  - 输入：被选 candidate_id
  - 输出：交给 SourceBroker 的候选子集；不在此下载大数据

现有 SourceBroker / optimize 接口继续承担组合，不在 discover 里做 set cover。

### 抽取

- `POST /api/v30/extract`
  - 输入：source_id、文件标识或 PMCID、允许模态
  - 输出：ParseResult 风格记录、REVIEW 警告
  - 约束：无 source_id 拒绝；图像像素读数接口第一期不提供

现有解析路由若已存在，抽取接口只做编排包装。

### 执行桥

- `POST /api/v30/integrate`
  - 输入：冻结 contract_id、已选发现集、是否闭环
  - 行为：
    - oncology → 内部转调现有 `/api/agent/tasks` 等价服务
    - 非 oncology → 只允许文件/论文表旁路，不得调用患者级跨源 Join
  - 输出：现有 AgentTaskResult 的兼容视图 + graph_id

不新增第二套任务状态机。任务状态继续用现有 `task_id`。

### 证据图

- `GET /api/v30/graphs/{graph_id}`
  - 输出：节点、边、生成时间、后端（networkx 或内置）
- `GET /api/v30/graphs/{graph_id}/facts/{evidence_id}`
  - 输出：标准值、raw_field、raw_value、source_id、支撑路径
- `GET /api/v30/graphs/{graph_id}/why/{finding_id}`
  - 输出：质量发现到合同缺口的解释路径

前端溯源图改为读这两个查询；不要为展示再生成一份无法回放的假图。

## 5.3 错误与诚实状态

| 情况 | HTTP / 业务状态 | 产品含义 |
|---|---|---|
| 闲聊被送进 integrate | 422 | Router 未允许取数 |
| 合同未冻结 | 422 | 不得取患者表 |
| 无 source_id 的抽取 | 422 | 禁止无来源解析 |
| 目录候选尚未 fetch | 业务标记 catalog_only | 不得声称字段已覆盖 |
| 图像读数 | 第一期 404 或明确未实现 | 不假装能像素提取 |
| 质量门 REVIEW | 200 + publish_allowed=false | 与现网一致 |
| 千问不可用 | 200 + fallback=true | 不得把兜底写成模型成绩 |

## 5.4 会话与凭据

沿用现有千问会话：凭据只在进程内存，最长两小时，不写入仓库。`/api/v30/*` 复用同一会话注册表，不新做一套密钥通道。

---

# 6. 文件目录设计

只新增目录，不搬迁旧内核。旧文件保持原路径，避免测试与导入断裂。

```text
backend/app/v30/
  __init__.py                 对外导出门面
  api.py                      挂载 /api/v30
  runtime.py                  编排器：按 Router 结果调用下游，不含领域策略
  models.py                   RouteDecision / GeneralContract / DiscoveryCandidate / GraphSnapshot
  compilers/
    oncology.py               GeneralContract → FrozenResearchContract
    provenance.py             通用溯源规则包选择（不改 medical_rules 文件）
  router/
    service.py
    rules.py                  无模型时的确定性分流
  planner/
    service.py                门面，内部转调 RequirementAgent / PlanningV2
  discovery/
    service.py                候选生产
    tools.py                  包装 GEO catalog / Europe PMC / 种子目录
  extraction/
    service.py                按模态调用 ParserRegistry
  graph/
    service.py                统一写入/查询
    projection.py             把旧 ScientificGraphStore / EvidenceCell 投影进来
  bridges/
    execution.py              转调 ResearchAgentService
    source_broker.py          转调 SourceBroker
    quality.py                只读转调，不改质量实现

backend/tests/v30/
  test_router.py
  test_planner_compile_oncology.py
  test_discovery_does_not_claim_coverage.py
  test_extraction_uses_parser_registry.py
  test_graph_forbids_patient_join_edges.py
  test_v30_api.py
  test_oncology_regression_bridge.py

configs/v30/
  schema_packs.yaml           只登记“用哪份已有 schema”，不改冻结 schema
  router_rules.yaml           分流词典
  discovery_budgets.yaml      来源预算与禁止项

docs/V3_UPGRADE_ARCHITECTURE.md   本文
```

明确不放进 `backend/app/agent/service.py` 的内容：

- 通用学科判断
- 开放世界发现策略
- PDF/图像新解析
- 证据图写入

前端第一期不必新目录。规划工作台增加对 `/api/v30/route` 的调用即可；高级工作台溯源区改为请求 graph 查询。

---

# 7. 开发优先级

原则：先接通入口和编译，再扩大发现，再增强抽取，最后才做图像；每一期都必须跑通肿瘤回归。

## P0：入口与肿瘤兼容（先做）

目标：v3.0 能作为门面存在，但不改变现网医学结果。

1. Router：确定性规则先上，模型分类可选。
2. Planner 门面：肿瘤问题编译回现有 Frozen Contract。
3. ExecutionBridge：冻结后转调现有 Agent 任务。
4. Evidence Graph 最小集：问题、合同、工具、来源、Evidence、质量发现。
5. `/api/v30/route`、`/plan`、`/integrate`、`/graphs/{id}`。

完成标准：

- 现有 pytest 肿瘤/Adapter/质量/闭环测试全部继续通过。
- 同一乳腺癌问题经 v30 与经旧 API 的质量门结论一致。
- 无千问时 Router 仍能拒绝闲聊进入 integrate。

## P1：发现与规划诚实性

1. Discovery Agent 包装 GEO 目录、Europe PMC、accession harvest。
2. 候选必须带 `verification_status=catalog_only`，直到 Adapter 返回。
3. Planner 在无论文时强制 GENERIC_FALLBACK。
4. SourceBroker 继续做组合，不在 Discovery 内选最终主表。

完成标准：

- 发现测试证明“摘要提到 pCR ≠ 字段已覆盖”。
- 现有 SourceBroker 测试不改期望。

## P2：多模态抽取接入注册表

1. Extraction 门面统一调用现有五解析器。
2. PDF 保持文本层；无文本层 REVIEW。
3. 论文表继续走 `extract_paper_assets` / JATS。
4. 前端允许“先抽取再决定是否整合”。

完成标准：

- `test_parsers.py` 期望不变。
- 新测试只覆盖编排，不放宽旧解析器。

## P3：证据图成为唯一展示源

1. 规划图、比赛 lineage、前端溯源改为投影自 Evidence Graph。
2. 增加 why-finding 查询。
3. 导出包增加图快照，但不替代来源 sheet。

完成标准：

- 图中不存在患者跨研究边。
- 旧 EvidenceBuilder 字段仍是事实权威。

## P4：谨慎的 PDF 表与图像候选（最后）

1. PDF 版面表只出 REVIEW 候选。
2. 图像只做图注/轴文字，不做像素读数入库。
3. 若赛题必须展示图像能力，单独开关，默认关闭。

完成标准：

- 任何图像数字进入主表都必须有人工确认接口；第一期可以没有该接口，即完全不入库。

## 明确不做的优先级事项

- 不重写 Adapter
- 不改 SDTI 公式
- 不把 GoalLoop 示范 GSE 提升为通用发现真理
- 不新开并行任务状态机
- 不把 v3.0 做成 ChatGPT 风格自由浏览 Agent

---

# 8. 测试方案

测试分四层。v3.0 新增测试不得靠硬编码 benchmark 答案通过；也不得改旧测试去迁就新行为。

## 8.1 旧内核回归（每次必跑，阻断发布）

范围：现有 Adapter、Parser、Schema、Entity、Quality、Critic、ClosedLoop、Research Agent、规划、Gold Set 观察脚本。

断言：

- 不改调用方式时，行为与现在一致。
- v30 ExecutionBridge 走肿瘤路径时，医学规则结论不变。
- `publish_allowed` 不会因为换了门面而变真。

这是增量升级的安全网。没有这一层，v3.0 不算可接受。

## 8.2 新模块契约测试

### Router

- 闲聊 / 概念问答不得进入 integrate。
- 明确的乳腺癌 pCR 问题应路由到 oncology + PLAN/INTEGRATE。
- 仅上传 PDF 应路由 EXTRACT。
- 无模型时规则回退仍可工作，并标记 fallback。

### Planner

- 肿瘤合同编译后的必选字段能被现有 Critic 识别。
- 无论文时 generation_source 不是 EVIDENCE_AGENT。
- 通用合同不得偷偷带上乳腺癌示范 GSE 作为默认必选来源。

### Discovery

- 候选必须有 source_id 与 discovered_from。
- catalog_only 不能写成字段覆盖成功。
- 不得输出跨研究 SAME_PATIENT 建议。

### Extraction

- 无 source_id 拒绝。
- 无文本层 PDF 得到 REVIEW，且无表值猜测。
- CSV/Excel/HTML/JATS 结果与直接调 ParserRegistry 一致。
- 第一期不存在“image_digitize_into_primary_table”成功路径。

### Evidence Graph

- 能从旧 EvidenceCell 投影出 SUPPORTED_BY。
- 拒绝写入 SAME_PATIENT / JOINED_ACROSS_STUDY。
- why-finding 能连到合同字段，而不是模型自评。

## 8.3 API 与权限测试

- 未冻结合同调用 `/integrate` 返回 422。
- `/discover` 成功不触发大数据下载。
- `/extract` 不接受缺失来源。
- 千问失败时响应含 fallback，且不把确定性结果标成模型成绩。
- 现有 `/api/v3/research/*` 与 `/api/agent/tasks` 契约保持。

## 8.4 端到端场景

场景一：乳腺癌专项（兼容）

1. 输入示范科研问题。
2. 经 `/route` → `/plan` → `/discover` → `/integrate`。
3. 对比直接旧链路的质量门、来源数、是否错误患者 Join。
4. 证据图中能回答“该 HER2 值的 raw_value 是什么”。

场景二：只规划

1. 输入过宽主题。
2. 停在澄清，不出现患者主表。
3. fallback 提示可见。

场景三：论文表抽取

1. 提供带 source_id 的 JATS/HTML。
2. 抽出表单元格与图注。
3. 图注不进主表；表单元格保留位置。

场景四：非法请求

1. 要求把细胞系 AUC 当作患者 pCR。
2. 旧规则仍阻断；新门面不得改写。

## 8.5 评测口径

v3.0 第一期**不宣布新的正式 SDTI**。

- 肿瘤正式观察仍走现有 Gold Set 与冻结公式。
- 通用能力继续用公开分层基准：问题解析、检索、字段匹配、实体匹配、清洗。
- 可为 Router / Discovery 增加任务级诊断，例如路由准确率、catalog_only 误报率；这些不是 SDTI，不得与正式成绩相加。
- 未运行的图像/PDF 版面能力不得填写分数。

## 8.6 验收清单

只有同时满足以下条件，才可称 v3.0 门面可用：

1. 旧内核回归通过。
2. 肿瘤兼容场景质量门一致。
3. 新模块无法绕过 source_id / raw / 质量门。
4. 证据图无非法身份边。
5. 文档不把旁路能力写成“已全面通用”。
6. 未实现的图像数字化保持未实现，而不是返回虚构表。

---

# 9. 设计收束

v3.0 的架构选择是：

**新智能在上，旧治理在下，编译层在中间。**

五个新模块各自补上审计里的一块缺口：

- Router：意图分流，不再靠前端和未接入 Orchestrator
- Planner：通用合同，肿瘤仍编译回旧契约
- Discovery：开放候选，SourceBroker 只做组合
- Extraction：多模态入口，解析内核仍是 ParserRegistry
- Evidence Graph：唯一可查询的证据关系，不替代 Evidence 事实

这不是 ChatGPT Agent，也不是重构。它把当前系统从“乳腺癌专项科研数据助手”，扩成“可走通用发现、但仍用可信内核收口的科研数据智能体”。

本文只设计，不修改代码。
