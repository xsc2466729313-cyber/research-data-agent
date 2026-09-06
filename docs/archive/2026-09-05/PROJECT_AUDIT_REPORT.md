# 项目架构审计报告

- 项目：research-data-agent（仓库显示名：科研数据智能体）
- 审计角色：资深 AI Agent 系统架构师 / 科研软件架构评审
- 审计日期：2026-09-05
- 审计范围：README、文档、目录、后端、前端、Agent、数据处理、数据源连接、测试
- 审计原则：只理解现状，不修改代码，不重构，不提出大规模推倒重来方案
- 结论性质：系统级架构审计，作为后续升级为“通用科研数据智能体”的依据，不是实施计划

---

# 第一部分：项目定位分析

## 1. 当前项目解决什么问题？

当前项目解决的不是“替研究者写论文”或“给出诊疗建议”，而是：

**把自然语言科研问题，转成一份可分析、可追溯、可审计、可下载的公开科研数据包。**

典型问题不是“数据在哪下载”，而是三类更硬的问题：

1. 问题有没有被拆成可检索的研究对象、暴露、结局、字段和数据粒度。
2. 目标变量是否真的存在于某个可核验的公开队列中，而不是只存在于摘要措辞里。
3. 多源数据能否被整理成标准表，同时阻止错误合并、错误语义和不可追溯发布。

系统明确不做：全医学领域泛化、影像诊断、WSI 训练、完整生物医学知识图谱、自动写论文、临床决策支持。

一句话：它是**科研数据生产链**，不是问答助手，也不是临床系统。

## 2. 面向什么用户？

主用户是**肿瘤精准治疗方向的科研人员 / 研究生 / 数据整理人员**，不是临床医生，也不是通用实验室数据工程师。

用户画像可以再拆一层：

| 用户 | 实际使用入口 | 他们真正要的东西 |
|---|---|---|
| 研究者 / 研究生 | 规划工作台 | 从宽泛想法走到可执行研究方案和可下载表 |
| 技术评审 / 赛题评委 | 高级工作台、比赛对齐、导出 Excel | 过程可解释、来源可回查、质量门可阻断 |
| 开发与评测人员 | API、Gold Set、公开基准脚本 | 分层能力分数、消融、来源审计 |

系统对用户有一条硬边界：不生成诊疗建议，不把相关性说成因果，不把模型摘要当作患者事实。

## 3. 当前核心应用场景是什么？

生产主场景是：

> HER2 阳性乳腺癌中，PIK3CA 突变是否与新辅助治疗响应有关？

围绕这个场景，系统已经长成一条固定链路：

提出方向 → 检索论文 → 形成候选问题 → 冻结 Research Contract → 选择公开数据源 → Adapter 取数 → Schema/实体对齐 → 质量门 → 两轮闭环补搜 → 导出 CSV / Excel / Parquet。

乳腺癌是**专项验证场景**，不是唯一入口。系统已配置 17 个其他常见癌种的 GDC / cBioPortal 种子队列，并为未配置癌种保留 GEO、Europe PMC、ClinicalTrials.gov、CIViC 等通用发现入口。但专项规则、pCR/HER2 闭环、Gold Set 和正式观察成绩都围绕乳腺癌。

因此，当前产品能力是“肿瘤科研数据助手”，深度资产是“乳腺癌精准治疗数据治理”。

## 4. 当前项目更像哪一类？

选项：

- A. 数据平台
- B. Agent 系统
- C. 科研助手
- D. 数据处理工具

**审计结论：当前项目最像 C（科研助手），工程内核是 D（数据处理工具），外层包装为有边界的 B（Agent 系统）。它不是 A（通用数据平台）。**

理由：

1. **对用户呈现为科研助手。** 首页不是库表浏览器，而是“告诉我你想研究什么”。规划工作台把宽泛主题变成问题、方案、字段和来源准备。这是助手交互，不是平台控制台。
2. **对数据的真正工作是处理与治理。** 字段映射、患者/样本命名空间、response_domain 隔离、Evidence、质量门、导出数据包，这些才是系统真正交付的东西。没有这些，Agent 只是一层对话壳。
3. **Agent 是编排层，不是操作系统。** 生产主链确有主 Agent、规划、采集、批评、质量、闭环等角色，但多数名为 Agent 的组件是确定性 Python 控制器；大模型主要用于结构化解析、工具选择和摘要。系统自己也定义为“有边界的混合式多 Agent 编排”，并刻意把 Adapter、Matcher、医学规则排除在 Agent 之外。
4. **不是数据平台。** 没有多租户数据湖、没有长期业务库、没有通用接入控制台、没有任意领域的数据目录运营。仓库不携带 GB 级业务数据，Adapter 按需取数或读缓存。多癌种也只是肿瘤底座上的配置扩展，不是平台化数据产品。

如果必须选一个主标签：**C. 科研助手**。  
如果必须描述系统本质：**带 Agent 编排外壳的肿瘤科研数据处理与可信整合工具。**

这对后续升级很关键：不要把它当成“已经是通用 Agent OS”，也不要把它当成“只是几个爬虫脚本”。它的价值在数据治理，它的缺口在通用智能。

---

# 第二部分：当前系统架构

## 文字版架构图

当前仓库里同时存在“文档主线”和“运行时主链”。二者方向一致，但并不完全重合。下面以**实际运行时**为准。

