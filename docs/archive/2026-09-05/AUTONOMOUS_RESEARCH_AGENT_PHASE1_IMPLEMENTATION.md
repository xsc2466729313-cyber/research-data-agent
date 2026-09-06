# Autonomous Research Agent Phase 1 实施设计

- 日期：2026-09-05
- 状态：待确认，暂不写代码
- 目标：在不修改后端、不新增 API、不引入 `research_id` 的前提下，完成比赛可用的前端自主运行体验
- 基线：`AUTONOMOUS_RESEARCH_AGENT_PRODUCT_PLAN.md`

## 1. Phase 1 的目标与边界

### 1.1 本阶段要交付的体验

用户输入一句：

> 我想研究 Ia 型超新星光变曲线

页面直接进入 `Research Run Workspace`，不再进入当前 Copilot 的连续确认页。中间区域自动呈现：

```text
原始问题
→ AI理解
→ Agent计划
→ 正在理解
→ 正在规划
→ 正在发现来源
→ 正在构建字段
→ 正在建立证据链
→ 阶段结果
→ 继续追问 / 修改方向
```

用户可以观察、追问和修改，但普通阶段不要求用户点击“继续”。

### 1.2 明确不做

- 不修改 `backend/`。
- 不新增后端 API。
- 不实现 `research_id`、后端 Research Project、跨刷新持久化历史。
- 不把当前 Copilot 页面继续修补成更多确认卡。
- 不伪造真实 CSV、数据行、Coverage、Evidence 或执行结果。
- 不把 `session_id` 之外的前端临时编号宣传为持久化任务身份。
- 不在本阶段实现完整的多 Run 历史比较。

本阶段的“自主”是前端对已有后端能力的自动编排和连续呈现，不是新增一套后端 Agent orchestration 服务。

## 2. 现有能力与 Phase 1 的可用接口

只使用当前已存在的接口：

| 能力 | 现有接口 | Phase 1 用法 |
|---|---|---|
| 创建研究上下文 | `POST /api/v30/sessions` | 创建当前研究 Slot |
| 理解研究问题 | `POST /api/v30/copilot/turn` | 获取 `understood_goal`、route、需求建议 |
| 读取 Memory | `GET /api/v30/sessions/{id}/memory` | 切换/恢复当前 Slot |
| 规划补充 | `POST /api/v2/research/plan` | 作为非阻塞的结构化规划来源 |
| v30 方案 | `POST /api/v30/plan` | 仅当后端 Memory 已满足现有 readiness 时调用 |
| 来源能力 | `GET /api/v30/registry/sources` | 展示可用来源能力 |
| 来源发现 | `POST /api/v30/discover` | 生成候选来源，明确 `fetched=false` 时仍是候选 |
| 来源选择 | `POST /api/v30/source-selection` | 自动展示选择/排除理由和 join risk |
| 字段体系 | `POST /api/v30/schema-packs/generate`、`GET .../{id}` | 生成或绑定 Schema Pack |
| 字段映射 | `POST /api/v30/schema-packs/match` | 展示 AUTO / REVIEW 映射，不能当数据行 |
| 证据图 | `POST /api/v30/graphs/project`、`GET .../{id}` | 生成解释图 |
| Why | `GET /api/v30/graphs/{id}/why/{finding_id}` | 回答为什么选来源/为什么 REVIEW |
| 图理解 | `POST /api/v30/figures/understand` | 保留“图理解不入库”边界 |
| 执行预览 | 已有 v30 integration preview/prepare 接口 | 本阶段只在真实前置条件满足时展示，不默认执行 |

不把 `POST /api/v30/plan` 当作唯一的“自主入口”。它当前后端仍有严格 readiness gate：

- `goal.object` 和 `goal.target` 必须存在；
- 所有 clarification 必须有 answer；
- 当前 v30 Copilot 的 focus question 仍包含肿瘤语义。

因此前端必须区分：

1. Agent 已经完成的自动阶段；
2. 由现有后端 readiness gate 阻断的阶段；
3. 尚未接入真实取数/执行的阶段。

不能通过前端假写确认答案来绕过后端安全门。

## 3. Research Run 页面设计

### 3.1 页面路由

新增产品语义路由：

```text
#/r/{session_id}/run
```

兼容处理：

- `#/r/{session_id}/copilot` 重定向到 `/run`；
- `#/r/{session_id}/timeline` 继续保留，作为工程进展/审计面；
- `/sources`、`/mapping`、`/graph` 继续保留为可展开的详情工作面。

左侧不再把这些路由显示成八步主导航。

