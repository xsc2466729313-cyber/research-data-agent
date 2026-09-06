# Autonomous Research Agent 产品计划

- 日期：2026-09-05
- 状态：产品架构评审稿，暂不实施
- 范围：科研 AI Agent 的前端产品形态、任务编排体验、研究资产展示
- 本轮明确：不修改任何代码，不继续修补当前 Copilot 页面

## 1. 产品重新定义

当前系统已经具备较完整的科研能力链：

```text
Research Copilot
→ Planner
→ Source Discovery
→ Schema Mapping
→ Evidence Graph
→ Medical Integrate
```

但前端把这条能力链暴露成了“用户逐步填表”：

```text
确认研究方向
→ 确认下一步
→ 是否继续
→ 再确认
→ 再进入下一个页面
```

这会让用户感觉自己在操作系统，而不是让 Agent 帮自己完成研究。

最终产品不应是 Copilot 页面集合，而应是：

> 用户提交一个科研问题，Agent 自主完成一轮有边界、可追溯、可中断、可追问的研究运行，并交付可检查的科研数据资产。

Copilot 从“主流程”降级为三种能力：

- 研究问题入口；
- 运行过程中的解释与追问入口；
- 用户修改方向后的重规划入口。

## 2. 当前前端问题分析

### 2.1 Copilot 是确认机器，不是研究 Agent

当前 `copilot.js` 的核心循环是：提交一句话、等待一个 turn、展示澄清卡、等待用户选择、再提交下一轮。`ready_for_planner` 之前，用户必须不断推动系统。

这把后端的安全门直接变成了用户任务清单。安全判断本应由 Agent 和规则层自动完成，只有高风险决策才需要用户介入。

### 2.2 页面按工程模块拆分，用户目标被拆散

Copilot、Timeline、Sources、Mapping、Graph 是能力模块，不是用户心智中的研究任务。用户想回答的是：

- Agent 理解了什么？
- Agent 找到了哪些证据？
- 研究数据资产是否可信？
- 我还可以改变什么？

而当前界面要求用户自己跨页面推动能力链。

### 2.3 八步流程成为主导航

Timeline 当前更像 API 事件和阶段门的工程审计页。它适合复核，不适合成为普通用户的主导航。左侧不应让用户感觉自己需要“完成八步表单”。

### 2.4 研究槽与真实任务不等价

当前 v31 前端通过 `workspace-store` 在浏览器内缓存多个 session 快照，已经能完成同标签页内的基础隔离；但这仍然是前端运行时状态：

- `session_id` 是后端 Memory 容器，不是完整的产品级 Research Project。
- 后端目前没有研究目录、运行任务、turn history、资产目录和跨刷新 timeline API。
- `conversationLog` 和部分 Timeline 是前端本地投影，刷新后无法保证完整恢复。

因此，真正的“研究历史、多任务切换、结果资产回看”需要在产品模型上区分 `research_id`、`run_id`、`session_id` 和 `asset_id`，不能继续把所有东西塞进一个 session。

### 2.5 结果能力没有成为终点

当前 Sources、Mapping、Graph 的结果停留在各自页面，用户看到了过程部件，却没有一个“研究资产交付面”把以下内容合在一起：

- 可下载的 CSV；
- Metadata；
- Evidence Graph；
- Source lineage；
- 质量门和未解决风险。

科研用户最终要带走的是资产，而不是一串页面浏览记录。

## 3. 最终产品形态

产品形态采用“ChatGPT Deep Research 的自主运行感 + Elicit 的结构化证据与数据资产感”：

```text
Research Home
├── Recent Research / Research History
├── New Research：一句科研问题
└── Workspace Switcher

Research Workspace
├── 左：研究与任务列表
├── 中：Research Run / Conversation
│   ├── 用户问题
│   ├── Agent 研究计划
│   ├── 自动执行过程
│   ├── 证据与中间发现
│   ├── 研究结论/资产摘要
│   └── 追问与修改入口
└── 右：Research Brief / Summary
    ├── 研究对象
    ├── 研究目标
    ├── 当前运行状态
    ├── 已确认假设
    ├── 未解决风险
    └── 下一步建议

Research Assets
├── CSV / Dataset
├── Metadata
├── Evidence Graph
└── Source Lineage
```

