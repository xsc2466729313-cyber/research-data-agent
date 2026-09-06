# V3.1 前端科研智能工作台设计

- 日期：2026-09-05
- 性质：产品与界面设计，不是实施授权，不含代码
- 能力基线：Router / Copilot / Planner / Registry / Discovery / Source Selection / Schema Pack / Matcher Bridge / Evidence Graph / Figure Understanding / Integration Preview / ExecutionBridge / Oncology Real Integrate
- 对照：现有 `frontend/` 仍是旧肿瘤规划工作台 + 高级工作台，**没有任何 `/api/v30` 调用**

本文把已经存在的后端能力设计成一个高级 AI 科研产品，而不是聊天机器人外壳。

---

## 0. 设计原则（必须先读）

**产品不是对话。** 对话只是入口之一。真正的产品是：目标被澄清、来源被选择、字段被对齐、证据可追问、执行可拒绝、结果可导出。

四家参照各自只借一层，不混成拼盘：

| 参照 | 借什么 | 不借什么 |
|---|---|---|
| Apple | 留白、层级、少按钮、空间感、克制动效 | 装饰性玻璃、空洞大标题 |
| Google | 状态、进度、可扫描信息块、明确下一步 | 材料风组件堆砌 |
| Perplexity | 来源卡片、引用可点开、证据先于结论 | 无限回答流、搜索引擎首页感 |
| Elicit | 结构化表、列即判断、工作流可回看 | 把科研做成问卷工厂 |

诚实性是视觉规范的一部分：

- `unverified` 不能画成已验证
- `coverage_claimed=false` 不能显示覆盖进度条
- `catalog_only` 不能显示“可下载”
- `execution_allowed=false` 时执行按钮必须禁用并解释原因
- 只有 `domain=oncology` 且 `execution_ready=true` 才能进入真实 Integrate
- 天文 / 材料停在 Preview，不得假装出主表
- 图理解即使 `digitization_possible=true` 也必须大字标明“未写入主表”
- 禁止把旧工作台的“发送并开始研究”做成 V3.1 主按钮

旧高级工作台保留为“内核实验室”，不作为 V3.1 主路径。

---

# 1. 产品定位

## 1.1 一句话

**面向科研人员的证据驱动数据工作台：把一句研究想法编译成可追溯的来源、字段、证据与（仅在医学插件就绪时）可导出数据集。**

不是诊疗系统。不是文献聊天。不是自动发论文。不是已经整完主表的黑盒。

## 1.2 用户是谁

| 角色 | 他们来做什么 | 他们怕什么 |
|---|---|---|
| 肿瘤转化研究者 | 从 HER2 / pCR / 耐药问题走到可复核的患者级公开数据 | 被自动判阳性、跨队列乱合并、细胞系当患者 |
| 跨领域科研用户 | 用同一入口试天文等问题，看系统是否乱套医学字段 | 被假装成已经取数 |
| 评审 / 合作者 | 顺着 Timeline 看每一步为什么、卡在哪 | 看不懂状态、分不清规划与执行 |

## 1.3 产品承诺

系统承诺的是**过程诚实**：

1. 先理解目标，再允许规划。
2. 先发现候选，再选择；发现不等于覆盖。
3. 先对齐字段，再谈执行；映射不是数据行。
4. 先预览将调用谁，再决定是否执行。
5. 执行后仍保留 `source_id` / `raw_field` / `raw_value` / Evidence / Quality Gate。

系统不承诺：自动诊疗、跨研究患者合并、把图读数写进主表、天文真实 Integrate。

## 1.4 与现有前端的关系

```text
现有 frontend/                 继续存活，降级为兼容面
  规划向导 #planning-workspace   旧 /api/v3 五阶段
  高级工作台 #task-entry         旧 /api/agent/tasks

新 V3.1 工作台                 唯一主产品面
  只消费 /api/v30/* + 执行后的旧导出接口
```

用户从新工作台进入。需要核对内核细节时，再打开“内核实验室”。禁止两个入口同时自动跑同一条执行链。

---

# 2. 页面信息架构

工作台是**一条研究会话（session）上的多表面**，不是网站栏目。左侧是研究脊骨，中间是当前工作面，右侧是只读情境。

```text
┌ Shell ─────────────────────────────────────────────────────────┐
│ 品牌 · 当前研究标题 · 领域徽章 · 会话状态 · 内核实验室入口      │
├──────────┬────────────────────────────────────┬────────────────┤
│ Timeline │ 当前工作面                          │ Context Rail   │
│ 阶段导航  │ Home / Copilot / Sources / Mapping │ Memory         │
│ 门状态    │ Graph / Preview / Dataset          │ 约束 / 合同     │
│ 会话列表  │                                    │ Why Drawer     │
└──────────┴────────────────────────────────────┴────────────────┘
```

## 2.1 路由（产品路由，不是实现）

| 路由 | 页面 | 对应后端阶段 |
|---|---|---|
| `/` | 首页 | 无会话，或选择已有 session |
| `/r/{session}` | 工作台壳 | `GET /api/v30/sessions/{id}/memory` |
| `/r/{session}/copilot` | Research Copilot | `POST /api/v30/route` `POST /api/v30/copilot/turn` `POST /api/v30/plan` |
| `/r/{session}/timeline` | 科研流程 Timeline | 前端根据各步结果合成，可回读 Memory / Plan |
| `/r/{session}/sources` | Source Discovery | Registry + Discover + Source Selection |
| `/r/{session}/mapping` | Schema Mapping | Schema Pack + Matcher Bridge |
| `/r/{session}/graph` | Evidence Graph | Graph Project / Why / Figure Understand |
| `/r/{session}/preview` | Integration Preview | Preview + Prepare |
| `/r/{session}/dataset` | Dataset 输出 | Execute + 旧 task / export |

Timeline 同时是左轨常驻物和可展开的全页。用户永远知道自己在哪一扇门之后。

## 2.2 全局对象（前端状态，全部来自已有 API）