```text
用户
  │  自然语言主题 / 科研问题 / 千问 API Key（会话内存）
  ↓
前端（两套界面）
  ├─ 规划工作台：提出方向 → 查找依据 → 明确问题 → 制定方案 → 准备数据
  └─ 高级工作台：运行研究协议、工具过程、质量门、分析矩阵、溯源、比赛对齐
  │
  ↓  REST API（FastAPI，同时托管静态前端）
API 层
  ├─ /api/research/*、/api/v3/research/*     规划与合同
  ├─ /api/agent/tasks、/api/v2/agent/closed-loop  主任务与两轮闭环
  ├─ /api/adapters/*                         单源 Adapter 直连
  ├─ /api/v2/schema|entity|quality|retrieval 能力层接口
  └─ /api/evaluation/*                       Gold Set / 官方评测
  │
  ↓
规划与合同层
  ├─ ResearchIntentAgent          主题拆解（规则/词典为主）
  ├─ LiteratureAgent              Europe PMC / Giiisp
  ├─ ResearchFormulationAgent     候选问题（证据 + 模板兜底）
  ├─ RequirementAgent             多视角澄清 + 冻结合同
  ├─ ResearchPlanningV2           证据抽取 / 变量设计
  └─ SourceBroker                 字段覆盖 + 加权集合覆盖选源
  │
  ↓
任务级主 Agent：ResearchAgentService
  ├─ QwenClient.extract_research_spec     问题 → ResearchSpec
  ├─ QwenClient.choose_tools / plan_next_tools
  ├─ FieldDrivenSearchPlanner             确定性检索计划
  ├─ CollectionAgent + GoalLoopController 缺口诊断与换方法
  └─ ClosedLoopService                    任务外两轮反馈
  │
  ↓
工具 / Adapter 层（确定性事实入口）
  ├─ GDC / GEO / cBioPortal / AACT / CIViC / DepMap
  ├─ DiscoveryAdapter：GEO 目录、BioSample、Europe PMC、论文表图注
  └─ ParserRegistry：CSV/TSV、Excel、HTML 表、JATS、PDF 文本层
  │
  ↓
整合与治理层（确定性）
  ├─ ResearchDatasetBuilder       把 Adapter 结果建成患者/样本宽表
  ├─ SchemaMapper / SchemaMatcher 字段对齐，保留 raw_field / raw_value
  ├─ PatientSampleLinker          身份关联，低置信度 unresolved
  ├─ EvidenceBuilder              字段级 Evidence
  ├─ biomarker / gene / drug 归一化
  └─ medical_rules.yaml + RulePackEngine + SafetyLayer
  │
  ↓
审查与发布层
  ├─ CriticAgent           合同缺口诊断（不改数据）
  ├─ QualityAgent / QualityV2 / QualityGate  PASS / REVIEW / FAIL
  └─ RepairLoop            仅低风险、有依据的自动修复
  │
  ↓
输出
  ├─ 主科研数据集、字段字典、质量报告、来源清单
  ├─ Excel / CSV / Parquet 导出
  ├─ 前端溯源图、比赛对齐诊断
  └─ Gold Set 观察成绩（当前 publish_allowed=false）
```

文档中的三层划分仍然成立，可作为理解框架：

1. 科研需求与数据发现
2. 多源数据处理与融合
3. 质量闭环与科研输出

需要纠正的一点：`ResearchOrchestrator` 在文档中像总控路由，但代码中它基本只被测试调用，**生产总控是 `ResearchAgentService.run()`**。规划工作台走 Research Planning / Requirement Agent；真正取数、建表、质量门走主 Agent。

## 1. 每个模块作用

### 前端

两套界面共用一个静态前端，由 FastAPI 托管。

- **规划工作台**：面向研究者的向导。输入主题，自动走意图理解、文献扫描、候选问题、合同、来源方案。
- **高级工作台**：面向过程审计。展示千问配置、Agent 过程、工具调用、质量门、分析矩阵、溯源图、比赛对齐和导出。

前端会把部分“普通对话”在浏览器里拦截，不送入科研规划；科研规划本身仍是阶段式工作流，不是自由多轮聊天。

### API 层

`backend/app/main.py` 是总入口。FastAPI 应用名仍带乳腺癌痕迹，但运行时已按多癌种肿瘤助手工作。API 同时暴露：

- 用户任务接口
- 单 Adapter 接口
- 规划 / 合同 / 质量 / 评测接口
- 多版本并存的 v2 / v3 能力接口

这是典型的“演进中仓库”：主链可用，历史阶段接口仍保留。

### 规划与合同层

作用是把“我想研究什么”冻成后续取数不能随意改写的契约。

关键对象：

- ResearchTopic：领域、疾病、人群、暴露、结局、缺失维度
- QuestionCandidate：候选问题及其文献证据
- ResearchContract / FrozenResearchContract：字段、指标、粒度、来源约束
- SourcePlanningResult：候选数据集、覆盖矩阵、禁止患者级 Join 的策略

### 主 Agent 层

`ResearchAgentService` 负责一次研究任务的推进：

1. 解析问题为 `ResearchSpec`
2. 生成研究设计与检索计划
3. 调用受控工具
4. 选择主分析表，其余来源作为独立 companion 表
5. 观察字段缺口，换尚未尝试的方法
6. 构建质量门、比赛对齐报告、中文摘要
7. 导出数据包

`ClosedLoopService` 在任务外再包一层，默认两轮：根据质量反馈改下一轮输入，用输入/输出哈希防止空转。

### 工具 / Adapter 层

Adapter 只负责访问官方来源、解析原始返回、登记 `source_id`、URL、accession 和原始字段。它们不理解用户意图，不生成不存在的患者事实。

### 整合与治理层

把原始记录映射到冻结 Canonical Schema，保留 `raw_field` / `raw_value`，构造 Evidence，处理身份关联和冲突。高风险医学语义由规则守门，不交给模型自行定值。

### 审查与发布层

Critic 只诊断，Quality Gate 只裁决，Repair 只在低风险且有依据时改值。三者权限分离：任何一个角色都没有“全链路写权限”。

## 2. 输入是什么

| 模块 | 输入 |
|---|---|
| 规划工作台 | 自然语言主题，可选示例问题 |
| 高级工作台 | 明确科研问题、来源预算、是否启用千问、是否两轮闭环 |
| Intent Agent | 主题文本 |
| Literature Agent | 检索词、最大文献数 |
| QwenClient | 问题、ResearchSpec、工具观察、字段画像、错误记录 |
| Adapter | 项目 ID / GSE / study_id / NCT / 疾病名等受控参数 |
| Dataset Builder | Adapter 原始结果 + ResearchSpec |
| Schema / Entity Matcher | 表头、值画像、身份候选 |
| Critic / Quality | 合同、覆盖率、记录、来源完整性 |
| ClosedLoop | 上一轮 AgentTaskResult 与质量诊断 |

## 3. 输出是什么

| 模块 | 输出 |
|---|---|
| 规划层 | 候选问题、Research Contract、Source Plan、覆盖矩阵 |
| 主 Agent | AgentTaskResult：主表、companion 表、工具日志、质量门、溯源、中文摘要 |
| Adapter | 带 source_id 的原始记录、文件/API 审计、checksum/缓存状态 |
| Parser | ParsedRecord 列表：source_location、raw_field、raw_value、parse_confidence |
| 整合层 | CanonicalRecord、EvidenceCell、link_decisions、conflicts |
| Quality | PASS / REVIEW / FAIL，问题清单，是否允许发布 |
| 导出 | CSV、Parquet、Excel（含来源、字段字典、可科研性、比赛报告等 sheet） |
| 评测 | 分层公开基准分数；乳腺癌候选卷 SDTI 观察值 |

## 4. 模块之间如何调用

实际调用不是“一个 Agent 自由找下一个 Agent”，而是**受控流水线 + 局部反馈**：