核心原则：

1. 用户只需提供初始问题，Agent 默认自动推进。
2. 用户可以观察、追问、暂停、修改方向，但不需要为每一个普通阶段点击确认。
3. 工程状态保留可审计性，但默认转译成研究语言。
4. 所有自动化都必须是可解释、可回溯、可中断的。

## 4. 页面信息架构

### 4.1 Research Home

首页不再是 Copilot 介绍页，也不展示八步流程。首页只做三件事：

- 输入一句科研问题；
- 继续最近的研究；
- 新建或切换研究任务。

主输入示例：

> 我想研究 Ia 型超新星光变曲线

提交后立即创建一次 Research Run，并进入运行中的 Workspace。首页不要求用户预先选择领域、方向或数据源。

### 4.2 Research Workspace

Workspace 是产品主页面，而不是 Copilot 页面升级版。

中间区域使用研究运行流：

1. Research Question：用户原始问题。
2. Agent Understanding：Agent 对对象、目标、范围的理解。
3. Research Plan：Agent 自动生成的研究路径，默认直接开始执行。
4. Live Research Progress：正在搜索、整理、映射、构图、生成资产。
5. Findings：阶段性发现和证据卡片。
6. Research Output：资产摘要、风险、可下载结果。
7. Follow-up：继续追问或要求修改研究范围。

这些不是必须逐步点击的页面，而是同一个研究运行中的可展开区块。

### 4.3 Research Progress

Progress 是可观察的运行状态，不是用户必须完成的流程：

- 默认展示当前正在做什么；
- 已完成步骤可展开；
- 失败或需要确认的步骤明确说明原因；
- 用户可以暂停、重试、修改范围；
- 普通完成状态不要求用户点“继续”。

工程 Timeline 继续保留，作为审计模式或详情 Drawer，不作为第一层主导航。

### 4.4 Research Assets

当 Agent 生成资产后，Workspace 的主关注点从“运行过程”切换为“结果资产”。资产页不是简单下载页，而是研究交付面：

- 先给结论和资产状态；
- 再给结构化数据；
- 再给证据、来源和 lineage；
- 最后给未解决问题与质量限制。

## 5. 用户完整流程

### 5.1 正常自主路径

```text
输入一句科研问题
  → 创建 Research Project / Research Run
  → Agent 理解对象、目标、领域和边界
  → 自动生成研究计划
  → 自动发现来源
  → 自动生成任务级字段体系
  → 自动执行可逆、只读、低风险的检索与整理
  → 自动生成字段映射和证据链
  → 自动运行质量与医学安全规则
  → 生成 CSV / Metadata / Evidence Graph / Source Lineage
  → 展示资产、风险和可继续追问入口
```

用户可以在任意阶段：

- 查看 Agent 正在做什么；
- 追问“为什么选这个来源”；
- 修改研究对象、目标、范围或约束；
- 暂停或取消当前运行；
- 要求基于新约束重新规划。

### 5.2 研究问题不完整时

Agent 不应立即把用户挡在确认页。默认策略：

1. 用当前最合理解释生成一个“工作假设”；
2. 先完成低风险的来源发现和证据探索；
3. 把不确定点标记为 `assumption` 或 `needs_review`；
4. 只有当歧义会改变研究对象、数据域或医学安全边界时，才暂停并问一个问题。

例如“研究 Ia 型超新星光变曲线”可以先自动规划光变参数、观测时间、波段、红移和数据来源，而不必先逼问用户选择“机制探索还是疗效预测”。

### 5.3 用户修改方向

用户输入：

> 把重点改成光变曲线和红移的关系，只保留公开数据。

Agent 应生成新的研究分支或新 Run：

- 保留原 Run 作为历史；
- 标记哪些计划、字段和来源受到影响；
- 自动重算受影响部分；
- 不静默覆盖旧资产；
- 允许用户比较两个 Run 的差异。

### 5.4 高风险路径

如果运行涉及真实 Medical Integrate、患者级连接、发布或可能造成不可逆外部影响，Agent 自动执行到安全门前，然后请求一次明确确认，并解释：

- 将执行什么；
- 会涉及哪些来源和数据范围；
- 哪些医学规则已通过；
- 哪些风险仍未解决。