### 3.2 页面三栏

```text
┌ Research List ─────┬ Research Run Workspace ─────────────┬ Research Brief ───┐
│ 研究 A              │ 原始问题                            │ 研究对象           │
│ 研究 B              │ AI理解                              │ 研究目标           │
│ + 新建研究          │ Agent计划                            │ 当前状态           │
│                     │ 自动运行阶段                         │ 数据域             │
│                     │ 阶段结果                             │ 未解决风险         │
│                     │ 追问 / 修改方向                       │ 技术详情 ▸         │
└─────────────────────┴─────────────────────────────────────┴───────────────────┘
```

### 3.3 中间区域顺序

固定顺序，不因 API 返回顺序改变：

1. `Research Question`：原始用户输入，永远保留原文。
2. `AI Understanding`：对象、目标、领域、范围和不确定点。
3. `Agent Plan`：研究路径和将使用的能力；计划不是结果。
4. `Run Progress`：当前运行阶段和已完成阶段。
5. `Stage Results`：来源、字段、证据图和 lineage 的真实回包摘要。
6. `Follow-up Composer`：追问“为什么选择这个来源？”或修改研究方向。

每个阶段卡都支持展开，但默认只显示一句研究语言的人话结论和真实状态。

## 4. 自动推进状态机

### 4.1 前端运行状态

前端为当前 Slot 增加运行态投影，不引入新的后端实体：

| 状态 | 用户文案 | 进入条件 | 结束条件 |
|---|---|---|---|
| `intake` | 正在理解研究问题 | 用户提交原句 | copilot turn 返回 |
| `understood` | 已形成初步理解 | 有 goal/route 或明确概念结果 | 创建计划摘要 |
| `planning` | 正在规划研究路径 | 进入规划调用 | v2/v30 规划回包或真实阻断 |
| `discovering` | 正在发现来源 | 有 domain/topic | registry/discover/select 完成 |
| `structuring` | 正在构建字段体系 | 有 topic/domain/字段候选 | pack/match 完成 |
| `linking` | 正在建立证据链 | 有来源、pack 或 mapping | graph/why 回包完成 |
| `results` | 阶段结果已生成 | 任一真实阶段有结果 | 用户追问或运行结束 |
| `needs_review` | 有一项需要人工判断 | 后端返回高风险/阻断 | 用户输入修改或确认 |
| `completed_preview` | 研究预览已完成 | 阶段回包齐全但未真实取数 | 进入结果资产详情 |

状态机只表达前端编排和已收到的结果，不表示后端真的执行了未调用的能力。

### 4.2 自动推进规则

1. 首句提交后立即启动 `intake`，不显示方向选择卡作为主任务。
2. `copilotTurn` 完成后，立即生成 AI Understanding 和工作假设。
3. 规划优先调用现有结构化规划接口；v30 plan 只在其 readiness 满足时调用。
4. 有足够的 `domain/topic` 时自动进入 Registry、Discovery 和 Selection。
5. 有字段假设时自动进入 Schema Pack 和 Mapping。
6. 有来源、选择和映射对象时自动进入 Graph。
7. 每一步完成后立即在同一页面追加阶段结果，不跳转到另一个必须操作的页面。
8. 某一步返回真实阻断时，停止该分支并显示原因；不继续伪造下游结果。

### 4.3 比赛演示的 Ia 型超新星路径

演示必须可见地完成以下链路：

```text
输入 Ia 型超新星光变曲线
  → AI 理解：天文对象 / 光变曲线
  → 工作计划：观测时间、波段、flux、redshift、来源和字段
  → 自动发现候选来源
  → 自动生成天文任务字段 Pack
  → 自动展示字段映射状态
  → 自动投影 Evidence Graph
  → 展示 Source Lineage
  → 明确标记：候选/预览，不等于已生成真实数据集
```

如果现有 v30 Planner readiness 阻止正式 Plan，页面仍应展示：

- `Agent Plan` 的结构化计划摘要；
- `needs_review` 或 `planner_gate` 的真实说明；
- 已完成的 Discovery / Mapping / Graph 结果；
- 不显示“研究失败”，也不把计划写成用户确认。

## 5. AI Understanding 设计

AI Understanding 不是当前 Copilot 的“下一步问题”。它是 Agent 对初始问题的工作解释：

```text
研究对象：Ia 型超新星
当前目标：分析光变曲线及其可观测变量
可能领域：astronomy
工作假设：优先关注时间、波段、flux、redshift 和来源可追溯性
不确定点：尚未指定具体巡天、波段或样本范围
```

规则：