1. 前端调用规划 API，生成 Topic / 文献 / 候选 / Contract / Source Plan。
2. 用户确认后，前端调用 `/api/agent/tasks` 或异步 `start()`。
3. `ResearchAgentService` 若启用千问，先 `extract_research_spec`，再 `choose_tools`；同时始终准备确定性检索计划，并与千问工具调用合并、守卫参数。
4. 工具串行执行。独立只读来源在 Function Calling 中可被标记为并行，但生产执行为受控串行，以保证来源登记和复现。
5. Dataset Builder 只从 GEO / cBioPortal / DepMap 等可解析队列建主表；GDC、AACT、CIViC、文献多作为来源/证据/关系层。
6. CollectionAgent 观察缺口，GoalLoopController 按诊断类型从预置策略库中选下一个工具。若启用千问，也可用 `plan_next_tools` 补搜。
7. Critic 和 Quality Gate 看到完整汇总后再裁决。
8. ClosedLoopService 最多再跑一轮合法补搜。质量门 REVIEW 不会被模型自评翻成 PASS。

这套调用关系的优点是权限清楚、失败可归因；缺点是主路径高度预定，动态性被预算、白名单工具和乳腺癌策略库限制。

---

# 第三部分：Agent 能力分析

## 已有 Agent / 角色

下面按“运行时真实职责”列出。名称带 Agent 不等于大模型智能体。

### 1. ResearchAgentService（任务级主 Agent）

- 职责：一次科研数据任务的总控。解析问题、选工具、执行 Adapter、建表、质量检查、摘要和导出。
- 输入：科研问题、来源预算、是否用千问、可选 focus accession / tool。
- 输出：AgentTaskResult（数据集、工具日志、质量门、溯源、比赛对齐）。
- 调用工具：search_gdc、search_geo、search_geo_catalog、search_cbioportal、search_trials、search_civic、search_depmap、search_biosample、search_europe_pmc、extract_paper_assets。
- 智能程度：中。有模型规划入口，但与确定性计划合并；执行、建表、选主队列、医学守卫都是程序。更像“带 LLM 插件的工作流引擎”。

### 2. QwenClient（模型适配器，不是独立业务 Agent）

- 职责：JSON Mode 解析 ResearchSpec；Function Calling 选工具；根据观察规划下一轮工具；字段映射、错误诊断、PICO 标注、检索改写、表清洗、实体匹配的批量辅助；最终中文摘要。
- 输入：结构化 prompt + 受控工具定义。
- 输出：通过 Schema 校验的 JSON / tool_calls / summary。
- 调用工具：不直接访问数据库，只提议工具。
- 智能程度：中高，但是**被契约绑住的智能**。它不能写患者事实，不能绕过质量门，摘要只能复述已验证统计。

### 3. ResearchIntentAgent

- 职责：宽泛主题的第一轮结构化。
- 输入：主题文本。
- 输出：ResearchTopic（领域、疾病、人群、暴露、结局、歧义等级）。
- 调用工具：无。词典和正则。
- 智能程度：低。可识别肿瘤/部分其他领域关键词，不是语义意图理解。

### 4. LiteratureAgent

- 职责：可替换文献 Provider 检索与去重。
- 输入：query、max_records。
- 输出：PaperRecord 列表和 Provider 追踪。
- 调用工具：Giiisp（需配置）、Europe PMC。
- 智能程度：低。检索编排，不是阅读理解 Agent。

### 5. ResearchFormulationAgent

- 职责：从论文和主题生成候选科研问题。
- 输入：Topic + papers。
- 输出：带证据引用和可行性分数的候选问题。
- 调用工具：无。
- 智能程度：低到中。有证据挂钩，但模板/基因列表/结局词典仍是主体；无论文时走 GENERIC_FALLBACK。

### 6. RequirementAgent

- 职责：多视角澄清，把候选冻成 Frozen Research Contract。
- 输入：主题或已选候选。
- 输出：ClarifyResponse / FrozenResearchContract。
- 调用工具：复用 ResearchPlanningService。
- 智能程度：中低。流程完整，生成质量依赖文献是否命中。

### 7. ResearchAgentV2 / Planning V2

- 职责：证据抽取、问题生成、变量设计、研究设计。
- 输入：主题、已检索论文、用户约束。
- 输出：候选问题、必选/推荐字段、study design、unresolved。
- 调用工具：无外部工具。
- 智能程度：中低。接口比 V1 更像 Agent，实现仍偏规则和抽取模板。文档已标明它是阶段能力，不是唯一生产入口。

### 8. CollectionAgent + GoalLoopController

- 职责：观察主表缺口，诊断失败类型，从尚未尝试的方法中换检索。
- 输入：ResearchSpec、当前数据集、readiness、已尝试调用。
- 输出：CollectionGap、下一轮工具、停止条件。
- 调用工具：通过主 Agent 再调 Adapter。
- 智能程度：中。这是系统最像“反思”的部分，但策略库高度预置，乳腺癌 GSE/cBioPortal 队列被写死在策略中。

### 9. CriticAgent

- 职责：独立判断当前数据能否回答冻结合同。
- 输入：合同、字段覆盖、行数、身份/来源/语义冲突标志。
- 输出：GapDiagnosis（缺失结局、暴露、身份未决、禁止 Join 等）。
- 调用工具：不改数据，只建议下一步工具类型。
- 智能程度：低到中。规则诊断器。价值在独立性，不在生成能力。

### 10. QualityAgent / QualityV2Service

- 职责：最终准入。检测、修复候选、安全应用、人工复核队列分开。
- 输入：规范化记录、必选字段。
- 输出：READY / REVIEW / FAIL，publish_allowed。
- 调用工具：ErrorClassifier、Repair 候选器；高风险字段永不自动改。
- 智能程度：低。必须保持低。这是安全门，不是智能体。

### 11. ClosedLoopService

- 职责：任务级两轮反馈控制器。
- 输入：初始 AgentTaskRequest。
- 输出：每轮指标快照、诊断、动作、哈希审计、最佳轮次展示。
- 调用工具：再次调用 ResearchAgentService。
- 智能程度：低到中。控制器，不是会自由发挥的模型 Agent。文档也明确反对把它包装成后者。

### 12. SourceBroker

- 职责：按字段覆盖、权威性、粒度、成本做来源组合。
- 输入：ResearchContract、论文中的 accession。
- 输出：候选来源、覆盖矩阵、Join 策略。
- 调用工具：种子目录 + greedy set cover。
- 智能程度：中低。优化器，不是开放世界发现器。肿瘤合同会先验加入 cBioPortal / GEO / GDC。

### 13. ResearchOrchestrator