## 6. Agent 自主执行流程

建议将 Agent 运行抽象为以下状态，而不是把内部模块直接映射成用户页面：

| Agent 状态 | 用户文案 | 主要动作 |
|---|---|---|
| `intake` | 正在理解研究问题 | 解析对象、目标、领域、限制 |
| `hypothesis_ready` | 已形成初步研究假设 | 记录假设与不确定点 |
| `planning` | 正在规划研究路径 | 选择数据需求、来源策略、字段目标 |
| `discovering` | 正在寻找可用来源 | Registry、Discovery、来源验证 |
| `structuring` | 正在建立数据结构 | Schema Pack、字段体系、响应域 |
| `retrieving` | 正在整理可追溯数据 | 仅调用允许的只读/真实 Adapter |
| `linking` | 正在建立证据链 | Mapping、Evidence、Graph |
| `quality_review` | 正在进行质量与安全检查 | Quality Gate、医学规则、可发布性 |
| `needs_confirmation` | 有一项高风险决策需要确认 | 暂停并展示具体风险 |
| `completed` | 研究资产已生成 | 展示资产、来源和限制 |
| `blocked` | 运行被规则阻断 | 说明阻断理由和可选修复 |

### 6.1 自主编排原则

- 每一步由前一步的真实输出触发，不靠用户点击推动。
- 可并行的只读来源检索可以并行；有共享写入或实体连接风险的步骤必须串行并受规则门控制。
- 每次自动决策记录 `decision`、输入、来源和理由。
- Agent 不生成不存在的数据行，不把计划当成结果，不把候选当成覆盖。
- 一旦用户修改目标，创建新的运行版本或明确的变更记录，不能覆盖旧证据。

## 7. Research Workspace 设计

### 7.1 左侧：研究与运行列表

左侧不列八步流程，而列用户真正维护的对象：

```text
我的研究

HER2 耐药机制
  当前运行 · 已生成数据资产

Ia 型超新星光变曲线
  运行中 · 正在建立证据链

+ 新建研究
```

研究项下可折叠显示运行版本：

- Run 1：初始问题；
- Run 2：修改红移分析范围；
- Run 3：只保留公开数据。

默认进入最近一次未完成或最近一次成功的 Run。

### 7.2 中间：自主运行与追问

中间区域不是聊天气泡堆，也不是表单。推荐采用纵向研究流：

- 顶部是原始问题和当前研究标题；
- 下面是 Agent 的理解与工作假设；
- 中段是自动运行的阶段卡；
- 阶段卡可展开查看来源、字段和证据；
- 结果完成后，资产摘要置于运行流末端；
- 底部只有一个“继续追问 / 修改研究范围”入口。

### 7.3 右侧：Research Brief

右侧始终提供低干扰摘要：

- 研究对象；
- 研究目标；
- 当前 Run 状态；
- 当前使用的数据域；
- 已确认假设；
- 未解决风险；
- 资产数量和质量状态；
- “查看完整来源链”入口。

工程字段进入折叠详情，不直接占据摘要：`route`、`retrieval_status`、`constraints`、raw API 状态、内部组件名等。

## 8. 研究历史、多任务切换设计

### 8.1 产品对象层级

```text
Research Workspace
└── Research Project
    ├── Research Question
    ├── Research Run 1
    │   ├── session_id
    │   ├── conversation history
    │   ├── plan
    │   ├── evidence
    │   └── assets
    ├── Research Run 2
    └── Project Summary
```

建议对象语义：

- `research_id`：用户认知中的一项长期研究。
- `run_id`：该研究的一次自动执行或重新规划版本。
- `session_id`：当前后端 Copilot/Memory 上下文，绑定到一个 Run。
- `asset_id`：CSV、Metadata、Graph 等产物。

当前 v30 的 `session_id` 可以作为 Run 的临时技术身份，但不能继续承担长期 Research Project 的全部职责。

### 8.2 切换规则

- 切换研究只切换 active Research Project，不改变其它研究状态。
- 切换运行版本时，所有 conversation、plan、evidence、asset 必须来自该 Run。
- 任何异步回包必须带 `research_id + run_id + session_id` 进行归属校验。
- 旧 Run 默认只读；用户修改方向时产生新 Run，而不是覆盖旧 Run。
- 研究历史显示“最近进展”和“最近资产”，不显示大量工程日志。