| 对象 | 来源 | 生命周期 |
|---|---|---|
| `session_id` + `MemorySnapshot` | `POST /sessions` `GET .../memory` Copilot / Plan 回写 | 整次研究 |
| `RouteDecision` | `POST /route` 或 Copilot 内嵌 | 每条输入 |
| `PlanResponse` | `POST /plan` | ready 之后 |
| `RegistrySourceList` | `GET /registry/sources` | 按 domain 缓存 |
| `DiscoverResponse` | `POST /discover` | 规划后 |
| `SelectedSourcePlan` | `POST /source-selection` | 发现后 |
| `SchemaPack` | `POST /schema-packs/generate` | 选择后 |
| `FieldMappingResult` | `POST /schema-packs/match` | pack 后 |
| `EvidenceGraph` | `POST /graphs/project` | 映射后 |
| `FigureUnderstandingResult` | `POST /figures/understand` | 可选 |
| `IntegrationPlan` | `POST /integration/preview` | 映射后 |
| `ExecutionRequestPreview` | `POST /integration/prepare` | Preview 确认后 |
| `ExecutionResult` | `POST /integration/execute` | 仅 oncology |
| 旧 `AgentTaskResult` + 导出流 | `GET /api/agent/tasks/{task_id}` `.../export/{fmt}` | 执行成功后只读 |

前端不自造数据集、不自造覆盖率、不自造 Quality 分数。

## 2.3 阶段门（Google 式状态，而不是进度条欺骗）

每个阶段只有四种门状态：

| 门状态 | 含义 | 视觉 |
|---|---|---|
| `idle` | 尚未到达 | 浅灰点 |
| `blocked` | 被规则挡住 | 琥珀，写明 error |
| `ready` | 本步完成，下一步可进 | 墨色勾 |
| `executed` | 仅 Dataset：旧链已跑 | 实心墨点，不是绿灯庆祝 |

阻挡文案必须用后端错误，不得改写：

| 后端 | 界面说法 |
|---|---|
| `research_goal_not_ready` | 研究目标尚未澄清，不能生成方案 |
| `only_oncology_integrate_supported` | 当前只支持医学真实整合 |
| `execution_not_ready` | 执行请求尚未编译完成 |
| `old_runner_not_injected` | 旧执行引擎未注入，不能取数 |
| `source_id_required` | 图理解必须先有来源编号 |
| `session not found` | 会话不存在或已隔离失效 |

---

# 3. 用户流程

主路径不是“用户一直打字，系统一直答”。主路径是**过门**。

```text
进入工作台
  → 说清研究对象与目标          Copilot
  → 必要时只问一个澄清问题        Copilot
  → 生成研究方案（不取数）        Planner
  → 查看已注册来源插件            Registry
  → 发现候选（unverified）        Discovery
  → 选择 / 排除 / 标 Join 风险    Source Selection
  → 绑定或生成 Schema Pack        Schema
  → 预览字段映射（无数据行）      Matcher
  → 追问为什么选、为什么 REVIEW   Evidence Graph
  → 预览将调用的旧工具            Integration Preview
  → 医学：编译并执行              Prepare → Execute
  → 查看质量门、证据、导出        Dataset
  → 非医学：停在 Preview          不进入 Dataset 执行
```

## 3.1 流程 A · HER2 医学主链（完整产品路径）

1. 首页点「新研究」或示例「HER2 阳性乳腺癌耐药」。
2. 系统 `POST /sessions`，进入 Copilot。输入「我想研究HER2阳性乳腺癌耐药机制」。
3. 路由为 `CLARIFY`。右侧 Memory 出现对象，数据需求全部 `not_retrieved`。中间只出现**一个**澄清问题。
4. 用户点选项「疗效预测」。`ready_for_planner=true`。主按钮从「继续澄清」变为「生成研究方案」。
5. 用户补充约束「排除 METABRIC」。Memory.constraints 出现该条，Timeline 记为约束，不是数据缺失。
6. 用户确认后 `POST /plan`。合同草稿、领域 oncology、不自动 freeze。
7. 自动进入 Sources：先展示 Registry 插件条，再 Discover。候选一律 `unverified`。
8. Source Selection：GEO / GDC / cBioPortal 可入选；METABRIC 显示 `reason_code=user_constraint`；`join_risk` 写明禁止患者级跨研究 Join。
9. Mapping：医学 pack 绑定冻结 Canonical Schema，字段含 `her2_status`、`response_domain`、`patient_id`、`sample_id`。映射表可出现 `REVIEW`，无行。
10. Graph：点「为什么 REVIEW」「为什么排除 METABRIC」。确认没有 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`。
11. Preview：列出 `search_geo` / `search_gdc` / `search_cbioportal`，`execution_allowed=false`，`would_invoke=false`。用户点「编译执行请求」。
12. Prepare 成功且 `domain=oncology`、`execution_ready=true` 后，才出现危险确认：「进入现有医学执行链」。执行走 `POST /integration/execute`。
13. Dataset：展示 `task_id`、`quality_status`、证据摘要、可导出格式。主表来自旧 `GET /api/agent/tasks/{task_id}`，导出走旧 export。

此路径才允许出现数据行。

## 3.2 流程 B · Ia 型超新星（诚实停住）

1. **必须新开 session**，与 HER2 隔离。
2. Copilot 识别 `astronomy`。界面禁止出现 `patient_id` / `her2_status` / pCR 芯片。
3. 若仍弹出「机制探索还是疗效预测」，界面把它标成「通用澄清门的现状」，选项含义不是肿瘤疗效。
4. Planner 只出方案草稿，`used_existing_services` 可为空，文案：非肿瘤不是已冻结医学合同。
5. Registry / Discovery：`catalog_only` / `planned`，无 `fetch_binding`，`integrate_eligible=false`。
6. Schema Pack 为任务级 DRAFT，字段是 `sn_id` / `observation_time` / `band` / `flux` / `redshift` / 溯源三件套。
7. Figure Understanding 作为 Graph 页的附表面：可理解光变曲线，大字「未写入主表」。
8. Preview 永久禁用执行。Dataset 页显示空态：「天文真实整合尚未开放」，并引用 `only_oncology_integrate_supported`。

## 3.3 流程 C · 概念问答不启动研究

用户问「什么是HER2」。路由 `CONCEPT_QA`。

- 只在 Copilot 出解释卡
- Memory **不写**研究目标
- Timeline 不点亮 Planner 之后的门
- 不出现 Discover / Execute

闲聊 `CHAT` 同理，更轻：一条回复，无工作流。

## 3.4 流程 D · 未澄清强行规划

用户在 Copilot 点「生成研究方案」但 `ready_for_planner=false`。

- 前端先本地拦截
- 若仍调用，展示 422 `research_goal_not_ready`
- 焦点回到未回答的澄清问题
- 不猜测目标，不跳到 Sources

## 3.5 跨页回看规则

任何已完成步骤都可以回看，回看是只读。重新 Discover / Match / Preview 会生成新对象，旧 Graph / Plan 作为历史版本留在 Timeline，不静默覆盖。

两个研究会话不得共享 Memory、候选、图或执行任务。

---

# 4. 页面设计

以下每个页面都包含：目的、布局、组件、数据来源 API、交互。布局用空间描述，不写实现代码。

---

## 4.1 首页

### 目的

产品门厅。让人在 8 秒内知道：这是科研数据工作台，医学是高质量插件，不是聊天框。

### 布局

三层纵深，大量留白：

```text
[ 顶栏：品牌「研究工作台」· 内核实验室(次级) ]

        从研究想法
        到可追溯的数据工作

        [ 大输入：你想研究什么 ]     ← 唯一主操作
        回车只创建会话并进入 Copilot，不取数

        示例研究（不是快捷执行）
        ┌ HER2 耐药与疗效 ┐  ┌ Ia 超新星光变 ┐
        └ oncology 插件  ┘  └ 规划到 Preview ┘

        工作方式（四枚静默步骤，不可点执行）
        澄清目标 · 发现来源 · 对齐字段 · 预览后再执行
