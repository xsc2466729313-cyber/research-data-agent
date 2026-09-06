# V3.1 Demo 展示流程设计

- 日期：2026-09-05
- 性质：演示设计，不是代码，不是实施授权
- 时长目标：5–8 分钟
- 分支能力基线：`feat/v31-phase1-copilot` 已完成 Router → Copilot → Memory → Planner → Registry → Discovery → Selection → Schema Pack → Matcher Bridge → Evidence Graph → Figure Understanding → Integration Preview

本演示讲的是：**通用科研数据智能体 + 医学高质量插件**。  
不是“已经自动下载并整出主表”，也不是“前端已经接好 V3.1”。

---

## 0. 演示前必须承认的现状

### 后端已经能串起来的闭环

从一句话到“如果执行会怎样”的规划链，API 已通：

```text
会话 → 路由 → Copilot/Memory → Planner
     → Registry → Discover → Source Selection
     → Schema Pack → Matcher Bridge
     → Evidence Graph（为什么选、为什么映射、为什么 REVIEW）
     → Figure Understanding（只理解图，不进表）
     → Integration Preview（execution_allowed=false）
```

这是**规划与诚实性闭环**，不是**取数与发布闭环**。

### 前端尚未接 V3.1

`frontend/` 当前**没有**任何 `/api/v30` 调用。现有页面仍是旧肿瘤规划工作台 + 高级工作台（`/api/v3`、`/api/agent/tasks`）。

因此本场比赛演示的主路径是：

1. 开场用首页说明定位（10–20 秒，不要点“发送并开始研究”）
2. 主戏走 `/docs`（Swagger）或预先准备的 API 响应卡片
3. 需要证明医学内核仍在时，才**口头**指向旧高级工作台，不当成 V3.1 新 Integrate

若把旧工作台的“开始研究”当成 Copilot 演示，会误触发 `ResearchAgentService` 取数，评委容易以为 V3.1 已经真实 Integrate。

---

## 1. 8 分钟时间盒

| 时间 | 段落 | 目的 |
|---|---|---|
| 0:00–0:40 | 一句定位 | 通用智能体，医学是插件 |
| 0:40–4:20 | 案例 1 HER2 | 医学主链：澄清、冻结 schema、禁 Join、预览不执行 |
| 4:20–7:00 | 案例 2 超新星 | 证明不是医学系统：catalog_only、任务 pack、图理解不入库 |
| 7:00–8:00 | 闭环与边界 | 规划闭环已形成；生产闭环仍走旧内核，本轮不演示 |

超时优先级：砍超新星的 Matcher 细节，保住 Figure Understanding 和 `execution_allowed=false`。

---

## 2. 案例 1：HER2 阳性乳腺癌耐药机制

### 2.1 用户输入（按这个顺序，现网规则能跑通）

| 轮次 | 用户原话 | 预期路由 |
|---|---|---|
| 0（可选，15 秒） | `什么是HER2` | `CONCEPT_QA` |
| 1 | `我想研究HER2阳性乳腺癌耐药机制` | `CLARIFY` |
| 2 | `疗效预测` | 补齐澄清，`ready_for_planner=true` |
| 3 | `排除 METABRIC` | 写入 Memory 约束 |

不要在未澄清时说“开始找数据”。Planner 未 ready 会 422：`research_goal_not_ready`。

### 2.2 AI 每一步展示什么

**第 0 步 · 概念问答（可选）**

- 展示：HER2/ERBB2 是生物标志物解释
- 必须说：这不是取数，不是诊断
- Memory：不写研究目标

**第 1 步 · Copilot 复述**

- 对象：`HER2阳性乳腺癌`
- 目标：`耐药机制分析`
- 数据需求：临床结局 / 表达 / 突变 / 药物响应，且全部 `not_retrieved`
- 只问一个问题：机制探索还是疗效预测？

**第 2 步 · 澄清完成**

- Memory 同时有 goal + 澄清答案 `疗效预测`
- `ready_for_planner=true`
- 注意：Copilot 回复里可能仍有“本阶段还不会自动生成方案”的旧措辞。演示时不要念这句，直接调 Planner。

**第 3 步 · 约束**

- Memory.constraints 出现 `排除 METABRIC`
- 强调：这是用户约束，不是数据缺失

**第 4 步 · Planner**

- 转调现有 RequirementAgent / ResearchPlanning / ResearchPlanningV2
- 展示合同草稿：研究目标、领域 oncology
- 必须说：本步不取数、不自动 freeze

**第 5 步 · Registry + Discovery**

- Registry：gdc / geo / cbioportal 等医学插件，`fetch_binding` 指向旧工具名
- Discovery：候选 `verification_status=unverified`，`coverage_claimed=false`，`fetched=false`