### 8.3 持久化要求

要实现真正的历史、跨刷新和跨设备工作空间，后端最终需要提供：

- Research Project 创建、列表、读取；
- Run 创建、状态、取消、恢复；
- Conversation/Research Event 历史；
- Asset 目录与版本；
- Source lineage 和 Evidence 查询；
- 运行状态流或可轮询任务接口。

在这些接口存在前，前端只能诚实地提供当前浏览器运行时的多任务切换，不能宣传为持久化 Research History。

## 9. 结果资产页面设计

结果资产统一进入 Research Assets，而不是散落在 Mapping、Graph、旧导出接口中。

### 9.1 CSV / Dataset

页面首屏展示：

- 资产名称与研究问题；
- 行数、字段数、数据域、队列/实体类型；
- `PASS / REVIEW / REJECT` 或等价质量状态；
- 是否允许导出；
- 最后更新时间与 Run 版本。

表格区展示字段字典和少量预览行。每个关键字段可追溯到：

- `source_id`；
- `raw_field`；
- `raw_value`；
- Evidence 状态；
- confidence；
- review 原因。

CSV 下载是资产导出，不代表质量门自动通过。

### 9.2 Metadata

Metadata 页面给机器和研究者同时使用，至少包含：

- 原始研究问题；
- Agent 理解与工作假设；
- 研究目标、领域、response_domain；
- 运行版本、生成时间、组件/模型版本；
- 字段体系与 schema 版本；
- 来源列表与 source_id；
- 变换、映射、过滤、排除规则；
- 质量门结果；
- 未解决项和人工确认记录。

### 9.3 Evidence Graph

Evidence Graph 不是独立炫技页面，而是资产的解释视图：

```text
Research Question
  → Research Contract / Goal
  → Source Candidate
  → Selected Source
  → Schema Field
  → Field Mapping
  → Evidence / Quality Finding
  → Dataset Field / Asset
```

用户可点一个字段或质量问题查看 Why Drawer：

- 为什么使用这个来源；
- 为什么字段被映射到该 canonical field；
- 为什么状态是 `REVIEW`；
- 哪些边界阻止了自动合并。

禁止用图替代真实 Evidence，也禁止生成患者关系边或跨研究实体 Join。

### 9.4 Source Lineage

Source lineage 是资产的来源链，不是来源列表：

```text
真实来源
→ Registry 能力
→ Discovery 候选
→ Selection 选择/排除理由
→ Schema 字段需求
→ Mapping 字段映射
→ Evidence 单元
→ Dataset / CSV 字段
```

每个来源节点展示：

- source_key / source_id；
- 官方入口或 accession；
- verification_status；
- fetched / integrated 状态；
- 使用了哪些字段；
- 被排除的原因或 join risk；
- 是否进入最终资产。

## 10. 自动完成与用户确认边界

### 10.1 默认自动完成

以下步骤原则上不应要求用户逐步确认：

- 初步意图识别和领域判断；
- 生成工作假设；
- 生成研究计划；
- Registry 查询与候选来源发现；
- 低风险、只读、可追溯的来源检索；
- 任务级字段体系生成；
- Schema Pack 和字段映射预览；
- Evidence Graph 投影；
- Source lineage 生成；
- 质量规则和医学规则检查；
- 生成草稿 CSV、Metadata、Graph 和 lineage；
- 无副作用的重试、补搜和低风险重算。

### 10.2 必须确认或暂停

以下场景必须保留用户确认或人工 Review：

- 研究对象存在多个同等合理解释，且会改变数据域或结论含义；
- 高权威来源之间出现无法自动解释的冲突；
- 低置信度患者/样本关联；
- 任何跨研究、跨队列患者级 Join；
- HER2 IHC 2+、ERBB2 CNA 等医学语义可能被错误归一化；
- 将细胞系 AUC/IC50 与患者 response/pCR 放到同一解释域；
- 真实 Medical Integrate 或有外部副作用的执行；
- 质量门为 REVIEW/REJECT 但用户要求导出为正式结果；
- 缺少来源、raw 字段或 Evidence 的关键字段；
- 用户主动要求改变研究目标、删除证据或覆盖旧资产。