```

不要进度环，不要能力评分，不要 SDTI，不要“已整合 N 个数据集”。

### 组件

| 组件 | 作用 |
|---|---|
| Brand Lockup | 新名建议：**Research Workbench** / 「科研数据工作台」。副标：「医学插件已装载 · 通用入口」 |
| Intent Field | 大号单行/两行输入，占位符用完整研究句，不用“问我任何问题” |
| Domain Hint | 输入时本地浅提示可能领域；真正领域以 Router 为准，首页不锁死 |
| Case Tile | 两个案例磁贴，只预填文本并创建新 session |
| Honesty Line | 一行灰字：发现不是覆盖；预览不是执行；图理解不入库 |
| Session Resume | 若本地有最近 session，右侧轻列表，点入 Timeline |
| Legacy Link | 页脚级「打开内核实验室」，视觉权重最低 |

### 数据来源 API

| 时机 | API |
|---|---|
| 进入首页 | `GET /health`（连接状态） |
| 提交想法 / 点案例 | `POST /api/v30/sessions` |
| 可选预路由 | `POST /api/v30/route`（仅用于首页微文案，不写 Memory） |
| 恢复会话 | `GET /api/v30/sessions/{id}/memory` |

首页**禁止**调用 Discover、Preview、Execute、`/api/agent/tasks`。

### 交互

- Enter：创建 session，把原文带入 Copilot 作为第一轮 `copilot/turn`。
- Shift+Enter：换行。
- 点案例：同样创建**新** session，互不污染。
- 路由若是 `CHAT` / `CONCEPT_QA`：仍进 Copilot，但不点亮后续门。
- 不提供“跳过澄清，直接找数据”。

---

## 4.2 Research Copilot 页面

### 目的

把自然语言收成**研究对象、目标、约束、数据需求建议**。Copilot 是研究秘书，不是回答引擎。

### 布局

Apple 式中轴 + 右侧情境，对话很短：

```text
左：Timeline（Copilot 为当前）

中：
  理解摘要条（对象 / 目标 / 领域）     ← 比聊天气泡更重要
  数据需求建议（Elicit 小表，状态=未检索）
  澄清问题（最多同时 1 个）
  简短回复（不是长答案）
  底部组成器

右：
  Memory：goal / clarifications / constraints
  路由徽章：CHAT / CONCEPT_QA / CLARIFY / PLAN