**第 6 步 · Source Selection**

- GEO/GDC 可被选中（假说覆盖，不是已取数）
- METABRIC：`reason_code=user_constraint`
- `join_risk`：禁止患者级跨研究 Join
- `fetched=false`，`integrated=false`

**第 7 步 · Schema Pack + Matcher**

- `schema_pack_id=oncology_canonical_v0.1`，`binding=frozen_canonical`
- 字段含 `her2_status`、`response_domain`、`patient_id`、`sample_id`
- 映射示例：`her2 → her2_status`，高风险可进 `REVIEW`
- `row_count=0`，`generates_data=false`

**第 8 步 · Evidence Graph**

- 字段来源链：UserGoal → Contract → Candidate → SelectedSource → FieldMapping
- `why`：REVIEW 因为置信度/风险，不是已经采用该值
- METABRIC 排除显示为约束发现
- 无 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`

**第 9 步 · Integration Preview（收束）**

- `adapter_candidates`：`search_geo` / `search_gdc`
- `would_invoke=false`
- `join_policy=forbid_cross_entity`
- `execution_allowed=false`
- 预计产出全部写着 not generated / not executed

### 2.3 调用哪些模块

```text
POST /api/v30/sessions
POST /api/v30/route                 （可选）
POST /api/v30/copilot/turn          ×3
GET  /api/v30/sessions/{id}/memory
POST /api/v30/plan
GET  /api/v30/registry/sources?domain=oncology
POST /api/v30/discover
POST /api/v30/source-selection
POST /api/v30/schema-packs/generate
POST /api/v30/schema-packs/match
POST /api/v30/graphs/project
GET  /api/v30/graphs/{graph_id}
GET  /api/v30/graphs/{graph_id}/why/{finding_id}
POST /api/v30/integration/preview
```

不要调用：`/api/agent/tasks`、`/api/adapters/*`、`ResearchAgentService.run`、任何 download/CSV 接口。

### 2.4 前端应该展示哪些页面

**现在能用的：**

| 页面 | 用法 | 时长 |
|---|---|---|
| 规划工作台首页 `#planning-workspace` | 只展示“从想法到可开始的数据工作”，**不要提交表单** | 10 秒 |
| Swagger `/docs` | 按上表逐步点 V3.1 接口 | 主戏 |
| 右侧旧面板（研究方案/数据准备） | **不要在本案例打开**，避免和 v30 结果混在一起 | — |

**如果之后接上前端，应按这个顺序出卡片，而不是出一张大表：**

1. 对话区：复述目标 + 一个澄清问题
2. Memory 条：对象 / 重点 / 排除 METABRIC
3. Registry 插件条：医学来源 + 工具绑定名
4. Discovery 列表：unverified 徽章
5. Selection：选中理由 / 排除理由 / 禁 Join
6. Schema Pack：冻结绑定，不是生成新医学标准
7. 映射表：AUTO/REVIEW，无数据行
8. 图查询：为什么 REVIEW、为什么排除 METABRIC
9. Preview 计划：工具清单 + 红字 `execution_allowed=false`

### 2.5 必须突出的结果

1. 闲聊/概念问答不会开跑取数。
2. 没有澄清就不能 Planner。
3. 数据需求是建议，不是已检索。
4. 排除 METABRIC 是约束边，不是库里没数据。
5. 医学 pack 绑定冻结 Canonical Schema，`response_domain` 还在。
6. 患者/样本分界在，禁止跨研究 Join。
7. REVIEW 可解释，值未入库。
8. Preview 列出将调用的旧工具，但现在不调用。

### 2.6 本案例不要展示

- 旧工作台“发送并开始研究”后的主数据表、Excel 导出、SDTI 分数
- HER2 IHC 2+ 被自动判为 Positive
- 细胞系 AUC/IC50 当患者 pCR
- 患者跨队列合并图
- “已经整合完成 / 已验证覆盖”
- 伪造的光变或临床数字
- 未接线的前端假页面

---

## 3. 案例 2：Ia 型超新星光变曲线

### 3.1 用户输入

| 轮次 | 用户原话 | 预期 |
|---|---|---|
| 1 | `我想研究Ia型超新星光变曲线与红移的关系` | 领域 `astronomy`；对象能落到红移/天体观测 |
| 2 | `机制探索` | 仅用来通过现有澄清门，**不要解释成肿瘤疗效** |

现网 Copilot 对非肿瘤任务仍可能弹出“机制探索还是疗效预测”。演示词必须先说：这是通用澄清门的现状，不是把超新星套进乳腺癌字段。答 `机制探索` 只为让 Planner 放行。

Planner 对非 oncology **不会**冒充冻结医学合同，只返回方案草稿。这是优点，要讲出来。

### 3.2 AI 每一步展示什么

**Copilot**

- 领域：astronomy
- 数据需求：`domain_evidence`，`not_retrieved`
- 不出现 `patient_id` / `her2_status` / `pCR`

**Planner**

- `domain=astronomy`
- `used_existing_services=[]`
- notice：非肿瘤只出草稿，不是已冻结医学 Research Contract

**Registry + Discovery**

- nasa_mast / ads / open_supernova_catalog / zenodo：`catalog_only` 或 `planned`
- 无 `fetch_binding`
- `integrate_eligible=false`
- 候选不得升格为 verified，不得说字段已覆盖

**Schema Pack**

- 任务级 DRAFT pack
- 字段：`sn_id, observation_time, band, flux, redshift, source_id, raw_field, raw_value`
- 禁止混入 HER2 / patient 字段
- `row_count=0`

**Matcher Bridge**

- 示例：`MJD → observation_time`，`mag → flux`
- 仍无数据行

**Figure Understanding（本案例高潮）**

输入：

```json
{
  "source_id": "paper:sn-ia-demo",
  "figure_id": "Figure 3",
  "caption": "Ia型超新星论文 Figure 3 光变曲线"
}
```

输出必须念出来：

- `figure_type=light_curve`
- `x_axis=phase_day`，`y_axis=magnitude`
- `digitization_possible=true`
- `enters_primary_table=false`

台词：可以理解这是光变曲线，也可以说能人工数字化；**数字现在不进科研主表**。

**Evidence Graph**

- `FigureUnderstanding --EXTRACTED_FROM--> Paper`
- 节点只有类型/轴/可提取性，没有观测点

**Integration Preview**

- 天文来源 `fetch_binding=null`
- 即使允许执行也不能取数
- 仍然 `execution_allowed=false`

### 3.3 调用哪些模块

```text
POST /api/v30/sessions                 （新开会话，与 HER2 隔离）
POST /api/v30/copilot/turn             ×2
POST /api/v30/plan
GET  /api/v30/registry/sources?domain=astronomy
POST /api/v30/discover                 domain=astronomy
POST /api/v30/schema-packs/generate    domain=astronomy
POST /api/v30/schema-packs/match       MJD/band/mag/redshift
POST /api/v30/figures/understand
GET  /api/v30/graphs/{graph_id}
POST /api/v30/integration/preview
```

不要调用医学 Adapter，不要把超新星送进 `/api/agent/tasks`。

### 3.4 前端应该展示哪些页面

**现在能用的：**

- 继续留在 `/docs`，换一个 session
- 不要回到肿瘤示例按钮（新辅助治疗、EGFR、KRAS）去“假装通用”

**若以后接线，本案例只要四张卡：**

1. Registry：catalog_only / planned 徽章
2. Schema Pack：超新星字段 + 溯源三件套
3. Figure Understanding：理解卡，大字“未写入主表”
4. Preview：无 Adapter 可调，`execution_allowed=false`

### 3.5 必须突出的结果

1. 同一套入口能处理非医学问题。
2. 天文来源是目录/计划，不是已取数插件。
3. 任务 schema 是 DRAFT，不是新的冻结标准。
4. 图能理解，数字不能入库。
5. 两案例 Memory 隔离（必须新开 session）。

### 3.6 本案例不要展示

- 从像素估读的星等序列或 CSV
- 把 `digitization_possible=true` 说成已经数字化
- 用肿瘤 Canonical Schema 硬套光变
- 材料/天文 `active + fetch_binding`（系统禁止这样登记）
- 旧评测里的 SDTI、Gold Set、消融表（那是医学内核成绩，不是超新星成绩）

---

## 4. 前端页面对照（现状 vs 应展示）

| 现有页面 | 接了谁 | 本场 Demo |
|---|---|---|
| `#planning-workspace` 欢迎页 | 旧规划向导 | 只做开场定位 |
| `#planner-chat` / 右侧四页签 | 旧 `/api/v3` 规划 | 不作为 V3.1 主路径 |
| `#task-entry` 研究问题陈述 | 旧 Agent 任务 | **禁止演示点击** |
| `#quality-gates` 质量门 | 旧 Quality | 口头提“内核仍在”，不打开跑分 |
| 数据集表 / 导出 | 旧 Integrate | 不展示，避免像已经执行 V3.1 |
| `/docs` | 含全部 `/api/v30` | **主演示台** |

评委若问“界面在哪”：回答 V3.1 先做诚实 API 闭环，前端接线是下一步，不把旧医学工作台冒充新助手。

---

## 5. 当前系统是否已经形成完整闭环

结论先说：

**规划闭环：已形成。生产闭环：未接到 V3.1。产品闭环：前端未接。**

### 5.1 已经闭合的

| 闭环 | 证据 |
|---|---|
| 对话门 | CHAT / CONCEPT_QA 不进 Planner |
| 澄清门 | 未 ready → 422，不猜目标 |
| 记忆门 | 目标 / 澄清 / 约束按 session 隔离 |
| 发现诚实门 | unverified、catalog_only、coverage_claimed=false |
| 选择安全门 | 用户排除、planned 不入选、禁患者 Join |
| 契约门 | 医学绑冻结 pack；通用出 DRAFT pack |
| 映射门 | 只出 FieldMapping，不出行 |
| 解释门 | Graph 能回答为什么选、为什么映射、为什么 REVIEW |
| 图像门 | 理解卡 `enters_primary_table=false` |
| 执行门 | Preview 恒 `execution_allowed=false` |

从“用户一句话”到“系统知道下一步该调谁、不能干什么”，这条链是完整的。

### 5.2 尚未闭合的

| 缺口 | 现状 |
|---|---|
| ExecutionBridge | 没有 v30 真实 Integrate，不转调 `ResearchAgentService` |
| 取数 / CSV / CanonicalRecord | Preview 明确不做 |
| Quality Gate | 只在 Preview 里作为“若执行才会跑”的声明 |
| Extraction 门面 | Phase 5 计划中的 `/api/v30/extract` 未做 |
| 前端接线 | 无 `/api/v30` |
| Copilot 文案 | ready 之后仍可能说“尚未挂载 Planner” |
| 通用澄清问题 | 超新星仍可能被问疗效/机制 |

旧医学内核（Adapter → Schema → Evidence → Quality → 导出）**自己**仍是闭环，且回归 234 通过；但它是兼容后门，不是本轮 V3.1 演示闭环。

### 5.3 对评委的一句话

系统已经能连续理解、约束、发现、选源、定字段、解释原因，并拒绝在证据不足时执行。  
它还没有在 V3.1 入口里把这些计划变成主表。这是有意停在 Preview，不是演示事故。

---

## 6. 演示台词骨架（可直接念）

**开场：**  
这是通用科研数据智能体。医学是已经装好的插件，不是系统的全部世界。

**HER2 收束：**  
如果现在执行，会走 GEO/GDC 这些旧工具；但当前 `execution_allowed=false`。HER2 规则、response_domain、患者不跨研究合并，都还在计划里，没有被助手改掉。

**超新星收束：**  
同一套助手能看天文问题。来源只是目录，图是光变曲线，可以理解，数字不进表。这证明它不是套了壳的乳腺癌爬虫。

**结尾：**  
规划闭环已经闭合。真实取数仍交给旧内核，而且必须另开执行闸。我们这轮不把估读数和未验证覆盖讲成成绩。

---

## 7. 演示操作清单（避免现场翻车）

1. 用仓库 `.venv` 启动：`python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
2. 打开 `http://127.0.0.1:8000/docs`，不要先开首页表单
3. 案例 1、案例 2 **各建一个 session**
4. 预先收藏 HER2 的 `finding_id`（REVIEW）和 METABRIC 约束 finding，现场只 GET
5. 超新星 Figure 必须带 `source_id`，否则 422
6. 不要登录千问也能走完 V3.1 这一路（当前 v30 不依赖千问）
7. 旧工作台若被问到：说明那是医学插件后门，本场不跑，避免和 Preview 打架
8. 不要打开 Gold Set / SDTI 页报新分数

---

## 8. 明确不要展示的能力（总表）

| 能力 | 原因 |
|---|---|
| 真实 Integrate / Adapter 下载 | Phase 6-A 只做 Preview |
| CSV / CanonicalRecord / 主表行 | 会破坏“诚实未执行” |
| 图像数字化入库 | `digitization_possible` ≠ 已数字化 |
| `/api/v30/extract` | 未实现 |
| 前端 Copilot 工作台 | 未接线 |
| 患者跨研究关系图 | 系统禁止 |
| 把 catalog_only 说成已覆盖 | Discovery 诚实性约束 |
| 新的正式 SDTI | 冻结评测口径，禁止编造成绩 |
| 诊疗建议 | 产品边界 |

---

## 9. 结论

可以做一场 5–8 分钟、两个案例的比赛演示：HER2 证明医学插件仍守规则，超新星证明入口是通用的。  
主舞台是 `/api/v30`，不是旧数据表。

完整闭环只在“理解 → 约束 → 发现 → 契约 → 解释 → 拒绝执行”这一层成立。  
数据生产闭环仍在旧内核，尚未经 V3.1 执行桥接通。演示必须把这句说完，才算诚实。