- 职责：文档中的阶段路由器。
- 输入：问题、合同状态、已完成阶段、质量门。
- 输出：下一阶段和所需工具名。
- 调用工具：无。
- 智能程度：低。硬编码状态机。**当前未接入生产主链。**

## 目前系统是否具备关键智能能力

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 意图识别 | 部分具备 | 有主题拆解、PICO/序列特征、千问 ResearchSpec。规划前端还有规则分流“普通对话 / 科研规划”。但 Intent Agent 本质是词典；复杂否定、比较、复合终点仍弱。EBM-NLP F1 0.5522，说明能用，但远未达到稳健语义理解。 |
| 任务规划 | 部分具备 | 有 Research Contract、Search Plan、千问 choose_tools、确定性 SearchPlanner。规划是“在白名单工具和预算内填计划”，不是开放任务分解。乳腺癌补搜计划明显被示范队列先验牵引。 |
| 工具调用 | 具备 | 这是最完整的 Agent 能力。千问 Function Calling + 10 个受控工具 + 参数守卫 + 来源登记 + 串行审计。工具失败有日志，不静默编造 accession。 |
| 自主决策 | 弱 / 有边界 | 系统可以在缺口时换队列、换工具、拒绝发布。但不能自己发明新数据源类型，不能决定绕过医学规则，不能把 companion 表拼进主患者。所谓自主，是“在规则盒子里换合法方法”。 |
| 反思纠错 | 部分具备 | 有三层：任务内 goal_loop、Critic、两轮 ClosedLoop。能诊断结局域错配、缺 pCR、缺 HER2、空转。但反思规则化，常见动作是“改搜 GSE25066 / GSE76360 / GSE50948”。不是对任意失败做开放推理。 |
| 多轮交互 | 弱 | 有研究会话、任务状态、两轮闭环、规划阶段回看。没有 ChatGPT 式持续对话、记忆用户偏好、追问澄清后动态改合同的真正多轮 Agent。规划工作台更像一次提交驱动的向导；高级工作台更像一次协议运行。 |

**总评：** 当前是 **Tool-using Workflow Agent**，不是 **General Reasoning Agent**。  
它已经具备“调用工具拿真数据”和“用规则防止胡说”这两件最重要的科研数据 Agent 能力；缺少的是开放世界中的问题理解、来源发现和失败后的创造性再规划。

---

# 第四部分：数据能力分析

## 当前支持的数据来源总览

| 类型 | 来源 | 在系统中的角色 |
|---|---|---|
| 数据库 / 队列 API | GDC/TCGA、cBioPortal、NCBI GEO、ClinicalTrials.gov/AACT、CIViC、DepMap、NCBI BioSample | 患者/样本队列、试验、知识证据、细胞系、样本元数据 |
| 论文 | Europe PMC，可选 Giiisp | 研究语境、accession 发现、全文表/图注 |
| 表格 | GEO Series Matrix、cBioPortal 临床/突变/CNA 宽表、CSV/TSV、Excel、HTML table、JATS table | 主分析表和论文表抽取 |
| 文件 | GEO matrix/soft/suppl 下载与缓存、GDC 文件下载（有大小限制）、本地解析上传形态 | 原始文件审计 |
| API | 上述官方 API + 千问 API | 取数与规划 |
| 评测数据 | EBM-NLP、BEIR、Valentine、DeepMatcher、Raha/HoloClean、乳腺癌 Gold Set | 能力证明，不是业务主表 |

DepMap 是增强来源，默认不作为患者主表。PRISM / GDSC 仍是设计中的增强来源，不是已完成 MVP。

## 每个数据源：获取、解析、输出

### GDC / TCGA

- 获取方式：GDC 官方 API，按 project_id 检索临床/突变/表达/拷贝数文件。
- 解析方式：Adapter 校验项目、文件清单和下载限制；不把文件清单直接当成患者表。
- 输出格式：SourceItem + 文件/项目元数据。主患者宽表目前更常由 cBioPortal / GEO 建成；GDC 承担官方项目与组学文件证据。

### NCBI GEO

- 获取方式：按 GSE accession 访问 NCBI FTP/Portal，下载 Series Matrix 等，本地缓存。
- 解析方式：解析样本注释和特征字段；映射 HER2、治疗、pCR 等同义表达；治疗后样本不得变成另一名患者。
- 输出格式：样本级宽表候选、source_id=`ncbi_geo` / `geo:{accession}`、raw characteristics。

GEO 另有目录检索：只发现候选 GSE 和摘要，**目录命中不等于已经具备 pCR/HER2 字段**。必须再调用 search_geo 下载矩阵。

### cBioPortal

- 获取方式：按 study_id 拉临床表、突变、离散 CNA。
- 解析方式：临床表作为队列锚点，按 sampleId 连接分子；透视为科研宽表。
- 输出格式：患者/样本级宽表，accession 如 `brca_metabric`。生存队列不能自动充当 pCR 队列。

### ClinicalTrials.gov / AACT

- 获取方式：试验检索 API，按 condition / NCT。
- 解析方式：保留 studies / conditions / interventions / outcomes 关系，不做参与者级患者表。
- 输出格式：试验关系记录。可解释方案和结局定义，不能填入患者治疗记录。

### CIViC

- 获取方式：知识证据 API。
- 解析方式：Variant-Drug-Disease-Evidence 关系，保留证据等级和出处。
- 输出格式：知识证据层。不得替代患者检测结果。

### DepMap

- 获取方式：细胞系药敏查询。
- 解析方式：强制 `response_domain=preclinical_cell_line`。
- 输出格式：细胞系表。AUC/IC50 不得解释为患者 pCR，不得与患者行 Join。

### NCBI BioSample

- 获取方式：eutils esearch/esummary。
- 解析方式：样本 accession 与属性。
- 输出格式：样本元数据。只核验，不证明跨库同一患者。

### 论文 / Europe PMC / Giiisp

- 获取方式：Europe PMC 检索 API；可选全文 XML；Giiisp 需用户配置。
- 解析方式：题录、摘要、PMID/DOI、全文 JATS 表和图注；accession 从文本收获。
- 输出格式：PaperRecord、chunk、表格单元格、图注文本。摘要不能当患者事实。

### 本地/通用文件解析器

| 解析器 | 获取方式 | 解析方式 | 输出格式 |
|---|---|---|---|
| CSV/TSV | 文件名或文本 | 行列解析 | ParsedRecord |
| Excel | xlsx/xlsm 字节 | 工作表单元格 | ParsedRecord |
| HTML table | HTML 中的 table | 表头+单元格 | ParsedRecord，带 table/row 位置 |
| JATS XML | 论文全文 XML | 表格单元格 + figure caption | 表为 PARSED，仅图注时 REVIEW |
| PDF | 需已提供文本层 | 按摘要/方法/结果等标题切段 | 文本摘录 + content_hash；无文本层则 REVIEW，禁止猜表 |