```

聊天气泡不是主视觉。主视觉是「理解卡 + 需求表 + 一个问题」。

### 组件

| 组件 | 内容 | 交互 |
|---|---|---|
| Understanding Bar | `object` `target` `domain` | 用户可点「这不是我的目标」回到澄清 |
| Data Need Table | category / description / `retrieval_status` | 状态固定显示「未检索」，禁止做成已完成勾 |
| Clarifying Card | 一个问题 + 选项按钮 + 自由补充 | 选完立即 `copilot/turn` |
| Constraint Chip | 如「排除 METABRIC」 | 输入「排除…」后写入 Memory，可删除后重说 |
| Route Pill | 当前 `RouteKind` | 只读 |
| Reply Block | `user_visible_reply` | 短文本，不做打字机长文 |
| Plan CTA | 「生成研究方案」 | 仅 `ready_for_planner=true` 可点 |
| Block Banner | `blocked_reason` | 说明为何不进 Planner |

### 数据来源 API

| 动作 | API | 关键字段 |
|---|---|---|
| 每轮输入 | `POST /api/v30/copilot/turn` | `understood_goal` `suggested_data_needs` `clarifying_questions` `ready_for_planner` `memory` |
| 可选预判 | `POST /api/v30/route` | `route` `domain` `fallback` |
| 刷新记忆 | `GET /api/v30/sessions/{id}/memory` | goal / clarifications / constraints |
| 生成方案 | `POST /api/v30/plan` | `contract` `planning_v2` `notice` `used_existing_services` |

成功 Plan 后自动把 Timeline 推到「方案已生成」，并建议进入 Sources，不自动 Discover。

### 交互

- 选项按钮优先于打字。打字用于约束和修正。
- CONCEPT_QA：显示概念卡，Plan CTA 隐藏。
- 未 ready 点 Plan：展示 `research_goal_not_ready`，滚动到澄清卡。
- 医学与天文用同一组件，靠 `domain` 换芯片颜色与禁用字段词库，不换两套 UI。
- 不在此页展示数据集、质量分、Adapter 日志。

---

## 4.3 科研流程 Timeline

### 目的

Google 式状态反馈：整次研究的可审计时间线。它是产品脊骨，不是装饰进度条。

### 布局

两种密度共用同一数据：

**左轨（常驻）** 窄、竖、8 个节点，只显示门状态。  
**全页（`/timeline`）** 宽、横+详，每步一张事件卡。

```text
01 会话成立
02 目标澄清        ready_for_planner
03 研究方案        PlanResponse
04 来源发现        Discover + Selection
05 字段对齐        Pack + Mapping
06 证据可问        Graph / Why / Figure
07 执行预览        Preview + Prepare
08 数据产出        仅 oncology Execute
```

### 组件

| 组件 | 规则 |
|---|---|
| Gate Node | idle / blocked / ready / executed，禁止用百分比冒充完成度 |
| Event Card | 时间、API 名、一句话结果、对象 ID（session / pack / graph / plan / task） |
| Constraint Event | 单独样式：用户约束，不是系统没找到 |
| Honesty Event | 如 `fetched=false` `enters_primary_table=false` `execution_allowed=false` |
| Jump Control | 点节点进入对应工作面；未解锁节点不可跳 |
| Diff Note | 若用户重跑 Discover，旧事件折叠为「历史」，新事件为当前 |

### 数据来源 API

Timeline **没有**独立后端。前端把下列回包编成事件：

- Memory：`GET .../memory`
- Plan：`POST /plan` 的 `contract_id` `notice`
- Discover：`fetched` `integrated` `notice` 候选数
- Selection：入选/排除数、`join_risk`、`reason_code`
- Pack / Match：`binding` `status` `row_count=0`
- Graph：`graph_id` `contains_patient_edges=false`
- Figure：`figure_type` `enters_primary_table`
- Preview / Prepare：`execution_allowed` `execution_ready` `tool_candidates`
- Execute：`task_id` `quality_status` `export_available`

### 交互

- 默认自动跟随最新未完成门。
- 全页可筛选：约束 / 拒绝 / REVIEW / 执行。
- 不允许用户“标记完成”。完成只由 API 回包决定。
- 天文流程在 08 永远 `blocked`，文案引用只支持 oncology。

---

## 4.4 Source Discovery 页面

### 目的

Perplexity 式来源工作面：先看见插件能力，再看见候选卡片，再做选择。发现是假设，选择是判断。

### 布局

上薄下主：

```text
[ Registry Strip ]  当前领域已注册插件（能力目录，不是数据）

[ 工具条 ]  Discover · 应用约束 · 选择

中：候选瀑布（来源卡）
右：选择摘要 + Join 风险 + 覆盖假设（不是覆盖事实）
```

### 组件

**Registry Chip**

- `display_name` `domain` `resource_kind` `status`
- `fetch_binding` 有则显示旧工具名（`search_gdc`）
- `integrate_eligible=false` 显示「不可整合」
- `catalog_only` / `planned` 用空心徽章，不用下载图标

**Source Card（Perplexity 来源卡）**

| 区域 | 字段 |
|---|---|
| 眉题 | `source_key` · `resource_kind` |
| 定位 | `locator.locator_type` + `value` |
| 来源编号 | `source_id`（必显） |
| 假设字段 | `field_hypotheses[]`，每条旁标注 `coverage_claimed=false` |
| 验证 | `verification_status=unverified` 固定灰章 |
| 下一步 | `next_action` |
| 资格 | `integrate_eligible` `registry_status` |

禁止在卡片上画“已覆盖 80%”。`coverage_status=unknown` 就写未知。

**Selection Board（Elicit 表）**

列：来源 | 假设字段 | 决定 | 理由码 | Join 风险

行分两组：`selected_candidates` / `rejected_candidates`。  
METABRIC 排除必须能看到 `reason_code=user_constraint`。

**Risk List**

`join_risk` 用警告条，不是小字。医学默认强调：禁止跨研究患者 Join；`response_domain` 与粒度只读展示。

### 数据来源 API

| 动作 | API |
|---|---|
| 打开页面 / 切领域 | `GET /api/v30/registry/sources?domain=` |
| 发现 | `POST /api/v30/discover` |
| 选择 | `POST /api/v30/source-selection` |

Discover 入参来自 Plan / Memory：`domain` `topic` `contract_id`，可选 `required_modalities` `field_gaps`。  
Selection 入参：全部 candidates + `SelectionContract`（goal / required_fields / response_domain / data_granularity）+ Memory.constraints。

### 交互

- 打开页面不自动 Discover；用户点「发现候选」。
- Discover 后 `fetched` `integrated` 必须在页眉以否定句出现：「未取数 · 未整合」。
- 用户不能把 `unverified` 手工改成 verified。
- 用户不能强行勾选 `planned` 为可执行源；若后端拒绝，展示 `reason`。
- 选择完成后 CTA：「进入字段对齐」，不出现「开始下载」。

---

## 4.5 Schema Mapping 页面

### 目的

Elicit 式字段工作面：左边是契约字段，右边是映射判断。这是对齐，不是出表。

### 布局

双栏，中间一条细映射带：

```text
左 Schema Pack                 右 Mapping Table
绑定方式 / 冻结或 DRAFT         源字段 → 目标字段
字段清单 + 风险 + 允许值        confidence / AUTO|REVIEW / risk
溯源三件套始终置顶              页脚：row_count = 0
```

医学与天文同一表格骨架。医学 pack 额外冻结条：绑定 `canonical_schema.yaml`，不可编辑字段名。

### 组件

| 组件 | 规则 |
|---|---|
| Pack Header | `schema_pack_id` `domain` `entity_type` `binding` `status` |
| Frozen Banner | 医学：`binding=frozen_canonical`，「不是新生成的医学标准」 |
| Draft Banner | 天文：任务级 DRAFT，「不是冻结标准」 |
| Field List | name / description / required / risk_level / allowed / frozen |
| Required Trio | `source_id` `raw_field` `raw_value` 始终置顶且不可隐藏 |
| Medical Trio | oncology 必显 `response_domain` `patient_id` `sample_id` |
| Mapping Table | 每行一条 `FieldMapping` |
| Status Token | `AUTO` 墨色，`REVIEW` 琥珀，禁止绿勾表示“已采用该值” |
| Empty Rows | 固定文案：`generates_data=false`，`row_count=0` |
| Risk Callout | HER2 IHC 2+、AUC/IC50 ≠ pCR 作为只读医学约束，不让用户关 |

### 数据来源 API

| 动作 | API |
|---|---|
| 生成/绑定 pack | `POST /api/v30/schema-packs/generate` |
| 回看 pack | `GET /api/v30/schema-packs/{schema_pack_id}` |
| 预览映射 | `POST /api/v30/schema-packs/match` |

Match 的 `source_fields` 来自 Selection 的假设字段或用户粘贴的列名。本页不上传 CSV 文件冒充已整合。

### 交互

- 生成 pack 后默认不自动 match；用户点「预览映射」。
- 点某一 `REVIEW` 行：打开右侧 Why 预览（若图已投影）或提示先去 Graph。
- 用户不能把 `her2_status` 允许值改成自动 Positive。
- 用户不能删除 `response_domain`。
- CTA：「查看证据关系」或「进入执行预览」。两端都允许，因为 Graph 与 Preview 都是规划层。

---

## 4.6 Evidence Graph 页面

### 目的

解释工作面：为什么选这个源、为什么这样映射、为什么 REVIEW、为什么排除。图是投影，不是患者关系网，也不是事实库。

### 布局

空间感最强的一页。中央是疏图，四周是空气，右侧是 Why Drawer。

```text
顶：图声明
  不替代 EvidenceBuilder · 不含患者边 · 不复制事实值

