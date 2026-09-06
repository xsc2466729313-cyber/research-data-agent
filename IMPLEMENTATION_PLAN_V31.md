# V3.1 增量实施计划

- 依据：`V3.1_UPGRADE_ARCHITECTURE_FINAL.md`
- 前序：`docs/V3_UPGRADE_ARCHITECTURE.md`、`PROJECT_AUDIT_REPORT.md`
- 对象：已有成熟系统 cancer-precision-data-agent
- 日期：2026-09-05
- 性质：实施计划，不是代码，不是重构授权

本计划把 V3.1 落成可执行阶段。每个阶段结束后，现有医学流程必须仍可运行。冻结内核全程只读。

---

# 第一部分：整体实施策略

## 1. 为什么采用增量升级

当前系统已经具备可演示、可导出、可评测的医学数据生产链：官方 Adapter、冻结 Canonical Schema、医学规则、Schema/Entity 对齐、Quality Gate、两轮闭环、Gold Set 与公开基准。审计结论是：缺的是通用交互与发现，不是这套内核本身。

直接重构会失去：

- HER2 / response_domain / 身份隔离等医学语义
- `source_id` / `raw_field` / `raw_value` / Evidence
- 已验证 Adapter 与约 90 个测试文件
- SDTI 与公开基准的可比口径

增量升级的含义是：新智能做成旁路服务，旧链路作为兼容后门始终可直连。医学回归是每一阶段的发布闸门，而不是最后补测。

## 2. 新旧系统如何共存

```text
旧入口（全程保留，行为不改）
  /api/research/*
  /api/v3/research/*
  /api/agent/tasks
  /api/adapters/*
  /api/v2/schema|entity|quality
  /api/evaluation/*

新入口（只增不替）
  /api/v30/*
      route / copilot / sessions / plan
      registry / discover
      schema-packs
      graphs
      extract / figures
      integrate  → 内部转调旧 ResearchAgentService
```

共存规则：

1. 旧前端高级工作台与旧 API 继续能独立跑完乳腺癌任务。
2. 新规划工作台可以先走 Copilot；用户仍可“跳过助手、直接运行研究协议”。
3. `integrate` 不新写任务引擎，只编译后调用现有 `ResearchAgentService`。
4. 肿瘤患者级任务继续使用冻结 schema 与 medical_rules，不走生成 pack 覆盖。
5. 新模块失败时，旧入口不受影响；禁止为了新测试去改旧期望。

## 3. 哪些模块作为新增智能层

全部放在 `backend/app/v30/`，不迁入 `backend/app/agent/service.py`。

| 模块 | 首次出现 | 职责 |
|---|---|---|
| Router | Phase 1 | 闲聊 / 概念问答 / 科研分流 |
| Research Copilot | Phase 1 | 理解目标、建议数据需求、必要澄清 |
| Session Memory（最小） | Phase 1 | 目标、澄清回答、约束 |
| Scientific Planner 门面 | Phase 1 | 确认后编译/转调现有合同服务 |
| Universal Source Registry | Phase 2 | 领域来源插件目录 |
| Discovery 门面 | Phase 2 | 按注册表产候选，不声称已覆盖 |
| Schema Generator | Phase 3 | 医学绑定冻结 pack；通用生成任务 pack |
| Evidence Graph | Phase 4 | 统一关系查询，不存患者跨研究边 |
| Extraction 门面 | Phase 5 | 包装 ParserRegistry |
| Figure Understanding | Phase 5 | 图理解演示，不进主表 |
| ExecutionBridge | Phase 1 末仅预留，Phase 2+ 使用 | 转调旧执行引擎 |

## 4. 哪些模块作为可信数据内核

以下只被调用，不重构、不改算法、不改公式：

| 内核 | 路径 |
|---|---|
| 冻结 Canonical Schema | `configs/canonical_schema.yaml` |
| 医学安全规则 | `configs/medical_rules.yaml` |
| 官方 Adapter | `backend/app/sources/*` |
| SchemaMatcher 核心算法 | `backend/app/integration/schema_matcher_v2.py` 及 V3 对照实现 |
| Quality Gate / Quality V2 | `backend/app/agent/quality_gate.py`、`backend/app/quality_v2/` |
| Critic | `backend/app/critic/` |
| EvidenceBuilder | `backend/app/evidence/` |
| 患者/样本关联安全门 | `backend/app/integration/patient_sample_linker.py` |
| 肿瘤执行引擎 | `backend/app/agent/service.py` |
| 闭环 | `backend/app/agent/closed_loop.py` |
| Gold Set 与 SDTI | `goldset/`、`docs/06_评测指标与SDTI.md` |
| 现有规划/合同 | `requirement_agent`、`research_planning`、`research_planning_v2` |

内核原则：新层可以**读**合同、质量报告、Evidence；除 ExecutionBridge 按旧接口**调用**执行外，新层不得**写** CanonicalRecord。

---

# 第二部分：开发阶段规划

阶段编号与 V3.1 文档中的 P0–P5 对齐关系：

| 本计划 | V3.1 优先级 | 内容 |
|---|---|---|
| Phase 0 | 工程保护（V3.1 未单列，实施必须先做） | baseline、API 快照、医学回归 |
| Phase 1 | P0 | Copilot + Router + 最小 Memory + Planner 门面 |
| Phase 2 | P1 | Registry + Discovery |
| Phase 3 | P2 | Schema Generator |
| Phase 4 | P3 | Evidence Graph |
| Phase 5 | P4 | Multimodal + Figure Understanding |
| Phase 6 | P5 | 可选高级能力，默认关闭 |