## 数据整合时的关键边界

系统允许的组合：

- 同一 `study_id` 内，按 sample_id / 唯一 patient_id 关联
- 不同队列作为独立分析或外部验证
- 试验、细胞系、CIViC 通过基因/药物/疾病在研究层关联

系统明确禁止：

- 凭同名 patient_id 跨 GDC / GEO / cBioPortal 合并
- 用细胞系药敏推断患者疗效
- 用知识库证据填患者主表
- 把图中估读数写成患者原始记录

这套边界是数据能力的一部分，不是附属说明。它决定了系统“能整合什么”以及“整合到什么粒度”。

---

# 第五部分：当前优势分析

## 哪些代码和设计是项目核心资产？

按不可替代性和赛题价值排序。

### 1. 医学安全规则与语义隔离（最不能丢）

- `configs/medical_rules.yaml`
- `configs/canonical_schema.yaml`
- HER2 IHC 2+ 不得直接 Positive
- ERBB2 CNA ≠ HER2 IHC positive
- `response_domain` 区分临床 / 细胞系 / 试验 / 知识证据
- 低置信度身份关联进入 unresolved/review
- 缺 Evidence 不得发布

这不是普通校验，而是项目能被称为“可信科研数据系统”的根基。公开字段匹配分数再高，也不能替代这组规则。

### 2. 来源可追溯机制

强制 `source_id`、`raw_field`、`raw_value`、官方 URL、accession、checksum/缓存、行级来源。EvidenceBuilder 把标准值绑回原始证据。导出 Excel 含来源和可科研性 sheet。前端有溯源图。

这直接对应赛题的“来源追踪”。很多 Agent demo 做不到这一层。

### 3. 官方数据源 Adapter 与解析深度

GEO Series Matrix、cBioPortal 临床+分子透视、GDC、AACT、CIViC、DepMap、Europe PMC、BioSample，不是搜索框演示，而是可运行、有错误码、有缓存和下载限制的 Adapter。测试覆盖 adapter、integration、api 三层。

其中 GEO 样本特征解析、治疗后样本配对、cBioPortal 宽表构建，是乳腺癌场景能跑通的直接原因。

### 4. 字段对齐与数据质量控制

- Canonical Schema 冻结接口
- SchemaMatcher / 值画像 / 千问辅助匹配
- 格式型清洗、来源锚点修复
- Quality V2：检测、候选、安全应用、复核队列分离
- 高风险字段永不自动改

公开评测上，字段匹配和有证据的清洗是相对强项。Valentine F1 0.9018，清洗六项 F1 0.9169。真正可迁移的不是分数，而是“能自动的自动，不能自动的进 REVIEW”这套策略。

### 5. 身份与跨源合并策略

实体匹配公开分数几乎不优于基线，系统没有假装自己很强。相反，它把 matcher 降级为候选生成器，用研究命名空间和 0.90 阈值守门。这是正确的科研软件判断，属于资产而不是短板包装。

### 6. 缺口驱动闭环，而不是一次检索交差

CollectionAgent、GoalLoop、ClosedLoop 把“缺 pCR 却拿到生存表”识别为结局域错配，并改搜响应队列。质量门可以保持 REVIEW。候选卷观察中 9 个任务仍为 REVIEW，系统没有为了分数自动发布。

这对赛题“反馈修正”是有说服力的，只要不把两轮固定补搜夸成通用反思。

### 7. 评测与诚实口径

分层公开基准、Gold Set 分册、SDTI 公式冻结、`publish_allowed=false`、禁止硬编码答案、禁止把 Qwen 未调用的备用流程写成 Qwen 成绩。这套科研诚信约束本身是资产。通用 Agent 升级时必须带着走，否则会迅速变成不可审的生成系统。

### 8. 前端过程可视化

规划向导 + 高级工作台把过程、结果、质量、溯源、比赛对齐同时展开。对评委和研究者，这比纯 API 更接近“科研助手”。它不是核心算法资产，但是核心产品资产。

### 9. 多癌种配置底座

18 个癌种的 GDC/cBioPortal 种子入口已经核验。未配置癌种不会静默回退成乳腺癌。这说明项目已经开始从“单病种 demo”走向“肿瘤通用底座”，尽管专项深度仍在乳腺癌。

## 哪些模块不能轻易修改？

必须先走 `CHANGE_REQUEST.md` 或同等影响分析的冻结面：

1. `configs/canonical_schema.yaml`：全系统数据契约。改字段会牵动 Adapter、Matcher、质量门、Gold Set、导出。
2. `configs/medical_rules.yaml`：医学安全语义。改错会直接产生错误临床含义。
3. `../../06_评测指标与SDTI.md`：评测公式。改公式等于改比赛口径。
4. 来源审计字段：`source_id` / `raw_field` / `raw_value` / Evidence。去掉它们，系统立即失去可信性。
5. 身份规则：跨研究不自动 Join、低置信度 unresolved。放宽会污染主表，且不可逆。
6. Adapter 官方入口与错误边界：不要把模型生成记录混进 Adapter 输出。
7. Quality Gate 的否决权：模型不得自证 PASS。
8. Gold Set 分册隔离：development 分数不得进入正式栏；official_candidate 仍未 sealed。

可以演进、但要当“兼容层”而不是替换内核的模块：

- QwenClient 的 prompt 与工具选择
- 前端向导文案和布局
- SourceBroker 的排序权重
- SchemaMatcher / EntityMatcher 的算法版本
- 检索 BM25/BGE 融合参数
- 规划 V1/V2 双轨 API

**架构判断：** 项目真正值钱的是“可信数据治理内核”，不是 Agent 角色命名，也不是前端皮肤。后续任何智能化升级，都应绕开冻结内核做增量，而不是先拆内核。

---

# 第六部分：与“科学数据整合 AI Agent”赛题匹配分析

赛题能力按 11 项逐条评价。状态只用：已有 / 部分已有 / 缺失。

## 1. 科研问题理解

- 当前状态：**部分已有**
- 实现位置：`ResearchIntentAgent`、`ResearchQuestionParser`、`QwenClient.extract_research_spec`、`RequirementAgent`、`ResearchContractBuilder`、公开评测 `evaluation/public_problem_understanding`
- 提升建议：把“词典拆字段”和“合同冻结”分开增强。前者需要真正的结构化抽取（span/PICO/关系），后者需要用户可确认的澄清问句。不要只靠增加关键词。当前 EBM-NLP F1 0.5522，干预边界仍弱，还不能代表任意学科问题理解。