中：节点画布（少、大、可点）
右：Why Drawer（语句 + 路径 + 边）

底可选：Figure Understanding 条
```

节点宜少。宁可用 12 个可读节点，不要 200 个点的力导向秀。

### 组件

**Graph Canvas**

建议节点类型与颜色角色（不是领域彩绘）：

| node_type | 视觉角色 |
|---|---|
| UserGoal / Constraint | 最淡的墨，起点 |
| Contract / SchemaPack | 纸卡片 |
| Candidate | 空心来源卡 |
| SelectedSource | 实线来源卡 |
| FieldMapping | 细标签，REVIEW 带琥珀点 |
| FigureUnderstanding | 虚线框，标明不进表 |

边只显示后端 `edge_type` + `reason`。若 `forbidden_edges_present=true`，全页进入错误态，而不是悄悄画出来。

**Why Drawer（Perplexity 引用面板）**

打开某个 `finding_id` 后展示：

- `statement`
- `why[]` 逐条
- `path[]` 面包屑节点
- `edges[]`
- `forbidden_edges_present`

这是产品里“问为什么”的唯一正式位置。

**Figure Strip**

| 字段 | 展示 |
|---|---|
| `figure_type` | 如 light_curve |
| `x_axis` / `y_axis` | 轴 |
| `digitization_possible` | 可以写“可人工数字化” |
| `enters_primary_table` | **永远用否定大字：未写入主表** |
| `row_count` | 0 |

缺 `source_id` 时表单不能提交，错误用 `source_id_required`。

### 数据来源 API

| 动作 | API |
|---|---|
| 投影 | `POST /api/v30/graphs/project` |
| 回看 | `GET /api/v30/graphs/{graph_id}` |
| 追问 | `GET /api/v30/graphs/{graph_id}/why/{finding_id}` |
| 图理解 | `POST /api/v30/figures/understand` |

Project 入参拼装已有对象：goal、contract、candidates、selection、schema_pack、mappings、constraints。不传患者行。

### 交互

- 进入页面时，若尚无 graph，点「生成解释图」。
- 单击节点 = 打开 Why（若该节点有 finding）；双击不进编辑。
- 不允许拖拽改关系。图只读。
- 搜索框只搜 label / finding，不做“问图聊天”。
- Figure 理解成功后，可把 `graph_id` 链回同一图，新增 EXTRACTED_FROM 类节点，仍无观测点数值。

---

## 4.7 Integration Preview 页面

### 目的

执行前的合同页。像发布前检查清单，不像运行监控。默认立场是**还不能跑**。

### 布局

一张居中的 Plan Sheet，左右留白：

```text
        Integration Plan
        execution_allowed = false

        将可能调用的旧工具
        必填字段
        Join 政策
        医学约束

        [ 编译执行请求 ]     主按钮
        [ 进入真实整合 ]     默认禁用，Prepare 且 oncology 后才亮