- 明确区分用户原话、Agent 推断和未确认假设；
- `target` 缺失时显示“工作假设”，不显示“用户已确认”；
- 不使用 oncology 的“机制探索/疗效预测”问题解释天文研究；
- 高风险医学语义仍进入 `needs_review`，不能静默推断。

## 6. Agent Plan 设计

Agent Plan 用简短的研究路径说明取代“请确认下一步”：

```text
本轮计划

1. 识别光变曲线所需的观测字段
2. 查找公开、可追溯的天文来源
3. 建立时间 / 波段 / flux / redshift 的字段体系
4. 对齐来源字段并标记 REVIEW 项
5. 建立来源到字段的证据解释链
```

计划卡提供两个非阻塞入口：

- `查看计划细节`：展开来源和字段假设；
- `修改研究方向`：进入追问输入，不要求用户逐项确认。

计划卡必须标注：

- 计划不是已检索数据；
- 候选来源不是覆盖证明；
- 字段映射不是数据行；
- Graph 是解释投影，不是事实库。

## 7. 自动推进视觉

### 7.1 阶段条

中间顶部或阶段卡组显示五个面向用户的阶段：

```text
理解  →  规划  →  发现来源  →  构建字段  →  建立证据链
```

每个阶段只有三种视觉状态：

- `pending`：尚未开始；
- `active`：正在进行；
- `done`：已经收到对应真实回包。

如果后端返回阻断，额外显示 `review`，不使用“完成”。

### 7.2 阶段卡内容

| 阶段 | 运行中 | 完成后 | 诚实边界 |
|---|---|---|---|
| 理解 | 正在解析研究对象 | 对象/目标/领域摘要 | 推断不等于确认 |
| 规划 | 正在编排路径 | 计划步骤和工作假设 | 计划不等于结果 |
| 发现来源 | 正在查找候选 | 候选数、来源类型、状态 | `unverified` / `fetched=false` |
| 构建字段 | 正在生成 Pack/Mapping | 字段数、AUTO/REVIEW | `row_count=0` 仍无数据行 |
| 建立证据链 | 正在投影 Graph | 节点、边、Why 入口 | 不含患者边，不替代 Evidence |

### 7.3 动效边界

- 只使用轻量的 active indicator 和阶段切换；
- 不使用无限打字机、不伪造逐字输出；
- 网络请求期间显示明确的“正在进行”，失败后保留失败阶段和重试入口；
- 页面刷新或切换研究后，不显示无法由当前 Slot 证明的“已完成”。

## 8. 用户追问入口

### 8.1 “为什么选择这个来源？”

追问不是重新开始 Copilot，而是对当前 Run 的结果发起解释动作：

1. 从来源卡或 Source Lineage 点击“为什么”；
2. 展开当前来源的选择理由、source_id、verification_status、字段假设和 join risk；
3. 如果有 Graph finding，调用现有 Why 接口；
4. 在中间追加一条“解释结果”阶段条目；
5. 不修改 Memory，不改变当前研究目标。

### 8.2 “修改研究方向”

Phase 1 不实现持久化 `research_id` 或多 Run 历史，因此采用当前研究 Slot 内的轻量重跑策略：

- 保留原始问题和当前结果摘要；
- 输入新的研究方向；
- 以新输入启动当前 Slot 的一次前端运行；
- 清理只属于当前运行的临时产物，重新执行受影响链路；
- 不覆盖后端 Memory 中无法安全撤销的历史事实；
- 明确标注“本次运行基于新的方向输入”。

若未来需要比较旧 Run 与新 Run，必须等 Research Project/Run 持久化能力进入后续阶段。

### 8.3 追问 Composer

底部输入框只提供两类动作：

- 对当前结果追问：为什么、依据是什么、来源是什么；
- 修改研究范围：增加目标、排除来源、改变字段重点。

不再显示“继续说明”“确认方向”“生成方案”作为默认按钮。

## 9. Evidence、Graph、Source Lineage 保留方式

### 9.1 Evidence

Evidence 作为每个阶段结果的可展开证据面：

- 来源真实入口；
- `source_id`；
- `raw_field` / `raw_value`；
- confidence；
- verified / review / unverified 状态；
- 不能解释时保留 unresolved。

### 9.2 Graph

Graph 作为“为什么”的解释视图，不作为运行完成动画：

- 自动在证据链阶段投影；
- 用户可以点击节点打开 Why Drawer；
- 过滤禁止的 `SAME_PATIENT` / `JOINED_ACROSS_STUDY` 边；
- 明确 `contains_patient_edges=false`、`copies_fact_values=false` 等事实状态；
- 图理解结果仍显示“未写入主表”。