## 2. 自动数据发现

- 当前状态：**部分已有**
- 实现位置：`SourceBroker`、`SourceDiscovery`、`search_geo_catalog`、Europe PMC accession harvest、种子目录 `configs/source_capabilities`
- 提升建议：现在的发现主要是“在已知肿瘤数据库和论文 accession 里选”。通用科研数据发现需要目录层（数据集注册表、仓库 API、论文补充材料链接）和“未登记来源的候选生成”。SourceBroker 的集合覆盖可以保留，作为已发现候选的组合器，而不是唯一发现器。

## 3. 多源异构数据获取

- 当前状态：**已有**（在肿瘤公开数据范围内）
- 实现位置：`backend/app/sources/*`、`DiscoveryAdapter`、主 Agent 工具表
- 提升建议：保持 Adapter 模式。新增来源时复制 GDC/GEO 的契约：官方入口、错误码、source_id、原始值、测试。不要让 LLM 直接抓网页当事实。通用化时缺的是非肿瘤来源，不是这套获取架构。

## 4. PDF 解析

- 当前状态：**部分已有**
- 实现位置：`backend/app/parsers/pdf_text.py`、ParserRegistry
- 提升建议：当前只切文本层章节，无文本层就 REVIEW，禁止猜表。这在安全上正确，在赛题完整度上不够。后续应增加版面分析、表格区域检测和数字可信度；仍然不要让模型在不确定布局时填数。PDF 解析应产出“候选表 + 置信度 + 原文位置”，送入现有 ParsedRecord，而不是另建一套事实通道。

## 5. 表格解析

- 当前状态：**已有**
- 实现位置：CSV/TSV、Excel、HTML table、JATS table、GEO matrix、cBioPortal 透视
- 提升建议：结构化表已经能进 Canonical 流程。缺口在复杂表：多级表头、跨页表、补充材料 xls、图内表。优先把 Parser 输出稳定接到 SchemaMatcher，而不是再写一套乳腺癌专用解析。

## 6. 图像数据提取

- 当前状态：**部分已有，接近能力缺口**
- 实现位置：JATS 提取 figure caption；工具 `extract_paper_assets` 明确禁止从图像素读数
- 提升建议：当前只拿到图注文本，没有轴、点、热图、Western blot 读数。赛题若要求图像数据，应新增“多模态抽取 Agent”，但输出必须是候选观测 + 位置 + 低置信度 REVIEW。不要把估读数写入患者主表。可先做：图注-表格互证、流程图/队列图的文字理解，再考虑谨慎的图表数字化。

## 7. 字段对齐

- 当前状态：**已有**
- 实现位置：`canonical_schema.yaml`、`SchemaMapper`、`SchemaMatcherV2/V3`、千问 `normalize_research_field` / `match_schema_batch`、GEO 特征同义映射
- 提升建议：算法层已经是优势。通用化时不要把肿瘤 Canonical Schema 强行当成万物模式。正确做法是保留“冻结目标 schema + raw 保留 + AUTO/REVIEW/REJECT”，让目标 schema 可按学科加载。医学高风险字段继续规则复核。

## 8. 数据清洗

- 当前状态：**已有**（格式/有证据修复）；语义清洗仍弱
- 实现位置：DatasetBuilder 清洗、Quality V2、RepairLoop、Raha/HoloClean 评测
- 提升建议：继续坚持“无证据不修”。Hospital/Rayyan 类任务为 0，说明缺值与无锚点损坏仍应 REVIEW。通用化需要错误分类器可配置，而不是把乳腺癌 HER2 规则扩散到所有领域。

## 9. 来源追踪

- 当前状态：**已有**
- 实现位置：SourceItem、EvidenceCell、source_manifest、导出“数据来源”sheet、前端溯源图、ScientificGraphStore
- 提升建议：这是赛题匹配最强项之一。升级时把现有 lineage 从“来源-数据集-字段-质量反馈图”扩展为证据图，但边仍然不能表示患者身份。不要用知识图谱营销替代审计图。

## 10. 质量验证

- 当前状态：**已有**
- 实现位置：QualityAgent、QualityGate 四层、Quality V2、Critic、medical_rules、SDTI 观察
- 提升建议：质量门已经能阻断发布。通用化需要把“肿瘤医学规则包”变成可插拔 Rule Pack，同时保留通用规则：缺来源、缺原始值、低置信度身份、跨粒度混用。正式 SDTI 仍未 sealed，不能把 98.11 / 100.00 写成可发布成绩。

## 11. 反馈修正

- 当前状态：**部分已有**
- 实现位置：CollectionAgent、GoalLoop、ClosedLoopService、outcome_repair、前端展示第二轮动作
- 提升建议：已有“诊断缺口 → 换合法方法 → 防止空转”。不足是动作空间小、轮次少、策略偏乳腺癌示范队列。升级应把诊断类型抽象为通用缺口（缺主表、缺结局、缺同源暴露、解析失败、来源不权威），再让规划器选工具，而不是删除现有两轮控制器。

### 赛题匹配总表

| 赛题要求 | 状态 | 相对成熟度 |
|---|---|---|
| 科研问题理解 | 部分已有 | 中 |
| 自动数据发现 | 部分已有 | 中低 |
| 多源异构数据获取 | 已有 | 高（肿瘤域） |
| PDF 解析 | 部分已有 | 低 |
| 表格解析 | 已有 | 高 |
| 图像数据提取 | 部分已有 | 低 |
| 字段对齐 | 已有 | 高 |
| 数据清洗 | 已有 | 中高 |
| 来源追踪 | 已有 | 高 |
| 质量验证 | 已有 | 高 |
| 反馈修正 | 部分已有 | 中 |

**匹配判断：** 作为“肿瘤科研数据可信整合系统”，与赛题主链高度同向。作为“通用科学数据查找解析与整合 Agent”，目前是领域特化的强实现，不是通用 Agent。最短板是开放发现、PDF/图像多模态、以及非肿瘤问题的动态规划。

---

# 第七部分：智能化不足分析

## 为什么当前系统不像 ChatGPT Agent？

因为它被设计成**不让模型自由行动的科研数据工厂**。ChatGPT Agent 的默认假设是：模型可以看页面、写代码、决定下一步、对失败即兴换招。本系统的默认假设是：模型可以建议，事实必须来自 Adapter，发布必须过规则门。

这不是实现失败，是产品选择。但这个选择带来了“看起来不像通用 Agent”的体验。