```

### 组件

| 组件 | 字段与规则 |
|---|---|
| Verdict Banner | 默认红/墨双色陈述：`execution_allowed=false`，「这是规划，不是执行」 |
| Adapter List | `source_key` `fetch_binding` `integrate_eligible` `would_invoke=false` |
| Binding Empty | `fetch_binding=null` 显示「无旧工具可调」 |
| Field Requirements | `field_requirements` 芯片 |
| Mapping Recap | 只读回放 `field_mappings` |
| Join Policy | oncology 固定 `forbid_cross_entity`，放大显示 |
| Medical Constraints | IHC 2+、AUC/IC50、patient/sample 分界，只读 |
| Expected Outputs | 全部标注 not generated / not executed |
| Prepare Sheet | `ExecutionRequestPreview`：`tool_candidates` `execution_ready` `executed=false` |
| Execute Gate | 双步确认。文案必须写：将转调现有 `ResearchAgentService`，v30 不直接打 Adapter |
| Domain Lock | 非 oncology：Execute 永久禁用，展示 `only_oncology_integrate_supported` |

### 数据来源 API

| 动作 | API | 输出 |
|---|---|---|
| 预览 | `POST /api/v30/integration/preview` | `IntegrationPlan` |
| 编译 | `POST /api/v30/integration/prepare` | `ExecutionRequestPreview` |
| 执行 | `POST /api/v30/integration/execute` | `ExecutionResult` |

Preview 入参：selected sources、`schema_pack_id`、mappings、`contract_id`、domain、`response_domain`、granularity、goal。

### 交互

- 进入本页自动 Preview 一次（只读规划，不取数）。
- 「编译执行请求」才调用 Prepare。编译成功仍 `executed=false`。
- 「进入真实整合」使用系统对话框：输入研究问题确认句（可预填 Memory 目标）。取消是默认焦点。
- 天文 / 材料：按钮不可聚焦到执行，辅助技术读出“当前领域不支持真实整合”。
- 执行中跳到 Dataset 的等待态；成功才填 `task_id`。
- 失败：422/503 原文案，Timeline 记 blocked，不重试循环。

---

## 4.8 Dataset 输出页面

### 目的

执行之后的 Elicit 主表 + Perplexity 证据抽屉 + Quality 门面。没有执行时，本页是诚实空态，不是假表。

### 布局

```text
顶：Execution Result 条
    task_id · status · quality_status · export_available

中：科研主表（旧任务行）
    固定列优先：source_id / raw_field / raw_value / patient_id / sample_id / response_domain

右：Quality + Evidence Drawer
    点单元格打开字段证据