---

## Phase 0 — 工程保护

### 目标

在写任何新功能之前，把“现网医学能力”冻成可对照的基线。没有基线，后续无法证明没损坏。

### 新增能力

无产品能力。只增加保护资产：分支约定、基线记录、回归命令、输出对照清单。

### 修改文件

新增：

- `docs/v31_baseline/` 目录（基线说明与快照索引）
- `docs/v31_baseline/API_SNAPSHOT.md`
- `docs/v31_baseline/REGRESSION.md`
- `docs/v31_baseline/OUTPUT_CONTRACT.md`

修改：

- 无业务代码
- 可选：只在开发说明中引用上述文档（不改 README 成绩表述）

不修改：

- 全部 `configs/` 冻结文件
- 全部 Adapter / Matcher / Quality / Gold Set / 评测公式
- `backend/app/agent/service.py`
- `frontend/` 行为

### 数据流变化

无。用户仍走现有规划工作台与 `/api/agent/tasks`。

### API 变化

新增接口：无  
修改接口：无

只做只读盘点，见第三部分。

### 测试方案

1. 新功能：本阶段无新功能，不测新行为。
2. 医学未损坏：跑固定回归集，记录通过数与关键输出字段清单，作为后续阶段对照。

### 完成标准

- 升级分支已从当前可运行提交拉出
- API 快照与回归命令已落盘
- 基线回归一次通过，结果写入 `docs/v31_baseline/`
- 未合并任何 v30 业务代码

---

## Phase 1 — Copilot + Router + Planner

### 目标

用户先被理解、建议和澄清，再进入现有规划/合同。闲聊不得取数。旧医学 API 直连仍可用。

### 新增能力

- Router 分流
- Research Copilot 结构化回复
- 最小 Session Memory：研究目标、澄清回答、约束
- Planner 门面：仅在 Copilot `ready_for_planner=true` 后转调现有 Requirement / Planning 服务
- 前端可选展示 Copilot 回复；不强制关掉旧“运行研究协议”

### 修改文件

新增：

- `backend/app/v30/` 下 router / copilot / memory / planner / api 骨架
- `backend/tests/v30/` 对应测试
- `configs/v30/router_rules.yaml`

修改：

- `backend/app/main.py`：只增加 `mount_v30_routes`，不改旧路由处理函数
- `frontend/app.js` / `frontend/index.html`：规划工作台增加 Copilot 展示与“继续澄清 / 生成方案”；不删除旧提交流程