## 1. 缺少哪些智能能力？

1. **开放世界意图理解。** 离开肿瘤词典和示范问题后，Intent Agent 很快退化成关键词。没有真正的澄清对话，也没有对含糊问题主动提问“你要的是 pCR 还是 OS”。
2. **开放任务分解。** 没有把任意科研问题拆成未知工具序列的规划器。现有计划是填入固定阶段：解析 → 选源 → 取数 → 对齐 → 质量门。
3. **未知数据源的发现与接入。** 不能在运行时学会一个新仓库、读它的 API 文档、生成新 Adapter。发现被种子目录和论文 accession 限制。
4. **文档与图像的深度理解。** PDF 不还原表结构，图像不数字化，补充材料不会被当作探索对象。
5. **真正的多轮研究对话。** 用户不能像和同事一样说“不要 METABRIC，换成新辅助队列，顺便看一眼补充表 2”。系统可以再跑一轮任务，但不是连续研究会话。
6. **对失败的创造性反思。** 能识别结局错配并改搜几个预置 GSE；不能提出全新假设，例如“这篇方法学论文的补充 CSV 可能有事件定义”。
7. **跨领域 schema 生成。** Canonical Schema 是冻结的肿瘤患者/样本模型。天文学、材料、生态数据没有对应契约。Intent 虽能把主题标成 astronomy，后续主链仍是肿瘤数据工具。
8. **Orchestrator 名实不符。** 文档中的总控路由几乎不在生产路径上。真实控制流写在 `ResearchAgentService` 的长过程里，智能化扩展会继续把逻辑堆进这个服务。

## 2. 哪些地方是固定流程？

以下环节即使启用千问，也仍然是固定的：

- 规划工作台五阶段：方向 / 文献 / 问题 / 合同 / 来源
- 主任务五步：理解问题 / 研究设计 / 搜索数据库 / 数据整合 / 质量检查
- 工具白名单：10 个 function
- 主表候选来源：主要从 GEO / cBioPortal / DepMap 建表
- 跨源不患者级 Join
- 医学规则和质量门
- 默认两轮闭环、最大收集轮次
- 乳腺癌缺口时优先搜索 GSE25066、GSE76360、GSE50948 等示范队列
- 无论文 Evidence 时候选问题只能算 GENERIC_FALLBACK
- 离线评测可完全关闭模型，走确定性基线

千问出现时，也常被确定性计划合并和参数守卫。也就是说，模型很少单独决定主路径。

## 3. 哪些地方需要动态规划？

如果目标是通用科研数据智能体，以下环节不应继续全靠写死：

1. 问题一进来，就要判断学科、数据粒度、是否需要实验数据/文献表/仓储 API，而不是默认肿瘤队列。
2. 发现阶段应能根据合同缺口选择“搜数据仓库 / 搜论文补充材料 / 搜已知 API / 请求用户上传”。
3. 解析阶段应能根据文件类型动态选 PDF 表、Excel、图像、API JSON，而不是主要等待 GEO matrix。
4. 整合阶段应能生成或加载该任务的目标 schema，而不是所有任务共用乳腺癌患者字段。
5. 闭环阶段应根据 Critic 诊断选择新方法，包括换查询词、换仓库、换解析器，而不仅是换几个预置 accession。
6. 用户中途插入约束（只要公开个体数据、不要细胞系、只要中国队列）应能改写尚未执行的计划，而不是从头重跑一个固定协议。

当前动态性只覆盖“在肿瘤工具盒里换入口”。

## 4. 哪些地方需要 LLM 参与？

适合 LLM 的地方：

- 含糊科研问题的澄清问句
- 从论文中提出候选问题、变量和结局定义
- 在未见过的表头上做字段假说
- 从 PDF/HTML 中定位可能的表、图、补充文件链接
- 把质量缺口翻译成下一轮检索策略
- 用自然语言解释为什么某个来源被拒绝或进入 REVIEW

不适合 LLM 单独负责的地方：

- 生成患者/样本行
- 最终 HER2 / response_domain / 身份合并
- 官方 API 的事实返回
- 发布准入
- 评测分数
- 无文本层 PDF 的表格猜数
- 图像像素读数直接入库

**结论：** 不像 ChatGPT Agent，是因为系统把智能用在“填计划、做摘要、辅助匹配”，而把“世界状态”锁在 Adapter 和规则里。要升级，不是取消这些锁，而是在锁之外增加真正的规划与发现智能。

---

# 第八部分：升级建议（只提出，不修改）

目标形态：**通用科研数据发现与可信整合智能体**。  
约束：增量叠加，不推倒现有治理内核。

下面只提新增模块。每个模块都说明与现有代码的关系，避免“再写一套系统”。

## 新增模块

### 1. Router Agent（路由智能体）

- 作用：判断用户输入是闲聊、概念问答、还是科研数据任务；判断学科、数据粒度、是否需要进入完整整合链。
- 输入：用户原话、会话状态、是否已有 Frozen Contract。
- 输出：路由决策（对话 / 澄清 / 规划 / 取数 / 仅检索文献）、学科标签、需要激活的下游 Agent。
- 与现有代码关系：收编前端现有的规则分流，以及 `ResearchIntentAgent` 的领域词典。不替换 `ResearchAgentService`。生产主链仍只在路由结果为“科研数据任务”时启动。现有 `ResearchOrchestrator` 可被它取代或降为确定性兜底，不必继续作为独立生产组件扩展。

### 2. Scientific Planner（科学规划器）

- 作用：把问题变成与领域无关的研究契约：对象、处理、结局、单位、时间窗、数据模态、成功标准、停止条件。
- 输入：用户问题、文献 Evidence Pack、用户约束。
- 输出：通用 Research Contract + 可执行计划草稿 + 待澄清问题。
- 与现有代码关系：站在 `RequirementAgent`、`ResearchContractBuilder`、`ResearchPlanningV2` 之上做统一门面。肿瘤任务继续复用现有字段和医学规则包；其他学科加载不同 schema 与规则包。不要让 Planner 直接写 CanonicalRecord。

### 3. Data Discovery Agent（数据发现智能体）

- 作用：在开放资源中寻找候选数据集，而不仅是从种子目录打分。
- 输入：冻结合同、已有论文 accession、字段缺口。
- 输出：候选资源列表（仓库、论文、补充文件、API、用户本地文件），每个候选带发现证据和需验证的字段假说。
- 与现有代码关系：现有 `SourceBroker` 保留为“候选组合与覆盖优化器”；Discovery Agent 只负责产生候选。现有 GEO 目录、Europe PMC、accession harvest 应成为它的第一批工具，而不是被重写。