底：导出动作（旧 export 流）
```

### 组件

**Result Strip**

来自 `ExecutionResult`：

- `task_id` `status` `quality_status`（PASS / REVIEW / REJECT）
- `evidence_summary`：是否有 source_id / raw_field / raw_value / evidence / 行数
- `join_policy` `medical_constraints`
- `notice`：已转调现有执行链，v30 未直接调用 Adapter

Quality 颜色只服务三态，不把 REVIEW 画成成功绿。

**Research Table**

- 行数据**不**来自 v30 捏造，而来自 `GET /api/agent/tasks/{task_id}` 的 `modeling_dataset`
- 无行：只显示 metadata / quality_report 可导出，并写「没有可导出的科研数据行」
- companion / 分研究表若存在，用页签分开，禁止一个 Tab 叫“合并队列”
- 单元格左上角小点：有 Evidence 的字段可点

**Evidence Drawer**

优先走冻结契约：`GET /api/v3/evidence/field/{record_id}/{field}`  
展示 `evidence_id` `canonical_value` `raw_field` `raw_value` `source_id` `confidence` `status`。  
没有 Evidence 的关键字段：显示阻断，而不是补一个模型解释。

**Export Bar**

`export_formats` 映射到：

`GET /api/agent/tasks/{task_id}/export/{csv|xlsx|json|parquet|metadata|quality_report}`

按钮在 `export_available=true` 时可用。CSV 在无行时应按旧服务失败并展示原因。

**Empty / Blocked States**

| 状态 | 页面 |
|---|---|
| 尚未 Preview | 「先完成执行预览」 |
| 已 Prepare 未执行 | 显示编译摘要，主表空 |
| 非 oncology | 整页说明只支持医学整合 |
| 执行失败 | 后端 error，无假行 |

### 数据来源 API

| 动作 | API |
|---|---|
| 执行 | `POST /api/v30/integration/execute` |
| 读主表 / 质量 / 工具调用 | `GET /api/agent/tasks/{task_id}` |
| 导出 | `GET /api/agent/tasks/{task_id}/export/{file_format}` |
| 字段证据 | `GET /api/v3/evidence/field/{record_id}/{field}` |

禁止为了画表去打 `/api/adapters/*`。那是内核实验室的事。

### 交互

- 默认排序不跨 `study_key`。
- 过滤可按 source_id、response_domain、quality。
- 点击 HER2 相关单元格：抽屉必须能看到原始值；若为 IHC 2+，界面复述规则「不得自动判为 Positive」，不提供“一键纠正为阳性”。
- 导出前若 `quality_status=REJECT`，仍允许下载数据包，但页眉标明不可作为正式发布。`publish_allowed` 若为假，禁用任何“发布”措辞。
- 不展示新的 SDTI 成绩。

---

# 5. 页面一览（布局 / 组件 / API / 交互）

下表供设计与后续实施对照，不增加新接口。

| 页面 | 布局骨架 | 核心组件 | 主 API | 主交互 |
|---|---|---|---|---|
| 首页 | 中轴门厅 | Intent Field、Case Tile | `POST /sessions` `GET /health` | 创建会话，不取数 |
| Copilot | 理解卡 + 短对话 + Memory | Understanding Bar、Need Table、Clarify Card | `/copilot/turn` `/route` `/plan` `/memory` | 澄清后才能规划 |
| Timeline | 左轨 + 全页事件 | Gate Node、Event Card | 合成上述回包 | 回看与跳转，不标记完成 |
| Sources | Registry 条 + 卡片瀑布 + 选择表 | Source Card、Selection Board | `/registry/sources` `/discover` `/source-selection` | 发现≠覆盖，选择可排除 |
| Mapping | Pack \| Mapping | Frozen/Draft Banner、Mapping Table | `/schema-packs/generate` `GET pack` `/match` | 无数据行 |
| Graph | 疏图 + Why Drawer | Canvas、Why、Figure Strip | `/graphs/project` `GET graph` `/why` `/figures/understand` | 只读追问 |
| Preview | 居中清单 | Verdict、Adapter List、Execute Gate | `/integration/preview` `/prepare` `/execute` | 默认不执行 |
| Dataset | 表 + Quality + 导出 | Result Strip、Research Table、Evidence Drawer | `/execute` + 旧 `/api/agent/tasks` + `/export` + `/api/v3/evidence` | 仅 oncology 有行 |

---

# 6. 视觉设计

目标气质：**一张干净的研究书桌**，不是仪表盘，不是聊天 App。

## 6.1 颜色

只用一套中性底，状态色专职语义，品牌不抢医学红。

| Token | 值 | 用途 |
|---|---|---|
| `--paper` | `#F4F3EF` | 页面底，暖灰，空间感 |
| `--panel` | `#FFFEFB` | 卡片，近白 |
| `--ink` | `#1C1B19` | 主文字 |
| `--muted` | `#6F6B64` | 说明、未检索、catalog |
| `--line` | `#E6E1D8` | 细线，少阴影 |
| `--accent` | `#1C1B19` | 主按钮用墨，不用鲜蓝铺满 |
| `--focus` | `#2F6FED` | 仅焦点环与链接，面积小 |
| `--review` | `#A15C12` | REVIEW / blocked |
| `--review-soft` | `#F8EEDD` | REVIEW 底 |
| `--reject` | `#9B1C1C` | REJECT / 禁止 Join / 未写入主表 |
| `--reject-soft` | `#F8E8E8` | 危险底 |
| `--pass` | `#1F6B4A` | 仅 Quality PASS |
| `--pass-soft` | `#E7F3EC` | 仅 PASS 底 |
| `--unverified` | `#8A8680` | 发现候选默认章 |

规则：

- 不要用绿色表示“已发现”“已映射”“已理解”。绿只给 Quality PASS。
- 不要用渐变英雄区。
- 领域不用彩码系统：oncology / astronomy 只靠文字徽章。
- 暗色模式本阶段不做。科研阅读优先稳定纸感。

## 6.2 字体

| 角色 | 建议 | 用法 |
|---|---|---|
| 中文 UI | `"Source Han Sans SC"` / `"Noto Sans SC"` / PingFang SC | 正文、按钮 |
| 英文 UI | `"Source Sans 3"` / SF Pro Text | 英文标签 |
| 展示标题 | 同族 Semibold，字距 -0.02em | 首页标题、页眉研究名 |
| 等宽 | `"IBM Plex Mono"` / Cascadia / ui-monospace | source_id、task_id、字段名、API error |
| 数字 | 等宽或 tabular-nums | confidence、行数 |

层级：

- 首页主标题 40–48 / 1.15
- 页面标题 22–24 / 1.25
- 卡片标题 15–16 / 1.35
- 正文 14 / 1.6
- 元信息 12 / 1.45
- 等宽 ID 11–12

不要用装饰衬线装学术。学术感来自表格与编号，不是 Garamond 海报。

## 6.3 间距与栅格

- 基准 8px。组件内 8 / 12 / 16，区块 24 / 40 / 64。
- 工作台壳：左轨 240、中列自适应、右轨 320。大屏右轨可到 360；小于 1100 右轨改为抽屉。
- 内容最大阅读宽：Copilot 理解区 720；Preview 清单 800；表格全宽。
- 卡片圆角 12，按钮 10，徽章 6。不要 24 以上的胶囊玩具感。
- 阴影只有一层：`0 1px 2px rgba(28,27,25,.06)`。层次靠留白和线，不靠投影堆叠。
- 密度：表格行高 40–44；来源卡内边距 16–20。不要把 Elicit 表做成 Excel 拥挤风。

## 6.4 动画

原则：状态被看见，元素不表演。

| 场景 | 动效 | 时长 |
|---|---|---|
| 页间切换 | 中列内容 8px 上移 + 淡入 | 180ms |
| Timeline 门点亮 | 圆点缩放 0.92→1 | 160ms |
| Why Drawer | 右侧推入 | 200ms |
| 来源卡出现 | 按列表依次 20ms 错开淡入，最多 6 张 | 160ms |
| REVIEW 高亮 | 背景淡入，不闪 | 120ms |
| 执行确认 | 无庆祝彩屑；按钮进入 spinner | — |
| 降低动态 | 遵循 `prefers-reduced-motion`，全部改为瞬时 |

禁止：打字机长回复、骨架屏假造表行、Lottie 大脑、粒子、自动轮播案例。

Copilot 等待用**静态状态句**：「正在理解研究对象」，不要假百分比。真正长的只有 oncology Execute，用明确句：「正在转调现有医学执行链」，并列出将出现的工具名。

## 6.5 组件规范

### 按钮

| 类型 | 外观 | 何时用 |
|---|---|---|
| Primary | 墨底白字 | 每页最多 1 个：生成方案 / 发现候选 / 编译请求 |
| Secondary | 线框 | 回看、投影图、打开 Why |
| Danger | 线框红字，确认后才实心 | 进入真实整合 |
| Ghost | 无底 | 内核实验室、取消 |
| Disabled | 50% 墨 + 旁注 | 未过门；禁用必须有原因句 |

### 徽章

统一小写语义，不用图标代替文字：

`unverified` `catalog_only` `planned` `not_retrieved` `AUTO` `REVIEW` `PASS` `REJECT` `forbid_cross_entity` `未写入主表` `未取数` `未整合`

### 卡片

- Source Card：上眉等宽 ID，中部 3–5 行，底部状态。可点开，不在卡内塞按钮丛。
- Understanding Card：无边框或极淡线，像纸上的摘要，不像聊天气泡。
- Plan Sheet：像一页合同，顶部 verdict，底部动作。

### 表格

- 表头固定，列可调整但不改语义。
- 空单元格显示「—」，不填模型猜测。
- `confidence` 用 0.62 数字，不用五星。
- 状态列只允许后端枚举。

### 输入

- 组成器固定在 Copilot 底部，不悬浮成聊天岛。
- 占位符写完整研究句。
- 澄清用大选项按钮，每项一行可读句子。

### 空态 / 错态

空态：一句话 + 一个合法下一步。  
错态：等宽 error 码 + 人话 + 回到造成它的那一页。  
不要插画吉祥物。

### 无障碍

- 门状态不只靠颜色。
- Why Drawer 可键盘关闭。
- 执行危险按钮默认焦点在「取消」。
- 跳过链接保留。
- 中文界面，ID 用等宽原文，不翻译 `source_id`。

---

# 7. 前端目录设计

不写代码。目录表达**产品表面与职责隔离**，并与现有静态前端共存。

建议新工作台作为独立入口，由 FastAPI 继续托管静态文件。不在本设计中引入必须换框架的决策；若后续实施选用原生模块或轻量 SPA，应对齐下面边界。

```text
frontend/
  index.html                         现有旧工作台（降级为内核实验室入口）
  app.js                             现有旧逻辑，不承接 /api/v30
  styles.css                         现有旧视觉
  ...

  v31/
    index.html                       V3.1 工作台唯一 HTML 壳
    README.md                        页面与 API 对照（实施时再写）

    styles/
      tokens.css                     颜色 / 间距 / 字体 token
      base.css                       重置、排版、焦点环
      shell.css                      顶栏、左轨、右轨
      pages/
        home.css
        copilot.css
        timeline.css
        sources.css
        mapping.css
        graph.css
        preview.css
        dataset.css
      components/
        badges.css
        cards.css
        tables.css
        drawers.css
        gates.css

    app/
      main.js                        启动、路由、壳
      router.js                      产品路由 /r/{session}/...
      session-store.js               session_id 与 Memory 为唯一真相
      timeline-store.js              把门事件写成只读日志
      api/
        v30.js                       只封装 /api/v30/*
        agent-export.js              只封装执行后的旧 task/export/evidence
        health.js                    GET /health
      pages/
        home.js
        copilot.js
        timeline.js
        sources.js
        mapping.js
        graph.js
        preview.js
        dataset.js
      components/
        understanding-bar.js
        data-need-table.js
        clarify-card.js
        source-card.js
        selection-board.js
        mapping-table.js
        graph-canvas.js
        why-drawer.js
        figure-strip.js
        plan-sheet.js
        execute-gate.js
        research-table.js
        evidence-drawer.js
        quality-strip.js
        gate-node.js
      copy/
        honesty.zh.js                固定诚实文案：未取数 / 未入库 / 仅 oncology
        medical-constraints.zh.js    IHC 2+、AUC/IC50、forbid_cross_entity
```

## 7.1 分层纪律

1. `pages/*` 只编排组件与过门，不直接 `fetch` 散落。
2. `api/v30.js` 不得调用 `/api/adapters/*`。
3. `api/agent-export.js` 只能在 Dataset 且已有 `task_id` 后使用。
4. `session-store.js` 按 session 隔离；切换研究 = 换路由，不在内存里混 HER2 与超新星。
5. `copy/honesty.zh.js` 是产品文案源，禁止页面随手写“已验证覆盖”。
6. 旧 `frontend/app.js` 不引用 `frontend/v31/`。新壳可以用一个页脚链回旧 `index.html#task-entry`。

## 7.2 建议入口

| URL | 产品 |
|---|---|
| `/v31/` 或 `/workbench/` | V3.1 科研智能工作台（新默认） |
| `/` | 过渡期可重定向到工作台，或保留旧门厅并放「进入 V3.1」 |
| `/#task-entry` | 内核实验室（旧执行面） |

实施时若把 `/` 切到 V3.1，必须保留旧页面可达，以满足“旧入口行为不改”。

## 7.3 明确不建的目录

- 不建 `chat/` 独立聊天产品
- 不建 `eval/` 成绩看板
- 不建 `adapters/` 前端直连层
- 不建 `theme-dark/`
- 不把 Figure 数字化画成编辑器
- 不把天文 Dataset 做成“即将推出”的假表模板

---

# 8. 文案与产品语言

| 不要说 | 要说 |
|---|---|
| 已为你找到数据 | 发现了未验证候选 |
| 已覆盖这些字段 | 假设可能包含这些字段 |
| 开始研究 | 生成研究方案 / 发现候选 / 编译执行请求 |
| 智能整合完成 | 已转调现有医学执行链 |
| 图已数字化入库 | 图已理解，未写入主表 |
| 跨队列患者已对齐 | 禁止跨研究患者 Join |
| 问我任何问题 | 告诉我你想研究什么 |

主按钮动词随门变化，永不使用「发送并开始研究」作为 V3.1 CTA。

---

# 9. 与 Demo 设计的关系

`DEMO_DESIGN_REPORT.md` 写的是评委 8 分钟怎么走 API。本文是产品该长成什么样。

演示顺序映射到页面：

1. 首页定位（10–20 秒）
2. Copilot 澄清 HER2
3. Timeline 显示过门
4. Sources 看 unverified 与排除 METABRIC
5. Mapping 看冻结 pack 与 REVIEW
6. Graph 问为什么
7. Preview 念 `execution_allowed=false`，再决定是否演示 oncology Execute
8. 超新星另开会话，停在 Preview + Figure「未写入主表」

若现场只演示规划闭环，不要打开 Dataset 主表，以免和 Preview 的诚实立场打架。Dataset 是医学插件的生产能力，不是通用入口的默认高潮。

---

# 10. 范围外（本设计故意不做）

- 不设计诊疗建议、患者主页、随访提醒
- 不设计天文 / 材料真实 Integrate 界面细节
- 不设计 `/api/v30/extract`（后端尚未作为本工作台主链）
- 不设计新的评测成绩页
- 不设计把旧五阶段向导换皮成 V3.1
- 不写 HTML / CSS / JS

---

# 11. 验收标准（给后续实施，不是本阶段任务）

一句话能对评委说清：

> 这不是聊天机器人。用户在一条时间线上完成澄清、发现、对齐、解释和预览；只有医学插件就绪时，才进入现有执行链，并把带证据的表拿出来。

页面级验收：

1. 首页提交不触发 Adapter。
2. 未澄清无法进入 Plan。
3. Discovery 卡片可见 `unverified` 与 `source_id`。
4. Mapping 页 `row_count` 恒为 0，直到 Dataset。
5. Graph 能回答 REVIEW 与用户约束，且无跨研究患者边。
6. Preview 默认不能执行。
7. 天文执行按钮不可用。
8. oncology 执行后表中仍有 `source_id` / 原始字段 / Quality。
9. 旧内核实验室仍可单独打开，互不抢会话。

本文件到此结束。下一步若实施，应另开任务，按页面逐个接线，而不是一次重写整个 `frontend/app.js`。