不修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/sources/**`
- SchemaMatcher 核心算法文件
- Quality Gate / Quality V2 逻辑
- Gold Set 与 `docs/06_评测指标与SDTI.md`
- `ResearchAgentService.run` 主过程

### 数据流变化

```text
用户输入
  → POST /api/v30/route
  → CHAT / CONCEPT_QA：Copilot 短答，不写研究目标，不 plan
  → RESEARCH：POST /api/v30/copilot/turn
        → 写最小 Memory
        → ready=false：只提问
        → ready=true：才允许 POST /api/v30/plan
  → Planner 门面转调现有 /api/v3/research 等价服务
  → 用户仍可直接打旧 /api/agent/tasks（兼容后门）
```

本阶段不自动 Discovery，不自动 Integrate。

### API 变化

新增接口：

- `POST /api/v30/route`
- `POST /api/v30/copilot/turn`
- `POST /api/v30/sessions`
- `GET /api/v30/sessions/{session_id}/memory`
- `POST /api/v30/plan`（无 ready 则 422）
- `GET /api/v30/contracts/{contract_id}`（门面，读编译结果）

修改接口：无旧路径行为变更。

### 测试方案

新功能：

- 闲聊 / 概念问答不产生合同
- HER2 耐药先复述再提问
- 确认“疗效预测”后 Memory 有目标，plan 才允许
- 新 session 不继承旧约束

医学未损坏：

- 重跑 Phase 0 回归
- 直接调用 `/api/v3/research/clarify` 与 `/api/agent/tasks` 的现有测试保持通过

### 完成标准

见第四部分验收清单。核心：旧医学流程绿，新助手不抢跑。

---

## Phase 2 — Universal Source Registry + Discovery

### 目标

Discovery 按注册表找来源。医学条目绑定现有工具名；天文/材料可为 catalog/planned。

### 新增能力

- 来源注册与查询
- 候选带 `verification_status`
- Copilot 的“可能去哪里找”可读 Registry
- 排除约束（如不要 METABRIC）能传给发现候选过滤，但不改 Adapter

### 修改文件

新增：

- `backend/app/v30/registry/`
- `backend/app/v30/discovery/`
- `configs/v30/source_registry/oncology.yaml`
- `configs/v30/source_registry/astronomy.yaml`
- `configs/v30/source_registry/materials.yaml`
- 对应测试

修改：

- `backend/app/v30/api.py` 增加 discover / registry 路由
- Copilot 建议数据需求时可引用注册表显示名
- `main.py` 仅继续挂载，不改旧路由

不修改：

- Adapter 实现
- `source_broker` 集合覆盖算法（只调用）
- 冻结配置与评测公式

### 数据流变化

```text
已确认合同或 Copilot 领域
  → Registry 按 domain 过滤
  → Discovery 产出候选（catalog_only / unverified）
  → SourceBroker（旧）做组合
  → 仅 fetch_binding 指向旧工具的候选可进入后续 integrate
```

### API 变化

新增接口：

- `GET /api/v30/registry/sources`
- `POST /api/v30/discover`
- `POST /api/v30/discover/{set_id}/select`

修改接口：无。

### 测试方案

新功能：医学任务能列出 GEO/GDC/cBioPortal；catalog 不得变已覆盖；planned 天文源不能生成观测主表。  
医学未损坏：旧 `test_source_broker.py`、`test_research_agent.py`、Adapter 测试通过。

### 完成标准

- 注册表可查询，无硬编码新库名进 Discovery 服务
- 医学 fetch 仍指向旧工具名
- Phase 0 回归通过

---

## Phase 3 — Dynamic Schema Generator

### 目标

医学高风险字段绑定冻结 pack；通用任务生成任务级 pack，作为 SchemaMatcher 的目标清单，不改 Matcher 算法。

### 新增能力

- Schema Generator
- `schema_pack_id` 进入合同门面
- 通用表示例字段（超新星等）含溯源三件套

### 修改文件

新增：

- `backend/app/v30/schema_generator/`
- `configs/v30/schema_packs.yaml`（索引，不复制改写冻结 schema）
- 对应测试

修改：

- Planner 门面输出增加 pack 引用
- 仅在 v30 融合桥里把“目标字段列表”传给现有 Matcher 调用点；不改 Matcher 内部打分

不修改：

- `configs/canonical_schema.yaml`
- SchemaMatcher 核心算法
- Quality Gate 逻辑

### 数据流变化

```text
Planner 合同
  → oncology 患者级：绑定 oncology_canonical_v0.1
  → 通用：生成 DRAFT pack，确认后 READY
  → Matcher 用该目标清单对齐
  → 医学规则只作用于冻结字段
```

### API 变化

新增接口：

- `POST /api/v30/schema-packs/generate`
- `GET /api/v30/schema-packs/{pack_id}`

修改接口：无旧 Matcher HTTP 契约变更。可新增 v30 包装，旧 `/api/v2/schema/match` 保持。

### 测试方案

新功能：乳腺癌绑定冻结包；超新星 pack 含指定字段与 raw 三件套；未 ready 不生成完整通用 pack。  
医学未损坏：`test_schema_entity_v2.py`、`test_schema_matcher_v3.py`、`test_v2plus_matchers.py`、医学安全相关测试通过。

### 完成标准

- 冻结文件 diff 为空
- 医学任务 HER2 规则仍生效
- 通用 pack 不得占用高风险医学字段名装其他含义

---

## Phase 4 — Evidence Graph

### 目标

把问题、约束、来源、Evidence、质量发现收成可查询图。前端溯源改为读图，不再另造假图。

### 新增能力

- 图写入与三类查询
- 节点含 CopilotTurn、MemoryConstraint、SchemaPack
- 禁止患者跨研究边

### 修改文件

新增：

- `backend/app/v30/graph/`
- 图测试

修改：

- v30 各阶段在成功路径上登记节点（只写引用 ID）
- 前端溯源区增加读 `/api/v30/graphs/{id}` 的可选视图；旧 lineage 展示可先并存

不修改：

- `EvidenceBuilder` 事实生成逻辑
- Quality Gate 判定

### 数据流变化

各阶段产物以 ID 投影入图。查询不改变质量门结果。

### API 变化

新增接口：

- `GET /api/v30/graphs/{graph_id}`
- `GET /api/v30/graphs/{graph_id}/facts/{evidence_id}`
- `GET /api/v30/graphs/{graph_id}/why/{finding_id}`

修改接口：无。

### 测试方案

新功能：能解释 raw 来源与 REVIEW 原因；排除 METABRIC 是约束边。  
医学未损坏：导出 Excel 的来源 sheet 仍由旧 exporter 生成；评测脚本不读新图也能跑。

### 完成标准

- 无非法身份边
- EvidenceCell 仍是事实权威
- Phase 0 回归通过

---

## Phase 5 — Multimodal Figure Understanding

### 目标

抽取走现有 ParserRegistry；图理解可演示；数字不进主表。

### 新增能力

- `/extract` 编排包装
- `/figures/understand` 理解卡
- 界面标明“理解演示，非主表数据”

### 修改文件

新增：

- `backend/app/v30/extraction/`
- `backend/app/v30/figures/`
- 对应测试

修改：

- 前端增加图理解卡片
- api 挂载 extract / figures

不修改：

- 现有五个解析器成功语义
- Adapter
- Quality 对主表的判定

### 数据流变化

```text
带 source_id 的文件/论文
  → extract：ParsedRecord
  → figures/understand：理解卡，enters_primary_table=false
  → 主表仍只来自 Adapter 或表格解析
```

### API 变化

新增接口：

- `POST /api/v30/extract`
- `POST /api/v30/figures/understand`

修改接口：无。旧 `/api/v3/parsing/run` 保持。

### 测试方案

新功能：无 source_id 拒绝；理解卡不入库；无文本层 PDF 仍 REVIEW。  
医学未损坏：`test_parsers.py`、GEO/cBioPortal 建表测试通过。

### 完成标准

- 不存在数字化入库 API
- 导出主表不含图估读数
- Phase 0 回归通过

---

## Phase 6 — 可选高级能力（默认关闭）

### 目标

仅为后续预留：PDF 版面表 REVIEW 候选、第一个非医学真实 Adapter、人工确认后的数字化、只读档案。本阶段可以只出开关与“未实现”响应，不承诺开发。

### 新增能力

默认无。若做，必须独立开关，默认关。

### 修改文件

新增：功能开关配置与未实现接口说明。  
修改：无内核。  
不修改：冻结文件、评测公式、默认主链。

### 数据流变化

开关关闭时与 Phase 5 完成态完全相同。

### API 变化

可选新增但必须 404/明确未实现。禁止静默成功。

### 测试方案

开关关闭 = Phase 5 行为。未实现能力不得出现分数。

### 完成标准

- 默认关闭
- 不宣布新正式 SDTI
- 医学回归通过

---

# 第三部分：Phase 0 详细设计

本阶段禁止开发新功能。目标是“先能证明以后没把医学弄坏”。

## 1. 升级分支策略

建议分支（名称可按仓库习惯微调，策略不可省）：

| 分支 | 用途 |
|---|---|
| 当前稳定分支（main 或现用发布枝） | 不直接开发 V3.1 |
| `feat/v31-phase0-baseline` | 只提交基线文档，可先合并 |
| `feat/v31-phase1-copilot` | Phase 1 旁路 |
| 此后每阶段一条 `feat/v31-phaseN-*` | 阶段结束必须 rebase/merge 前跑回归 |

规则：

1. 不在医学内核文件上开长期改动枝。
2. 每个 phase 分支只允许新增 `backend/app/v30/**`、`backend/tests/v30/**`、`configs/v30/**`、必要的 `main.py` 挂载、以及有限前端接线。
3. 若某提交碰到冻结文件，视为不合格，回退。
4. 禁止 `--no-verify` 跳过与医学回归相关的检查（除非用户明确要求，本计划不建议）。
5. 不把 v30 与无关重构混在同一 PR。

## 2. 当前系统 baseline 记录

在 `docs/v31_baseline/` 记录一次“升级前真相”，至少包括：

| 项 | 记什么 |
|---|---|
| git 提交 | 短哈希、日期、分支 |
| 应用版本 | FastAPI 标题与现有 `2.0.0-qwen-agent` 标记 |
| 冻结文件校验 | `canonical_schema.yaml` / `medical_rules.yaml` / SDTI 文档的校验和或 git blob |
| 公开对照成绩口径 | 只引用现有文档数字，不重算、不改写 |
| 医学主链入口 | 规划工作台、`/api/v3/research/clarify`、`/api/agent/tasks`、导出 |
| 已知诚实限制 | `publish_allowed=false`、official_candidate 未 sealed、DepMap 非患者主表 |

禁止在 baseline 里“顺便优化”文档成绩表述。

## 3. 当前 API 快照

对现网只读列出，写入 `API_SNAPSHOT.md`。建议用 OpenAPI `/openapi.json` 导出路径清单，并人工标出冻结入口：

必须快照的产品入口：

- `GET /health`
- `POST /api/agent/qwen-sessions`
- `POST /api/agent/tasks`
- `GET /api/agent/tasks/{task_id}`
- `GET /api/agent/tasks/{task_id}/export/{file_format}`
- `POST /api/v2/agent/closed-loop`
- `POST /api/research/topics` 及后续 literature / contract / source-plan
- `POST /api/v3/research/clarify`
- `POST /api/v3/research/contracts`
- `POST /api/v3/research/contracts/{id}/freeze`
- `POST /api/v3/parsing/run`
- `POST /api/v3/critic/diagnose`
- `POST /api/adapters/gdc|geo|cbioportal|aact|civic`
- `POST /api/v2/schema/match`、`/api/v2/entity/match`
- `POST /api/v2/quality/review`
- `POST /api/evaluation/run`、`/api/evaluation/official-run`

快照字段：方法、路径、现有 response_model 名、是否允许在后续 phase 修改。  
默认：上表全部标记 **行为冻结**。后续只能在 `/api/v30/*` 新增。

## 4. 医学流程回归测试

写入 `REGRESSION.md` 的固定命令（实施时按仓库实际环境执行，本计划不改测试内容）：

第一层：自动测试（每次 phase 合并前必跑）

- 规划与合同：`test_research_planning.py`、`test_research_planning_v2.py`、`test_requirement_agent.py`、`test_v3_api.py`
- 主 Agent：`test_research_agent.py`、`test_closed_loop.py`、`test_goal_loop.py`、`test_quality_gate.py`、`test_quality_agent.py`
- Adapter：`test_*_adapter.py`、`test_*_integration.py`（gdc/geo/cbioportal/aact/civic/depmap）
- 治理：`test_schema_entity_v2.py`、`test_normalizers.py`、`test_integration_pipeline.py`、`test_quality_v2.py`
- 解析：`test_parsers.py`
- 评测加载：`test_official_evaluation.py`、`test_goldset.py`（不改分数、不改公式）

第二层：手工/脚本冒烟（Phase 0 做一次，之后每阶段至少一次）

1. 不经 v30，直接用现有工作台或旧 API 跑一条乳腺癌示范问题（允许确定性兜底，以便无密钥环境也可对照）。
2. 记录：task_id、工具名列表、主表行列数、质量门状态、`publish_allowed`、是否出现跨源患者合并。
3. 导出 Excel，确认仍有来源 / 字段 / 可科研性类 sheet（以现网为准）。

第三层：安全断言抽查

- HER2 IHC 2+ 不得变成 Positive
- 细胞系 AUC 不得进入患者 response
- 无 Evidence 不得 publish_allowed=true

这些断言已有测试则只记录“由某某测试覆盖”；不要在 Phase 0 新写产品逻辑。

## 5. 数据输出一致性检查

写入 `OUTPUT_CONTRACT.md`，作为后续对照表，而不是新格式：

| 检查项 | 基线期望 |
|---|---|
| 主表行来源 | 仅 Adapter / 现有 DatasetBuilder 可解析队列 |
| 每条标准值 | 能回到 source_id + raw_field + raw_value |
| companion 表 | 独立 study_key，不拼进主患者 |
| 质量门 | PASS / REVIEW / FAIL 枚举不变 |
| 导出格式 | csv / parquet / xlsx 入口不变 |
| 评测 | official-run 仍读 `goldset/templates/`，公式文档不变 |

后续阶段若 v30 导出与旧导出并存，旧导出字段不得变少。新图快照只能新增，不能替换来源 sheet。

## Phase 0 完成清单

- [ ] 保护分支存在
- [ ] 基线文档三份齐全
- [ ] 回归命令执行一次并记录通过
- [ ] 输出契约列出
- [ ] 工作区无 v30 业务实现混入本阶段

---

# 第四部分：Phase 1 详细设计

重点：Research Copilot + Router + 最小 Memory + Planner 门面。  
不做：Registry、Schema 生成、Graph、Figure、长期记忆、自动取数。

## 总数据流

```text
用户输入
    ↓
Router
    ↓
Research Copilot
    ↓
Session Memory（目标 / 澄清回答 / 约束）
    ↓
Planner 门面（仅 ready 后）
    ↓
现有 RequirementAgent / ResearchPlanning 服务
```

## 1. Router

### 输入

- `session_id`（可空，空则后续 Copilot 创建）
- `message`
- `has_frozen_contract`
- `attached_files`（本阶段可忽略文件内容，只看是否存在）

### 输出

- `route`：`CHAT` / `CONCEPT_QA` / `CLARIFY` / `PLAN`
- `domain`：`oncology` / `biomedicine` / `general_science` / `unknown`
- `reason`
- `fallback`：未用模型时为 true

本阶段 Router **不要** 输出 `INTEGRATE` / `DISCOVER`。即使用户说“开始找数据”，若尚未澄清，仍是 `CLARIFY`；已有旧合同且走兼容后门时，让用户继续打旧 API，不在 v30 自动 integrate。

### 接口

- `POST /api/v30/route`

### 依赖

- `configs/v30/router_rules.yaml` 确定性规则
- 可选：现有 `ResearchIntentAgent` 的领域词典，只读调用
- 可选：千问分类；失败必须规则回退
- 不依赖 Adapter、Matcher、Quality

### 规则要点

- 问候、无对象无验证意图 → `CHAT`
- “什么是 HER2 / 什么是红移” → `CONCEPT_QA`
- 含研究意图但缺重点/结局 → `CLARIFY`
- 已有 Memory 中确认重点，且用户明确要求形成方案 → `PLAN`

## 2. Research Copilot

### 输入

- `session_id`
- `message`
- Router 的 `route` / `domain`（Copilot 不得把 CHAT 改写成 PLAN）
- 当前 Memory 快照

### 输出

- `understood_goal`：对象、目标、粒度
- `suggested_data_needs`：建议列表，且标记“尚未检索”
- `clarifying_questions`：1 到 3 个
- `ready_for_planner`：布尔
- `user_visible_reply`：给前端的结构化文本
- `memory_patches`：本轮增量
- `blocked_reason`：CHAT/CONCEPT_QA 时必填

示范：用户说研究 HER2 阳性乳腺癌耐药机制 → 复述对象与目标，建议临床/表达/突变/药敏，询问机制还是疗效预测。此时 `ready_for_planner=false`。

### 接口

- `POST /api/v30/copilot/turn`

### 依赖

- Router 判定
- Session Memory 读写
- 本阶段不要调 Registry（数据需求用内置通用建议即可；医学可用静态提示，不写死 accession）
- 不要调 `ResearchAgentService`
- 不要写合同

### ready 条件（第一阶段从严）

同时满足才为 true：

1. 已有研究对象
2. 用户已回答至少一个关键澄清（研究重点、结局类型、或明确“按默认疗效预测继续”）
3. route 不是 CHAT / CONCEPT_QA
4. 用户本轮或上一轮明确接受进入方案（或前端点了“生成方案”且 Memory 已有确认回答）

## 3. Session Memory（最小）

第一阶段只支持三桶，不做失败检索档案、不做跨天持久、不做用户画像。

| 桶 | 内容 | 示例 |
|---|---|---|
| goal | 对象、目标、领域 | HER2 阳性乳腺癌；耐药；oncology |
| clarifications | 问题-回答对 | 重点=疗效预测 |
| constraints | 用户约束原文 + 规范化短标签 | 只要公开数据；不要细胞系（若已说） |

### 输入 / 输出

- 创建：`POST /api/v30/sessions` → 新 `session_id`
- 读取：`GET /api/v30/sessions/{id}/memory`
- 更新：仅由 Copilot 的 `memory_patches` 写入，禁止前端任意 PATCH 覆盖历史

### 生命周期

- 进程内为主，可附带过期时间
- “新建研究”必须新 session
- 不继承上一 session 的 clarifications
- 不存 API Key
- 不存数据集行

### 依赖

- 无旧模块。不要复用千问 SessionRegistry 存研究记忆（那是密钥会话）。

## 4. Planner 门面

### 输入

- `session_id`
- 必须已 `ready_for_planner=true`
- 可选 `question_override`

### 输出

- 转调现有服务后的合同视图：候选问题或 FrozenResearchContract 的兼容摘要
- `compiled_from_session`：true
- 肿瘤路径：内部调用 `RequirementAgent.clarify` / `create_contract` 等价能力，不复制合同规则
- 本阶段可不做通用学科正式合同，unknown 领域只返回“方案草稿 + 仍需确认领域”，不得冒充已冻结医学合同

### 接口

- `POST /api/v30/plan`
- 未 ready：422
- CHAT session 调用：422

### 依赖

- `RequirementAgentService`
- `ResearchPlanningService` / V2（只调用，不改内部）
- Oncology 编译：第一阶段可用“直接走现有 clarify，把 Copilot 复述后的问题句当作 topic”
- 不依赖新 Schema Generator（Phase 3）
- 不自动 freeze 除非沿用现有 freeze API 的 confirmed=true

### 与旧接口关系

旧 `/api/v3/research/clarify` 保持可直接调用，作为评测和兼容后门。Phase 1 不删除、不改其字段。

## 5. 前端接线（有限）

规划工作台：

- 发送先走 `/route` + `/copilot/turn`
- 展示理解 / 需求建议 / 澄清问题
- 用户回答作为新 turn
- “生成方案”才打 `/plan`
- 保留进入高级工作台、直接运行旧协议的入口

不要在 Phase 1 重做整个 UI。

## 6. Phase 1 测试与验收

新功能有效：

- 你好 → CHAT，无 session 研究目标，无 plan
- 什么是 HER2 → CONCEPT_QA，无 Adapter 调用
- 耐药机制 → 有复述和提问，ready=false
- 回答疗效预测 → Memory.goal/clarifications 更新，允许 plan
- 新建研究 → 空记忆

医学未损坏：

- Phase 0 回归全绿
- `test_v3_api.py`、`test_requirement_agent.py`、`test_research_agent.py` 通过
- 旧工作台直连任务仍能完成

完成标准：

1. `/api/v30/copilot/turn` 能复现 V3.1 文档中的 HER2 示例结构
2. 无 ready 不能 plan
3. 旧医学入口行为与 Phase 0 快照一致
4. 冻结文件无 diff
5. 没有调用 Adapter 的自动路径被 Copilot 打开

---

# 第五部分：后续阶段设计

## Phase 2：Universal Source Registry + Discovery

### 为什么现在做

Phase 1 解决“先对话再规划”。此时 Discovery 若仍在代码里写死肿瘤库，系统看起来仍是医学工具。Registry 把来源变成插件，才能在不写新 Adapter 的前提下声明通用发现。

### 如何和已有代码连接

```text
v30/registry 读取 configs/v30/source_registry/*.yaml
医学条目 fetch_binding = 现有工具名
    search_gdc / search_geo / search_cbioportal / search_trials / search_civic / search_europe_pmc
Discovery 门面
    调用旧 SourceDiscovery、GEO catalog、Europe PMC、accession harvest
    再把候选交给旧 SourceBroker / WeightedSetCoverOptimizer
Execution 仍未在本阶段强制自动跑
    若做 integrate 预览，只允许列出将调用的旧工具名
```

连接禁忌：不把 GSE25066 等示范队列写进通用注册表当真理；它们留在旧 GoalLoop。

## Phase 3：Dynamic Schema Generator

### 为什么现在做

有了合同和领域之后，才需要目标字段集。若在 Copilot 阶段就生成 schema，会把未澄清问题冻成假字段。医学必须先能稳定绑定冻结 pack，再开放通用生成。

### 如何和已有代码连接

```text
Generator
  oncology 患者级 → schema_pack 指向 configs/canonical_schema.yaml（只读）
  通用 → 任务级字段列表 + 强制溯源三件套
v30 融合桥
  调用现有 SchemaMatcher，传入目标字段名列表
  不修改 matcher 内部相似度 / 阈值算法
Quality
  医学记录仍走旧 Quality Gate
  通用记录只走 provenance 规则包选择器（V3.0 已设计，不改 medical_rules 文件）
```

## Phase 4：Evidence Graph

### 为什么现在做

前面几期已经有 session、合同、候选、（可选）pack。这时做图，才有真实节点可投影。过早做图会再造一套展示数据。

### 如何和已有代码连接

```text
投影来源（只读）
  ScientificGraphStore 规划图
  EvidenceBuilder 的 EvidenceCell
  AgentTaskResult 的 tool_calls / sources / quality
  Session Memory 的约束（标注为用户约束，不是数据证据）
查询给
  Copilot 回述
  前端溯源
  导出附加快照
禁止
  图边触发 PatientSampleLinker
```

## Phase 5：Multimodal Figure Understanding

### 为什么现在做

安全抽取必须先有 source_id 与合同/文件上下文。图理解是展示能力，放在可信链路稳定之后，避免评委阶段系统还不能诚实取数，却先强调“能看图”。

### 如何和已有代码连接

```text
extract → 现有 ParserRegistry.parse
论文表 → 现有 extract_paper_assets / JATS
caption → 现有 figure_caption
understand → 新理解卡写入 Graph
主表 → 仍只来自 DatasetBuilder / 表格 ParsedRecord
```

不连接：任何“读像素写主表”的函数。该路径 Phase 6 以前视为不存在。

---

# 第六部分：文件目录规划

不移动、不重命名旧文件。旧导入路径保持不变。

```text
backend/app/v30/
  __init__.py              导出门面类型与 mount 函数
  api.py                   只挂载 /api/v30，转调各 service
  runtime.py               按 Router 结果编排，不含医学策略
  models.py                RouteDecision / CopilotTurn / MemorySnapshot / 通用合同视图
  router/
    service.py             分流
    rules.py               无模型规则
  copilot/
    service.py             理解、建议、澄清、ready 判定
  memory/
    service.py             最小三桶记忆
    store.py               进程内 session 存储
  planner/
    service.py             ready 后转调 RequirementAgent / Planning
    oncology_compile.py    问题句/Memory → 现有 topic/clarify（只编不造字段语义）
  registry/                Phase 2
    service.py
    loader.py
  discovery/               Phase 2
    service.py
  schema_generator/        Phase 3
    service.py
    packs.py
  graph/                   Phase 4
    service.py
    projection.py
  extraction/              Phase 5
    service.py
  figures/                 Phase 5
    service.py
  bridges/
    execution.py           转调 ResearchAgentService（Phase 2 末或需要时再启用）
    source_broker.py
    parsers.py
    quality.py             只读转调

backend/tests/v30/
  test_router.py
  test_copilot.py
  test_memory_isolation.py
  test_planner_ready_gate.py
  test_v30_api.py
  test_oncology_regression_bridge.py
  test_registry.py         Phase 2+
  test_discovery_honesty.py
  test_schema_pack.py      Phase 3+
  test_graph_constraints.py
  test_figures_not_in_primary.py

configs/v30/
  router_rules.yaml
  source_registry/         Phase 2
    oncology.yaml
    astronomy.yaml
    materials.yaml
  schema_packs.yaml        Phase 3 索引

docs/v31_baseline/         Phase 0
  API_SNAPSHOT.md
  REGRESSION.md
  OUTPUT_CONTRACT.md
```

目录职责一句话：

- `v30`：新智能层唯一住所
- `tests/v30`：只测旁路契约与“不能破坏旧行为”
- `configs/v30`：可替换插件配置，不覆盖冻结 configs 根文件
- 旧 `backend/app/agent`、`sources`、`integration`、`quality_v2`：原地不动

前端不新开独立应用。只在现有 `frontend/` 增加调用，不搬文件。

---

# 第七部分：风险分析

## 1. 哪些地方容易破坏已有医学能力

| 风险点 | 为何危险 | 防护 |
|---|---|---|
| 改 `ResearchAgentService.run` 塞 Copilot | 主过程已过长，回归面最大 | 禁止。只允许 ExecutionBridge 外部调用 |
| `main.py` 改旧 handler 签名 | 工作台与评测立刻断 | 只追加 mount |
| Planner 门面复制一套合同字段 | 与 RequirementAgent 漂移 | 只转调 |
| Schema Generator 改冻结 yaml | 医学语义与 Gold Set 一起坏 | Phase 0 校验和检查 |
| Discovery 把 catalog 当覆盖 | 质量门被前端误报通过 | 强制 verification_status |
| 用户排除 METABRIC 被写进 Adapter | 内核出现会话状态 | 排除只存在 Memory / Discovery 过滤 |
| Matcher 换目标时改内部阈值 | 公开字段匹配成绩不可比 | 只换目标清单 |
| 前端去掉旧“运行协议” | Demo 回退能力丢失 | 旧入口始终保留 |
| 用新测试改旧期望 | 静默丢失医学约束 | 禁止改旧测试金值 |

## 2. 哪些地方容易过度 Agent 化

| 倾向 | 后果 | 约束 |
|---|---|---|
| Copilot 直接选 GSE 并取数 | 回到固定流水线，且绕过澄清 | Phase 1 无 integrate |
| Router 输出 INTEGRATE | 闲聊或半句研究被开跑 | Phase 1 路由集合不含 INTEGRATE |
| 长期记忆当事实 | 上一题患者表污染下一题 | 记忆只存目标/回答/约束 |
| 模型生成主表行 | 失去可信工厂 | 新层不得写 CanonicalRecord |
| 图理解数字入库 | 赛题加分、科学作假 | `enters_primary_table=false` |
| 通用 Agent 重写 Adapter | 官方事实边界消失 | Adapter 只读调用 |
| 让 Copilot 宣布 PASS | 质量门名存实亡 | 回述必须引用 Quality 枚举 |

## 3. 哪些地方需要人工确认

| 事项 | 谁确认 | 不确认则如何 |
|---|---|---|
| 进入 Planner / 冻结合同 | 用户 | 停在澄清 |
| 医学高风险字段自动定值 | 规则 + 必要时审核队列 | REVIEW，不得 Positive 猜 IHC 2+ |
| 通用 schema_pack 从 DRAFT 到 READY | 用户或评审 | 不对齐主表 |
| catalog 候选升格为已取数 | Adapter 运行时核验 | 保持 catalog_only |
| 图像数字化入库 | Phase 6 + 人工 | 第一至五阶段不允许 |
| 跨研究身份合并 | 永不自动，只审核 | unresolved |
| 正式 SDTI 发布 | 冻结 Gold Set 流程 | `publish_allowed=false` |
| 把 planned 天文源写成已支持 API | 产品负责人 | 界面必须标 planned |

---

# 第八部分：第一个开发任务拆解

以下是**第一个开发任务**，不是整个 Phase 1 一次做完。  
范围：**Phase 1 的第一刀 = Research Copilot + Router**（含最小 Memory，以便 Copilot 能跨一轮澄清）。  
本刀**不做** Planner 门面、不做前端大改、不做 Registry、不挂 integrate。

Planner 作为 Phase 1 第二刀，等本刀测试全绿再开。

## 需要创建的文件列表

新增：

- `backend/app/v30/__init__.py`
- `backend/app/v30/models.py`
- `backend/app/v30/api.py`（本刀只挂 route / copilot / sessions / memory）
- `backend/app/v30/runtime.py`（本刀只串 Router → Copilot → Memory）
- `backend/app/v30/router/service.py`
- `backend/app/v30/router/rules.py`
- `backend/app/v30/copilot/service.py`
- `backend/app/v30/memory/service.py`
- `backend/app/v30/memory/store.py`
- `configs/v30/router_rules.yaml`
- `backend/tests/v30/test_router.py`
- `backend/tests/v30/test_copilot.py`
- `backend/tests/v30/test_memory_isolation.py`
- `backend/tests/v30/test_v30_api.py`

允许的最小修改：

- `backend/app/main.py`：导入并 `mount_v30_routes(app)`，不改旧函数体

本刀不要创建：

- `planner/`
- `registry/`、`discovery/`、`schema_generator/`、`graph/`、`figures/`
- 任何 Adapter / Matcher / Quality 改动

## 开发顺序

1. 确认 Phase 0 基线文档已存在且回归刚跑过（若还没有，先做 Phase 0，不要开始本刀）。
2. 建立 `feat/v31-phase1-copilot`。
3. 写 `models.py`：RouteDecision、CopilotTurnRequest/Response、MemorySnapshot。
4. 写 `memory/store.py` 与 `memory/service.py`：创建、读取、按 session 打补丁。
5. 写 `router/rules.py` 与 `router/service.py`：CHAT / CONCEPT_QA / CLARIFY / PLAN。
6. 写 `copilot/service.py`：结构化理解、数据需求建议、澄清、ready=false（本刀即使信息较全，默认仍 false，除非澄清已答；本刀可不接 Planner）。
7. 写 `runtime.py`：先 route，再 copilot，再写 memory。
8. 写 `api.py` 与 `main.py` 挂载。
9. 写测试并只跑 `backend/tests/v30` + Phase 0 回归。
10. 不改前端也可验收 API；前端接线放到本刀之后或 Phase 1 第二刀。

## 测试案例

Router：

1. “你好” → `CHAT`，fallback 可为 true
2. “什么是 HER2” → `CONCEPT_QA`
3. “什么是红移” → `CONCEPT_QA`，domain 不是 oncology 也可
4. “我想研究 HER2 阳性乳腺癌耐药机制” → `CLARIFY`，domain=`oncology`
5. 空字符串 → 不进入 CLARIFY，不创建研究目标

Copilot：

6. 在案例 4 之后：回复含研究对象 HER2 阳性乳腺癌、目标含耐药、数据需求含临床/表达/突变/药敏一类建议、并提问机制还是疗效预测
7. 建议必须标明尚未检索，不得出现具体假造 GSE 已找到
8. 案例 1 的 Copilot：`blocked_reason` 非空，`ready_for_planner=false`，不写 goal
9. 用户第二轮答“疗效预测”：Memory.clarifications 含该回答，goal 仍在同一 session
10. 本刀不提供 `/plan`；若误挂，测试应不存在该成功路径，或存在则必须 404/未实现

Memory：

11. 两个 session 并行，A 的约束不会出现在 B
12. 新建 session 记忆为空
13. 不接受把患者表行写入 memory 的接口（无此类字段）

挂载与回归：

14. `GET /health` 仍 200
15. OpenAPI 中旧 `/api/agent/tasks`、`/api/v3/research/clarify` 仍在
16. 运行 Phase 0 回归清单，通过数不低于基线
17. `git diff` 不含 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`backend/app/sources/`、Matcher 核心文件、Quality 逻辑文件、`docs/06_评测指标与SDTI.md`

---

# 收束

实施顺序不可颠倒：先保护，再对话闸门，再发现插件，再任务契约，再证据图，再图像演示。  
每一阶段的合并条件相同：**旁路新增可用，内核文件无改，医学回归与 Phase 0 基线一致。**

本文件只规划实施，不包含代码。