### 4. Multimodal Extraction Agent（多模态抽取智能体）

- 作用：从 PDF、HTML、Excel、图像、补充材料中抽取表、图注、轴标签、队列描述。
- 输入：文件字节或全文 XML、source_id、期望字段。
- 输出：ParsedRecord 候选，带位置、置信度、模态类型；低置信度一律 REVIEW。
- 与现有代码关系：直接扩展 `ParserRegistry`。CSV/Excel/HTML/JATS 已可用；PDF 文本层作为 fallback；新增版面表抽取和图像理解时，必须继续禁止“无把握读数入库”。`extract_paper_assets` 可作为它的肿瘤论文工具之一。

### 5. Evidence Graph（证据图）

- 作用：统一表达问题、论文、文件、表、字段、质量反馈、修复动作之间的支持/反驳/来源关系。
- 输入：规划图、来源清单、EvidenceCell、Critic/Quality 发现。
- 输出：可查询、可展示、可导出的证据图快照；查询“这个标准值为什么成立”。
- 与现有代码关系：合并并升级现有 `ScientificGraphStore` 和比赛对齐里的来源-字段-反馈图。继续禁止用图边表示跨研究患者身份。前端溯源图改为读这个图，而不是另做一套展示数据。

## 建议保留为内核、不要重做成 Agent 的模块

- Adapter 层
- Canonical mapping + raw 保留
- 医学/安全规则引擎
- Quality Gate
- 评测与 Gold Set 口径
- ClosedLoop 的防空转哈希与轮次预算

## 增量升级顺序（仅建议，不实施）

1. 把 Router 从前端规则提升为明确服务，先不改取数。
2. 让 Planner 输出与现有 Frozen Contract 兼容的超集，肿瘤任务回归测试必须过。
3. 给 Discovery 增加“论文补充材料 / 通用仓库”候选，仍经 SourceBroker 选择。
4. 增强 PDF 表抽取，接到 ParserRegistry。
5. 证据图先打通现有 lineage，再考虑跨模态节点。
6. 最后才考虑图像数字化，且默认 REVIEW。

这条路径的目标是：用户感觉更像智能体，内核仍然是可信数据工厂。

---

# 第九部分：风险分析

## 如果直接重构，可能损失什么？

1. **医学安全语义。** 重写规则引擎或把 HER2 / response_domain 交给模型，会立刻破坏项目最硬的可信承诺。
2. **来源可追溯性。** 若新 Agent 直接生成表，不再强制 raw_field/raw_value/Evidence，赛题最能打分的部分会消失。
3. **已验证 Adapter。** GEO 矩阵、cBioPortal 透视、下载限制、缓存、错误码是长期试错结果。推倒重写通常先变成“能搜不能解析”。
4. **评测可比性。** SDTI 公式、Gold Set 分册、公开基准脚本一旦换口径，历史成绩全部作废，且容易滑向虚假成绩。
5. **质量门的否决文化。** 重构若以“更像 ChatGPT”为目标，往往会去掉 REVIEW 阻断，使系统重新变成流畅但不忠于数据的生成器。
6. **测试资产。** 后端约 90 个测试文件，覆盖 Adapter、规划、闭环、Matcher、Gold Set、公开评测。重构会使这张网失效，短期看起来快，中期无法证明没退步。
7. **前端过程叙事。** 规划向导和高级工作台已经能把过程讲清楚。重做 UI 而不接原 API，会失去评委和用户已经理解的工作流。
8. **诚实的失败模式。** 当前系统允许空结果、REVIEW、GENERIC_FALLBACK。重构常见失败是用模板或模型补全“看起来完整”的表。

## 哪些模块应该保留？

必须保留：

- 冻结 Canonical Schema 与医学规则
- 全部官方 Adapter 及其测试
- ParserRegistry 契约（ParsedRecord）
- Evidence / source_id / raw 保留
- Quality V2 的检测-候选-应用分离
- Critic 与 Quality Gate 独立
- ClosedLoop 防空转
- Gold Set 与 SDTI 口径
- 跨研究禁止患者 Join
- 千问凭据不落盘

建议保留并包一层新接口：

- ResearchAgentService（作为肿瘤执行引擎）
- SourceBroker（作为候选组合器）
- Research Planning 工作台
- 导出与比赛对齐可视化

可以逐步收缩、但不要突然删除：

- mock pipeline
- v2/v3 并存 API
- 未接入生产的 ResearchOrchestrator
- 乳腺癌示范队列策略（先泛化，再降为肿瘤规则包）

## 推荐采用：B. 增量升级

不推荐 A. 重构。

原因：

1. **问题不在架构类型，而在智能覆盖面。** 现有“规划 / 取数 / 整合 / 批评 / 质量 / 闭环”已经是正确的科研数据 Agent 骨架。缺的是通用发现和多模态，不是再发明一套角色名。
2. **核心资产是确定性内核。** 重构最容易毁掉的正好是现在领先赛题的部分：追溯、规则、Adapter、质量门。
3. **生产主链已经可演示、可导出、可评测。** 增量升级可以先让 Router/Planner/Discovery 走旁路，用现有乳腺癌回归做安全网。重构没有这张网。
4. **仓库已有双轨痕迹。** Planning V1/V2、Matcher V2/V3、Quality 与 Repair 并存。这说明团队已经在增量演进。需要的是收敛接口，而不是第三次推倒。
5. **通用化的正确方式是“内核不变，规则包可替换，发现层变宽”。** 这只能增量完成。若先重构为通用 Agent 框架，再把医学规则补回去，成本和回归风险都更高。

增量升级的主要风险不是“不够彻底”，而是**继续把新逻辑塞进 `ResearchAgentService` 超长主过程**，使系统更难变成通用体。因此增量也需要纪律：新智能放在新模块，旧服务只做适配，不在主文件里再长一层领域策略。

---

# 最终结论

当前项目是一个**有边界、可审计、肿瘤领域特化的科研数据助手**。  
它的内核是数据处理与可信治理，外壳是混合式多 Agent 编排。

它已经具备赛题最难但最有价值的部分：真取数、字段对齐、来源追踪、质量阻断、有限闭环。  
它还不像通用 ChatGPT Agent：意图、发现、PDF/图像、跨领域规划和多轮研究对话仍然不够。

下一步不应重构，而应在不触碰冻结内核的前提下，增量增加 Router、Scientific Planner、Data Discovery、Multimodal Extraction 和 Evidence Graph。这样，系统才能从“科研数据智能体”，成长为“通用科研数据发现与可信整合智能体”，同时保住现在真正值钱的东西。

本报告只分析，不构成代码变更或实施授权。