确认应当是“一个高价值决策”，而不是“下一步继续”。确认卡必须说明决策影响、证据和风险。

## 11. 如何保持科研可信性

### 11.1 过程诚实

界面必须区分：

- Agent 计划了什么；
- 实际调用了什么；
- 找到了什么；
- 哪些仍是候选或假设；
- 哪些字段进入了资产；
- 哪些步骤被规则阻断。

禁止把计划、候选、Schema、Graph 投影显示成已生成真实科研数据。

### 11.2 来源与可追溯性

所有外部数据必须保留真实 `source_id`，标准化后必须保留 `raw_field` 和 `raw_value`。资产字段、Evidence、Source lineage 之间必须可反向追踪。

### 11.3 医学安全

- HER2 IHC 2+ 不得自动判定为 HER2 Positive。
- ERBB2 CNA amplification 与 HER2 IHC positive 保持独立维度。
- 低置信度患者/样本关联进入 unresolved/review。
- 高权威来源冲突不自动选边。
- `response_domain` 明确区分 clinical、preclinical_cell_line、clinical_trial、knowledge_evidence。

### 11.4 资产版本与审计

每个资产必须绑定研究、Run、生成时间、来源链、schema 版本和质量状态。用户改变方向时生成新版本，保留旧版本和差异说明。

### 11.5 Agent 的自主不等于无监督

自主执行的边界由规则、质量门、来源验证和高风险确认共同定义。Agent 可以减少普通确认，但不能绕过医学规则、Evidence、质量门或用户对高风险决策的授权。

## 12. 产品落地优先级

### Phase 1：自主运行壳

- 单输入启动 Research Run；
- 中间区域改为运行流；
- 普通澄清不阻塞自动计划；
- 研究过程、阶段状态和用户追问进入同一 Workspace。

### Phase 2：任务与历史模型

- Research Project / Run / Session 分层；
- 多研究和多 Run 切换；
- 运行取消、恢复、重试、分支；
- 研究历史和最近资产。

### Phase 3：资产中心

- CSV 预览与导出；
- Metadata；
- Evidence Graph；
- Source lineage；
- 质量门和未解决项统一呈现。

### Phase 4：高风险确认与可信协作

- 风险驱动确认卡；
- 人工 Review 队列；
- 资产版本比较；
- 研究过程和证据审计导出。

## 13. 产品验收标准

1. 用户只输入一句“我想研究 Ia 型超新星光变曲线”，系统可以自动进入研究运行，不要求先选择研究方向。
2. Agent 能自动展示理解、计划、来源发现、字段体系、证据链和资产生成进展。
3. 用户不需要为普通阶段连续点击“下一步”。
4. 用户可以在运行中追问、暂停、修改方向，并产生可比较的新 Run。
5. HER2 与 Ia 型超新星可以并行维护，研究、运行、资产和上下文不互相污染。
6. 结果中心可以统一查看 CSV、Metadata、Evidence Graph 和 Source lineage。
7. 所有资产都能追溯到真实来源、原始字段和证据状态。
8. 高风险医学决策、患者级连接、真实执行和不可逆动作仍然要求确认或 Review。
9. 系统不会把候选来源、计划、映射或图投影伪装成已生成的真实科研结论。

## 14. 需要架构确认的关键问题

本计划建议先确认以下产品方向，再进入技术拆解：

1. 是否接受“默认自主推进，风险驱动暂停”，替代当前“每阶段人工确认”？
2. 是否接受把 `Research Project / Research Run / session_id / asset_id` 分层，而不再把一个 session 当作完整研究？
3. 是否接受把 Copilot、Timeline、Sources、Mapping、Graph 组合进一个 Research Workspace，而不是继续作为并列主页面？
4. 是否接受补充研究目录、运行状态、资产和历史所需的后端持久化契约？当前 v30 session 本身不足以承载真正的跨刷新/跨设备历史。
5. 是否将真实 Medical Integrate、患者级连接、发布和正式导出定义为风险确认点，而把低风险读取、规划和证据整理默认自动化？

确认这些产品原则后，再分别拆分前端壳、Agent orchestration API、Research history API 和资产中心的实施计划。