### 9.3 Source Lineage

Phase 1 新增的是现有回包的组合视图，不新增后端对象：

```text
Registry Source
  → Discovery Candidate
  → Selection Decision
  → Schema Requirement
  → Field Mapping
  → Evidence / Graph Finding
```

Lineage 卡展示来源、字段、选择理由和状态；如果只有候选而没有真实抓取，明确显示“候选来源，尚未取数”。

## 10. 前端文件职责调整

本阶段实际实施时建议按职责改造，不继续把自主逻辑塞进 `copilot.js`：

| 文件/模块 | Phase 1 职责 |
|---|---|
| `app/pages/research-run.js` | Research Run 页面入口和渲染 |
| `app/research-run-orchestrator.js` | 串联现有 API，推进阶段，处理真实阻断 |
| `app/research-run-store.js` 或统一 `workspace-store.js` | 当前 Slot 的运行态与阶段结果 |
| `app/components/run-progress.js` | 五阶段自动推进视觉 |
| `app/components/run-stage-card.js` | 阶段卡和真实状态 |
| `app/components/research-question.js` | 原始问题和 AI Understanding |
| `app/components/agent-plan.js` | 计划与工作假设 |
| `app/components/follow-up-composer.js` | 为什么/修改方向入口 |
| `app/components/source-lineage.js` | Source lineage 组合视图 |
| 现有 `graph-canvas.js` / `why-drawer.js` | 保留并嵌入证据阶段 |
| 现有 `source-card.js` / `mapping-table.js` | 保留并嵌入阶段结果 |
| `app/pages/copilot.js` | 降为兼容入口，不再承担默认主页面 |
| `app/pages/timeline.js` | 降为工程审计/调试详情 |

API 包装器可以增加对“已有接口”的前端调用封装，但不能新增后端路径或修改 response 契约。

## 11. 运行与状态隔离要求

1. 每个阶段请求都捕获当前 `session_id`。
2. 回包提交前校验当前 Slot 仍是该 `session_id`。
3. 研究切换时取消或丢弃旧运行的后续 UI 提交。
4. 阶段结果、Graph、Source lineage、Why Drawer 全部跟当前 Slot 走。
5. 不使用全局 `runPhase`、全局 `lastWhy`、全局 `pendingIntent` 跨研究共享。
6. 自动编排失败只标记当前阶段，不清空已经获得的真实结果。
7. 追问“为什么”不触发来源重选或重新规划。

## 12. 比赛验收标准

### 必须通过

1. 输入一句 Ia 型超新星研究问题后，直接进入 Research Run，不出现连续确认卡。
2. 页面可见“正在理解、正在规划、正在发现来源、正在构建字段、正在建立证据链”五个阶段。
3. 阶段会依据真实接口回包变为 done；没有回包的阶段不能显示 done。
4. 页面同时展示原始问题、AI 理解、Agent 计划和阶段结果。
5. 用户可以点击来源进入 Source Lineage，并追问为什么选择该来源。
6. 用户可以输入“修改研究方向”，启动当前 Slot 的新一轮前端运行。
7. Evidence Graph 和 Why Drawer 可从阶段结果进入。
8. HER2 研究和 Ia 型超新星研究在同一标签页切换时不互相污染。
9. 不出现八步流程作为左侧主导航。
10. 不伪造已取数、已整合、已生成数据行或正式医学结论。

### 明确允许的限制

- v30 Planner readiness 仍可能使正式 Plan 阶段进入 `needs_review`；页面必须透明展示而不是假装自动完成。
- 没有后端持久化时，刷新后只恢复当前 session 能读取的 Memory 和前端可重建结果。
- 没有真实 Integration 结果时，CSV 区只能显示“尚无可下载数据资产”或预览状态。

## 13. 实施前最终确认点

开始写代码前，需要确认以下选择：

1. 默认路由是否从 `#/r/{session_id}/copilot` 切换为 `#/r/{session_id}/run`？
2. 是否接受用现有 `/api/v2/research/plan` 作为非阻塞结构化规划来源，同时保留 v30 readiness gate 的真实限制？
3. 是否接受 Phase 1 的“自主”只自动推进真实可调用阶段，不通过前端伪造确认绕过后端 Planner？
4. “修改研究方向”是否接受当前 Slot 内轻量重跑，而不是实现持久化 Run 历史？
5. 是否接受 CSV 在没有真实执行结果时只展示诚实空态，不生成演示假数据？

确认后，下一步才进入代码实施和回归测试设计。
