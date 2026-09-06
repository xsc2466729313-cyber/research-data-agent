# V3.1 前端实施计划

- 日期：2026-09-05
- 依据：`docs/v31_baseline/FRONTEND_V31_DESIGN.md`
- 性质：实施计划，不是代码，不是授权改旧前端
- 原则：新增 `frontend/v31/`；旧 `frontend/` 降为内核实验室并原样保留

本文回答：如何把设计落成可验收的阶段，而不重写现有工作台。

---

# 0. 当前技术栈判断（先于任何阶段）

## 0.1 现状盘点

| 项 | 事实 |
|---|---|
| 技术 | 原生 HTML + 单文件 `frontend/app.js`（约四千行）+ `frontend/styles.css` |
| 构建 | **无** `package.json`、无 Vite / webpack、无 React / Vue |
| 托管 | FastAPI `StaticFiles(directory=frontend, html=True)` 挂在 `/` |
| Docker 后端镜像 | `COPY frontend /workspace/frontend`，整目录随 uvicorn 提供 |
| Docker 前端镜像 | `frontend/Dockerfile` **只复制** `index.html` / `styles.css` / `app.js` 三件套 |
| Nginx | `try_files` 回退到旧 `index.html`；`/` 即旧工作台 |
| 测试 | `backend/tests/test_api.py` 对 `GET /`、`frontend/app.js`、`styles.css`、`nginx.conf` 做大量字符串断言 |
| 旧 API | `app.js` 已接 `/api/research/*`、`/api/v3/*`、`/api/agent/tasks`，**没有** `/api/v30` |

结论：**当前就是原生静态前端。** V3.1 应渐进接入，不换框架。

## 0.2 为什么本计划不引入框架

| 方案 | 理由 | 风险 |
|---|---|---|
| **原生 ES Module（采用）** | 与现有托管一致；无构建；`/v31/` 可被 StaticFiles 直接端出；旧测试不受影响 | 需手写 router / store，但页面少、API 面固定 |
| React / Vue + 打包 | 组件生态 | 新增工具链、改 Dockerfile、双份产物、评审环境更脆；收益不匹配 8 个页面 |
| 把逻辑写进旧 `app.js` | 看似快 | **明确禁止**；会触发旧测试与旧工作流污染 |

引入框架的唯一可接受时机：后续若 Graph 画布复杂度爆炸，且原生 Canvas 已先交付只读版。那是另开任务，不是本计划前置。

## 0.3 与 FastAPI 静态服务如何共存

```text
浏览器
  GET /                    → frontend/index.html          旧内核实验室（禁止改）
  GET /app.js              → frontend/app.js              旧逻辑（禁止改）
  GET /v31/                → frontend/v31/index.html      新工作台
  GET /v31/app/main.js     → frontend/v31/app/main.js
  GET /api/v30/*           → FastAPI 已有路由
  GET /api/agent/tasks/*   → FastAPI 已有路由（仅 Dataset 只读）
```

关键机制：

1. `main.py` 已 `app.mount("/", StaticFiles(..., html=True))`。子目录 `frontend/v31/` 会被自动映射到 `/v31/`，**Phase 0–5 默认不改 `main.py`**。
2. `/` 必须继续返回旧页面。`test_api.py` 的 `client.get("/")` 断言旧文案（「发送并开始研究」等）。**禁止把 `/` 重定向到 `/v31/`。**
3. 产品路由用 **hash**：`/v31/#/home`、`/v31/#/r/{session}/copilot`。这样刷新、书签不依赖 History API 回退，也不要求改 Nginx `try_files`。
4. 旧页脚链到 `/#task-entry`；新壳页脚链到 `/` 或 `/#task-entry`，文案写「内核实验室」。两套入口不共享 JS 状态。

## 0.4 允许改 vs 禁止改

**禁止（全程）：**

- 重写或增补 `frontend/app.js` 的 `/api/v30` 调用
- 删除或改写 `frontend/index.html` 旧工作台结构与文案
- 修改旧 `/api/v3`、`/api/research/*`、`/api/agent/tasks` 工作流语义
- 让旧页面调用 `/api/v30`
- 改 `canonical_schema.yaml` / `medical_rules.yaml` / 旧 Adapter / Quality Gate
- 为了新工作台去改 `backend/tests/test_api.py` 里对旧前端的断言

**允许：**

- **只新增** `frontend/v31/**`
- **只新增** `backend/tests/v31_frontend/**`（或同等新文件）
- Docker 前端镜像：在 `frontend/Dockerfile` **追加** `COPY frontend/v31 ...`；在 `nginx.conf` **追加** `location /v31/`。不得改 `location /` 的旧回退，不得改 `GET /` 行为
- 若必须动 `nginx.conf`，旧断言行（`/health`、timeout、Cache-Control）必须保持

Phase 0 若只做本地 uvicorn，可以暂缓 Docker/Nginx 增补，但必须在 Phase 0 报告里写明「Docker 前端镜像尚未带上 v31」。

---

# 1. 总施工纪律

1. 一阶段只开一类表面，做完验收再进入下一阶段。
2. 状态只存 API 回包。前端不得根据关键词（HER2 / 超新星）猜门状态。
3. 诚实文案集中在 `frontend/v31/app/copy/`，页面不得手写「已覆盖 / 已整合 / 已入库」。
4. 绿只表示 Quality `PASS`。发现、映射、理解一律不用绿勾。
5. 主按钮永不叫「发送并开始研究」。
6. 不是聊天窗口：Copilot 主视觉是理解条、需求表、一张澄清卡。
7. 每个 Phase 结束后跑：新前端隔离测试 + `backend/tests/v30` + Phase 0 回归 234。
8. 两会话隔离：换研究 = 新 `session_id` + 空 store，禁止 HER2 与天文对象混放。

---

# 2. 跨阶段状态与路由（所有 Phase 共用）

## 2.1 Hash 路由表

| Hash | 页面 | 最早出现 |
|---|---|---|
| `#/home` 或空 | 首页 | Phase 1 |
| `#/r/{session}/copilot` | Copilot | Phase 1 |
| `#/r/{session}/timeline` | Timeline 全页 | Phase 2 |
| `#/r/{session}/sources` | Sources | Phase 3 |
| `#/r/{session}/mapping` | Mapping | Phase 3 |
| `#/r/{session}/graph` | Graph | Phase 4 |
| `#/r/{session}/preview` | Preview | Phase 5 |
| `#/r/{session}/dataset` | Dataset | Phase 5 |

未实现的 hash：壳能解析，中列显示「本阶段尚未开放」，不得假造数据。

## 2.2 SessionStore（唯一可变真相）

只允许这些键，值必须是后端模型或 `null`：

```text
sessionId
memory                  MemorySnapshot
lastRoute               RouteDecision
lastTurn                CopilotTurnResponse
plan                    PlanResponse          （Phase 2 起）
registry                RegistrySourceList    （Phase 3）
discovery               DiscoverResponse      （Phase 3）
selection               SelectedSourcePlan    （Phase 3）
schemaPack              SchemaPack            （Phase 3）
mappings                FieldMappingResult    （Phase 3）
graph                   EvidenceGraph         （Phase 4）
lastWhy                 GraphWhyResponse      （Phase 4）
integrationPlan         IntegrationPlan       （Phase 5）
executionPreview        ExecutionRequestPreview（Phase 5）
executionResult         ExecutionResult       （Phase 5）
agentTask               AgentTaskResult       （Phase 5，旧只读）
lastError               { source, status, error }
```

规则：

- 切换 `sessionId` 时整表清空。
- 不得派生 `coveragePercent`、`isVerified`、`canExecuteGuess`。
- `lastError.error` 使用后端字面量：`research_goal_not_ready`、`only_oncology_integrate_supported` 等。

## 2.3 TimelineStore（只读投影，Phase 2 落地）

不是第二套真相。每次 SessionStore 更新后，按 **字段是否存在** 投影 8 个门。禁止 `if (topic.includes("HER2")) ready`。

---

# Frontend Phase 0 · 前端基础壳

## 1. 页面目标

建立可打开的空壳：能访问 `/v31/`，能切 hash，能 `GET /health`，能看到工作台骨架（顶栏 / 左轨占位 / 中列 / 右轨占位）。不实现业务页，不调用 `/api/v30` 写会话。

本阶段证明：**新目录能和旧 StaticFiles 共存，且旧 `/` 行为不变。**

## 2. 页面组件

| 组件 | 职责 | 视觉 |
|---|---|---|
| App Shell | 顶栏品牌「科研数据工作台」+「内核实验室」次级链接 | 留白、细线、无渐变 |
| Stage Slot | 中列挂载点 | 最大阅读宽，不堆卡片 |
| Rail Slot | 左轨 / 右轨占位 | 左 240 / 右 320，窄屏变抽屉 |
| Gate Node（空心） | 8 个门的视觉占位，全 `idle` | 浅灰点，无假进度 |
| Status Dot | 来自 `/health` | 只表示进程在线 |
| Token Preview（开发用，可不展示） | 验证颜色 / 字体 / 间距 | 不进产品页 |

本阶段不出现对话框、机器人形象、欢迎轮播。

## 3. API 依赖

| API | 用途 |
|---|---|
| `GET /health` | 顶栏连接状态 |

禁止：`/api/v30/*`、`/api/agent/tasks`、`/api/adapters/*`、`/api/v3/*`。

## 4. 数据状态管理

```text
boot
  → health.js GET /health
  → router 读 location.hash
  → 未识别 hash 落到 #/home 占位
```

无 SessionStore 写入。无 localStorage 研究数据（Phase 0 甚至不要持久化 session，以免空壳制造脏会话）。

## 5. 文件目录（本阶段必须落地）

```text
frontend/v31/
  index.html
  styles/tokens.css
  styles/base.css
  styles/shell.css
  styles/components/badges.css
  styles/components/gates.css
  app/main.js
  app/router.js
  app/session-store.js          空实现：get / set / reset
  app/api/health.js
  app/api/v30.js                空模块：只导出函数名，Phase 1 再填
  app/copy/honesty.zh.js        先放入固定否定句
  app/copy/medical-constraints.zh.js
```

`index.html` 用相对路径加载 `./app/main.js`（`type="module"`）。不要引用 `/app.js` 或 `/styles.css`。

**可选（Docker 前端镜像）：**

- `frontend/Dockerfile` 追加复制 `v31/`
- `frontend/nginx.conf` 追加 `location /v31/` → 该目录 `index.html`

不改 `location /`。

## 6. 测试方案

新增 `backend/tests/v31_frontend/test_phase0_shell.py`（文件名可调整，但必须是**新文件**）：

1. `GET /` 仍 200，且仍含旧工作台标志（`planning-workspace` 或「发送并开始研究」）。
2. `GET /v31/` 或 `GET /v31/index.html` 200，含「科研数据工作台」或设计中的品牌，**不含**「发送并开始研究」作为主按钮。
3. `frontend/app.js` 全文不出现 `/api/v30`。
4. `frontend/v31/**/*.js` 不出现 `backend.app.sources`、`/api/adapters/`。
5. `frontend/v31/index.html` 不引用 `/app.js`。
6. `tokens.css` 含设计 token：`--paper` `#F4F3EF`、`--ink`、`--review`、`--pass`。
7. 若改了 nginx：旧断言（health / timeout / Cache-Control）仍在；并存在 `/v31/`。

继续跑：`backend/tests/test_api.py` 中前端相关用例、`backend/tests/v30`、Phase 0 的 234。

## 7. 验收标准

- 本地 `uvicorn` 打开 `/v31/` 能看见壳，打开 `/` 仍是旧工作台。
- 旧「发送并开始研究」仍只存在于旧页。
- 无构建步骤。
- 无框架依赖。
- 壳动画仅 180ms 内淡入或不动画；遵守后续 `prefers-reduced-motion`。

---

# Frontend Phase 1 · Home + Research Copilot

## 1. 页面目标

把一句话收成会话，并在 Copilot 页展示**理解、数据需求、一个澄清问题、Memory**。  
本阶段**不**调用 Planner，**不**发现来源，**不**取数。

首页是门厅，不是聊天框。Copilot 是研究秘书，不是回答引擎。

## 2. 页面组件

**首页**

| 组件 | 行为 |
|---|---|
| Intent Field | 大输入：「告诉我你想研究什么」 |
| Case Tile ×2 | HER2 耐药；Ia 超新星。只预填文本并建**新** session |
| Honesty Line | 「发现不是覆盖；预览不是执行」 |
| Primary CTA | 「开始澄清研究目标」或「进入工作台」，禁止「开始研究 / 发送并开始研究」 |

**Copilot**

| 组件 | 绑定字段 |
|---|---|
| Understanding Bar | `understood_goal.object / target / domain` |
| Data Need Table | `suggested_data_needs[]`，`retrieval_status` 原样展示（多为 `not_retrieved`） |
| Clarifying Card | 同时最多 1 条 `clarifying_questions`；选项按钮优先 |
| Memory Rail | `memory.goal` / `clarifications` / `constraints` |
| Route Pill | `route.route`：CHAT / CONCEPT_QA / CLARIFY / PLAN |
| Reply Block | `user_visible_reply` 短文本，禁止打字机 |
| Block Banner | `blocked_reason` |
| Composer | 底部固定组成器，不是悬浮聊天气泡 |
| Plan CTA | **可见但禁用**，旁注「方案生成在下一阶段」；不得调用 `/plan` |

CONCEPT_QA / CHAT：只出解释，不点亮后续门（后续门此时也不存在业务数据）。

## 3. API 依赖

| 动作 | API | 写入 Store |
|---|---|---|
| 首页提交 / 点案例 | `POST /api/v30/sessions` | `sessionId` `memory` |
| 进入 Copilot 后首轮 | `POST /api/v30/copilot/turn` | `lastTurn` `memory` `lastRoute` |
| 可选预判（首页微文案） | `POST /api/v30/route` | `lastRoute`；**不得**因此写 goal |
| 刷新右轨 | `GET /api/v30/sessions/{id}/memory` | `memory` |

**本阶段禁止：** `/plan`、`/discover`、`/integration/*`、`/api/agent/tasks`。

## 4. 数据状态管理

```text
Home.submit(text)
  → POST /sessions
  → router.go(#/r/{id}/copilot)
  → POST /copilot/turn { session_id, message: text }

Clarify.click(option)
  → POST /copilot/turn { session_id, message: option }

Constraint.typed("排除 METABRIC")
  → POST /copilot/turn（由后端写入 memory.constraints）

session 切换
  → SessionStore.reset() 再写入新回包
```

路由：`ready_for_planner` 只作为 Memory / Understanding 旁的只读徽章，不在本阶段触发跳转。

错误：404 session → 回首页并显示 `session not found`。

## 5. 文件目录

```text
frontend/v31/
  styles/pages/home.css
  styles/pages/copilot.css
  styles/components/cards.css
  styles/components/tables.css
  app/api/v30.js                 实现 sessions / route / turn / memory
  app/pages/home.js
  app/pages/copilot.js
  app/components/understanding-bar.js
  app/components/data-need-table.js
  app/components/clarify-card.js
```

## 6. 测试方案

新增 `test_phase1_copilot.py`（静态 + TestClient）：

1. 隔离：`frontend/app.js` 仍无 `/api/v30`。
2. `v30.js` 含上述 4 个路径，不含 `/plan`、`/discover`、`/execute`、`/adapters`。
3. Copilot 模板或渲染函数出现 Understanding / Data Need / Clarifying / Memory，不出现「发送并开始研究」。
4. 诚实文案：`not_retrieved` 有对应展示，无「已检索」。
5. **API 契约（可复用现有 v30 测试，不必重写后端）：** HER2 首句 → 有澄清；CONCEPT_QA「什么是HER2」→ Memory 无研究目标。前端测试用 TestClient 打同一路径，断言前端封装函数的 URL 与方法。
6. 视觉契约：`home.css` / `copilot.css` 不引入聊天泡泡选择器（禁止 `.chat-bubble`、机器人 avatar）。
7. 回归：`GET /` 旧页不变；`backend/tests/v30`；234。

手工验收脚本（写入 Phase 报告，不自动化也须列出）：

- 首页回车 → URL 变为 `#/r/{id}/copilot`，网络面板只有 sessions + turn，无 adapter。
- 超新星案例必须**新** session。

## 7. 验收标准

- 首页提交不触发 Adapter、不建旧 `/api/agent/tasks`。
- Copilot 主区域是理解条 + 表 + 一张问题，不是消息瀑布。
- 数据需求状态来自 API，前端不改写成“已完成”。
- 未澄清时没有可点的「生成研究方案」（本阶段整个禁用）。
- 旧工作台逻辑与文案零 diff。

---

# Frontend Phase 2 · Timeline

## 1. 页面目标

做出科研脊骨：8 个门只反映 SessionStore 里**已有回包**，用户不能点「标记完成」。  
本阶段补上 `POST /api/v30/plan`，让「方案」门有真实来源。

左轨常驻 + `#/r/{session}/timeline` 全页事件列表。

## 2. 页面组件

| 组件 | 规则 |
|---|---|
| Gate Node ×8 | 仅 `idle / blocked / ready / executed`；`executed` 本阶段不会出现 |
| Event Card | 时间、API 名、对象 ID、一句话（来自 `notice` 或固定诚实句） |
| Constraint Event | `memory.constraints` 单独样式：用户约束，不是数据缺失 |
| Jump Control | 已 `ready` 的门可跳到已存在页面；Sources 及之后仍显示「尚未开放」 |
| Plan CTA（Copilot 解锁） | `lastTurn.ready_for_planner===true` 才可点 |

八门名称固定：

会话 → 澄清 → 方案 → 来源 → 字段 → 证据 → 预览 → 数据

## 3. API 依赖

| 动作 | API | 用于哪一扇门 |
|---|---|---|
| 已有 | sessions / memory / turn | 会话、澄清 |
| **本阶段新增** | `POST /api/v30/plan` | 方案 |
| 未实现页 | 无 | 来源及之后保持 `idle` |

422 `research_goal_not_ready` → 方案门 `blocked`，`lastError.error` 原样保存。不得改写为「请再试一次」。

## 4. 数据状态管理

**投影表（必须按此实现，禁止额外启发式）：**

| 门 | idle | ready | blocked |
|---|---|---|---|
| 会话 | 无 `sessionId` | 有 `sessionId` 且最近 memory GET/创建成功 | memory 404 |
| 澄清 | 无 `lastTurn` 且 goal 空 | `memory.goal` 有 object/target，或 `ready_for_planner` | `blocked_reason` 非空且未 ready |
| 方案 | 无 `plan` | 存在 `PlanResponse` | `lastError.error==research_goal_not_ready` |
| 来源 | 无 `selection` 且无 `discovery` | Phase 3 才可能 ready | — |
| 字段 | 无 `mappings` 且无 `schemaPack` | Phase 3 | — |
| 证据 | 无 `graph` | Phase 4 | `contains_patient_edges===true` 视为 blocked（防御） |
| 预览 | 无 `integrationPlan` | Phase 5 | — |
| 数据 | 无 `executionResult` | 永不在本阶段 ready | — |

`executed` 仅当 `executionResult.executed===true`（Phase 5）。

TimelineStore 伪过程：

```text
onStoreChange(store):
  gates = project(store)      # 只读字段存在性
  events = append-only
    若新对象 ID 与上次不同，追加 Event，旧事件折叠为历史
```

禁止根据 `domain==oncology` 把「数据」门提前点亮。

Plan 成功后：停留 Copilot 或跳 Timeline，**不**自动 Discover。

## 5. 文件目录

```text
frontend/v31/
  styles/pages/timeline.css
  app/timeline-store.js
  app/pages/timeline.js
  app/components/gate-node.js
  app/api/v30.js                 增加 plan()
```

Copilot 的 Plan CTA 改为调用 `plan()`，仍不进入 Sources。

## 6. 测试方案

新增 `test_phase2_timeline.py`：

1. 投影单测（纯 JS 不便跑时，用 Python 复刻同一张投影表，或把投影规则写成 JSON fixture 两端对照）：无 `plan` ⇒ 方案门 idle；422 ⇒ blocked + 错误码。
2. `v30.js` 此时允许 `/plan`，仍禁止 `/discover` `/execute`。
3. Timeline 文案不含百分比完成度、不含「已覆盖」。
4. 未 ready 调 plan 的前端路径：必须展示 `research_goal_not_ready`。
5. 隔离与 234、v30 回归。

手工：澄清前点方案 → 方案门琥珀；澄清后点方案 → 方案门墨勾，来源门仍灰。

## 7. 验收标准

- 门状态 100% 来自 API 回包字段，无前端猜测。
- 用户无法把 idle 标成 ready。
- CONCEPT_QA 会话：方案及之后保持 idle。
- 天文与医学用同一套投影；差别只来自回包 `domain` 展示，不来自两套 if。

---

# Frontend Phase 3 · Sources + Mapping

## 1. 页面目标

做出发现与对齐两个工作面。  
Sources：插件目录 → 未验证候选卡 → 选择表。  
Mapping：Schema Pack + 映射表 + REVIEW。  
两页都 **`row_count` 展示为 0**，`generates_data` 为假。

## 2. 页面组件

**Sources**

| 组件 | 字段 |
|---|---|
| Registry Strip | `display_name` `status` `fetch_binding` `integrate_eligible` |
| Source Card | `source_id` `locator` `field_hypotheses` `verification_status` `next_action` |
| Selection Board | 入选 / 排除两表：`reason` `reason_code` `hypothesized_fields` |
| Risk List | `join_risk` 警告条，不进小字 |
| Honesty Header | 固定显示 API 的 `fetched` `integrated`（应为 false） |

**Mapping**

| 组件 | 字段 |
|---|---|
| Pack Header | `schema_pack_id` `binding` `status` `domain` |
| Frozen / Draft Banner | 医学 frozen_canonical；天文 DRAFT |
| Field List | 必顶：`source_id` `raw_field` `raw_value`；oncology 另顶 `response_domain` `patient_id` `sample_id` |
| Mapping Table | `source_field` `target_field` `confidence` `status` `risk_level` |
| Status Token | `AUTO` 墨色，`REVIEW` 琥珀，不用绿 |

用户不能把 `unverified` 改成 verified，不能删 `response_domain`。

## 3. API 依赖

| 动作 | API |
|---|---|
| 打开 Sources / 切 domain | `GET /api/v30/registry/sources?domain=` |
| 发现 | `POST /api/v30/discover` |
| 选择 | `POST /api/v30/source-selection` |
| 生成 pack | `POST /api/v30/schema-packs/generate` |
| 回看 pack | `GET /api/v30/schema-packs/{id}` |
| 映射 | `POST /api/v30/schema-packs/match` |

入参只拼 Store 已有对象：`plan.domain` / `plan.topic` / `memory.constraints` / `plan.contract_id`。不得前端编造 accession。

打开 Sources **不**自动 Discover。打开 Mapping **不**自动 Match。

## 4. 数据状态管理

```text
Sources.open
  → 若 plan.domain 存在：GET registry
  → 用户点「发现候选」：POST discover → store.discovery
  → 用户点「应用选择」：POST source-selection
        candidates = discovery.candidates
        contract = 从 plan / memory 映射 SelectionContract
        constraints = memory.constraints
      → store.selection
      → 来源门 ready

Mapping.open
  → 用户点「生成或绑定 Schema Pack」：POST generate → store.schemaPack
  → 用户点「预览映射」：POST match
        source_fields = selection 假设字段（不得发明临床值）
      → store.mappings
      → 字段门 ready（仅当回包存在；row_count 只展示，不参与门计算）
```

覆盖矩阵若要画，只能列出 `field_hypotheses` 与 `coverage_claimed===false`。禁止进度条。

METABRIC：只展示后端 `reason_code=user_constraint`，前端不写死排除名单。

## 5. 文件目录

```text
frontend/v31/
  styles/pages/sources.css
  styles/pages/mapping.css
  app/pages/sources.js
  app/pages/mapping.js
  app/components/source-card.js
  app/components/selection-board.js
  app/components/mapping-table.js
  app/api/v30.js                 增加 registry / discover / select / packs / match
```

## 6. 测试方案

新增 `test_phase3_sources_mapping.py`：

1. Source Card 模板含 `unverified`、`source_id`；不含「已覆盖」。
2. `v30.js` 仍无 `/integration/execute`、`/api/adapters`。
3. Mapping 页写死展示 `row_count` 来自回包；测试用 fixture `row_count=0` 断言界面字符串为 0。
4. 选择板能渲染 `rejected_candidates` 与 `reason_code`。
5. 医学 pack fixture：页面出现 `response_domain` 与 `forbid_cross_entity` 相关约束文案（来自 copy，不来自前端新造规则）。
6. 隔离：旧 `app.js` 无 v30；234；v30 后端测试。

手工：HER2 排除 METABRIC 后选择表可见约束码；超新星 Registry 见 `catalog_only` / 无 fetch_binding。

## 7. 验收标准

- 发现页页眉能否看见「未取数 · 未整合」取决于 API 布尔值，不写死反过来说成已取数。
- 映射页没有数据行表格。
- REVIEW 不是“已采用该值”。
- 来源 / 字段两门仅在对应回包进入 Store 后变为 ready。

---

# Frontend Phase 4 · Evidence Graph

## 1. 页面目标

只读解释面：为什么选源、为什么映射、为什么 REVIEW、为什么排除。  
**不能**拖拽改边，**不能**新增患者关系，**不能**把图当事实库。

Figure Understanding 按设计是附带条；**本阶段默认不做**，以免扩大范围。若做，必须另开小节且 `enters_primary_table` 大字否定。本计划 Phase 4 验收不依赖图理解。

## 2. 页面组件

| 组件 | 规则 |
|---|---|
| Graph Canvas | 少节点、可点、不可编辑；节点取 `node_type` + `label` |
| Why Drawer | `statement` `why[]` `path[]` `edges[]` `forbidden_edges_present` |
| Graph Notice | 回包 `notice` + 三否定：不替代 EvidenceBuilder、不含患者边、不复制事实值 |
| Forbidden State | `contains_patient_edges` 或 why.`forbidden_edges_present` 为真 → 全页错误，不画禁边 |

布局：中央疏图，右侧抽屉，四周留白。不用力导向表演。

建议：用 SVG / 绝对定位分层，按 `edges` 画直线。禁止引入重型图谱库，除非原生方案先失败并另写理由。

## 3. API 依赖

| 动作 | API |
|---|---|
| 投影 | `POST /api/v30/graphs/project` |
| 回看 | `GET /api/v30/graphs/{graph_id}` |
| 追问 | `GET /api/v30/graphs/{graph_id}/why/{finding_id}` |

Project 入参只传 Store 已有：`goal` `contract` `candidates` `selection` `schema_pack` `mappings` `constraints`。不传患者行、不传数值事实。

进入页面不自动 project，用户点「生成解释图」。

## 4. 数据状态管理

```text
Graph.generate
  → POST project → store.graph
  → 证据门 ready 当且仅当 graph 存在且 contains_patient_edges===false
  → 否则 blocked

Node.click
  → 若节点 refs 含 finding_id：GET why
  → store.lastWhy
  → 打开抽屉

Drawer.close
  → 保留 lastWhy 供回看，不改 graph
```

前端不得补边、不得合并同名 `patient_id` 节点、不得请求不存在的“患者关系 API”。

## 5. 文件目录

```text
frontend/v31/
  styles/pages/graph.css
  styles/components/drawers.css
  app/pages/graph.js
  app/components/graph-canvas.js
  app/components/why-drawer.js
  app/api/v30.js                 增加 project / getGraph / why
```

不建 `graph-editor.js`。

## 6. 测试方案

新增 `test_phase4_graph.py`：

1. 源码扫描：`graph-canvas.js` / `graph.js` 不含 `addEdge`、`SAME_PATIENT` 创建逻辑、`JOINED_ACROSS_STUDY` 创建逻辑。
2. Why Drawer 绑定字段与 API 一致。
3. fixture：`contains_patient_edges=true` 时渲染错误态，不渲染网络。
4. `v30.js` 仍无 `/integration/execute`（可延到 Phase 5）。
5. 隔离 + v30 `test_graph_constraints` + 234。

手工：点 REVIEW 映射节点能看到 why；图上无患者—患者边。

## 7. 验收标准

- 只读。键盘可关闭抽屉。
- 无患者关系生成入口。
- 证据门不因“打开了 Graph 页”而 ready，只因 `store.graph` 存在。
- 动画：抽屉 200ms 推入；`prefers-reduced-motion` 时瞬时。

---

# Frontend Phase 5 · Integration Preview + Dataset

## 1. 页面目标

Preview：执行前合同，默认立场是**还不能跑**。  
Dataset：**仅** oncology 真实执行成功后展示主表、质量门、证据与导出。天文永远空态。

## 2. 页面组件

**Preview**

| 组件 | 字段 |
|---|---|
| Verdict Banner | `execution_allowed`（默认 false） |
| Adapter List | `adapter_candidates`：`fetch_binding` `would_invoke` `integrate_eligible` |
| Tool Recap | Prepare 后的 `tool_candidates` |
| Join Policy | `join_policy`，oncology 期望 `forbid_cross_entity` |
| Medical Constraints | 回包列表 + copy 中的 IHC / AUC 句 |
| Prepare CTA | 「编译执行请求」→ `/prepare` |
| Execute Gate | 双步确认；默认焦点在取消；非 oncology 永久禁用 |

**Dataset**

| 组件 | 字段 |
|---|---|
| Result Strip | `task_id` `status` `quality_status` `export_available` `evidence_summary` |
| Research Table | 旧 `modeling_dataset`；列优先 source_id / raw_field / raw_value / patient_id / sample_id / response_domain |
| Quality Strip | PASS / REVIEW / REJECT，绿只给 PASS |
| Evidence Drawer | `/api/v3/evidence/field/{record_id}/{field}` |
| Export Bar | 旧 `/api/agent/tasks/{id}/export/{fmt}` |
| Domain Empty | 非 oncology 或未执行：引用 `only_oncology_integrate_supported` |

无行：允许 metadata / quality_report；CSV 失败则展示旧服务错误，不造行。

## 3. API 依赖

| 动作 | API | 谁能调用 |
|---|---|---|
| 预览 | `POST /api/v30/integration/preview` | 有 pack + selection |
| 编译 | `POST /api/v30/integration/prepare` | 有 IntegrationPlan |
| 执行 | `POST /api/v30/integration/execute` | `domain==oncology` 且 `execution_ready==true`（**字段来自 preview 回包，不是前端猜领域词**） |
| 读任务 | `GET /api/agent/tasks/{task_id}` | 仅已有 `executionResult.task_id` |
| 导出 | `GET /api/agent/tasks/{task_id}/export/{fmt}` | `export_available==true` |
| 证据 | `GET /api/v3/evidence/field/{record_id}/{field}` | 用户点击单元格 |

进入 Preview 可自动 preview 一次（规划，不取数）。  
Execute 必须二次确认。  
`agent-export.js` 在本阶段才允许被 Dataset 引用。  
禁止 `/api/adapters/*`。

## 4. 数据状态管理

```text
Preview.open
  → POST preview → store.integrationPlan
  → 预览门 ready

Prepare.click
  → POST prepare → store.executionPreview
  → 仍 executed=false

Execute.click
  → 若 executionPreview.domain !== "oncology"：禁用，不发请求
  → 若 !execution_ready：展示 execution_not_ready
  → POST execute
        422 only_oncology_integrate_supported → 数据门 blocked
        503 old_runner_not_injected → 数据门 blocked
        成功 → store.executionResult
             → GET /api/agent/tasks/{task_id} → store.agentTask
             → 数据门 executed
```

前端不得在天文 preview 上改 `domain` 再执行。  
两个入口同时跑执行：产品层约定 Dataset 执行时，页眉提示「不要同时在内核实验室提交同一问题」；不做分布式锁（后端未提供）。

## 5. 文件目录

```text
frontend/v31/
  styles/pages/preview.css
  styles/pages/dataset.css
  app/pages/preview.js
  app/pages/dataset.js
  app/components/plan-sheet.js
  app/components/execute-gate.js
  app/components/research-table.js
  app/components/evidence-drawer.js
  app/components/quality-strip.js
  app/api/v30.js                 增加 preview / prepare / execute
  app/api/agent-export.js        task / export / evidence
```

## 6. 测试方案

新增 `test_phase5_preview_dataset.py`：

1. Preview 模板默认出现 `execution_allowed` 绑定，Execute 按钮初始 disabled。
2. `execute-gate.js`：仅当 `domain==="oncology"` 且 `execution_ready===true` 才 enable。用 fixture 天文 preview 断言不发出 execute。
3. `agent-export.js` 只含 `/api/agent/tasks` 与 `/api/v3/evidence`，不含 `/api/adapters`。
4. Dataset 空态含 `only_oncology_integrate_supported` 文案键。
5. 源码不含 SDTI、不含「智能整合完成」。
6. **隔离铁律：** `frontend/app.js` 仍无 `/api/v30`；`frontend/v31` 无对旧 `app.js` 的 import。
7. 后端：`test_oncology_integrate_bridge.py` + 全量 v30 + 234。

手工：

- HER2 走完 Prepare → 确认框取消 → 无 task。
- HER2 确认执行 → Dataset 出现 task_id 与 quality；点单元格能开证据（若该任务有 record）。
- 超新星 Preview 执行键不可聚焦。

浏览器验收（有工具则用，无则手工列步骤）：Preview 禁用执行；oncology 二次确认后才有表。

## 7. 验收标准

- Preview 默认不能执行。
- 天文不能出主表。
- oncology 执行后表中仍能看到 `source_id` 与原始字段列（有则显示，无则「—」，不编造）。
- Quality REJECT 仍可下载数据包，但无「发布」措辞。
- 旧内核实验室 `/` 与 `#task-entry` 仍可独立跑旧协议。

---

# 3. 视觉实施对照（各 Phase 共用检查单）

每个 Phase 的 UI 评审只问这四句：

1. Apple：这一屏有没有多余盒子？主操作是不是只有一个？
2. Google：门 / 错误 / 下一步是不是扫一眼能读懂？
3. Perplexity：来源是不是卡片 + 可点 ID，而不是一段散文？
4. Elicit：判断是不是在表列里（需求、选择、映射），而不是聊天里？

明确不做：普通聊天窗、机器人形象、卡片墙、花哨动画、打字机、假百分比、暗色主题。

动效上限：页切 180ms、门点 160ms、抽屉 200ms。执行无彩屑。

---

# 4. 测试总策略

```text
每阶段最少三层

A. 隔离测试     旧 frontend 零 v30；旧 GET / 文案仍在
B. 契约测试     v31 源码 URL / 字段 / 诚实句
C. 回归         backend/tests/v30 + Phase 0 234 文件集
```

不把前端验收做成“截图即过”。能用 TestClient 打静态文件和 API 的，优先自动化。  
交互过门用短手工清单写进各阶段报告。

建议目录：

```text
backend/tests/v31_frontend/
  test_phase0_shell.py
  test_phase1_copilot.py
  test_phase2_timeline.py
  test_phase3_sources_mapping.py
  test_phase4_graph.py
  test_phase5_preview_dataset.py
  test_isolation_old_frontend.py    可每阶段都跑
```

禁止把断言写进 `backend/tests/test_api.py`（那是旧前端冻结合同）。

---

# 5. 阶段依赖与停线

```text
Phase 0 壳
    ↓
Phase 1 Home + Copilot          无 /plan
    ↓
Phase 2 Timeline + /plan        来源之后的门保持 idle
    ↓
Phase 3 Sources + Mapping
    ↓
Phase 4 Graph + Why             只读
    ↓
Phase 5 Preview + Dataset       仅 oncology 执行
```

某阶段未验收，不得提前把下一阶段 API 填进页面按钮（封装函数可以先挂在 `v30.js` 但不暴露 CTA）。

**全程停线：**

- 不重写 `frontend/app.js`
- 不删除旧页面
- 不改旧 `/api/v3` 工作流
- 旧页面不调用 `/api/v30`
- 不把 `/` 换成 V3.1
- 不实现天文真实 Integrate UI
- 不把 Figure 数字化入库做成编辑器（即使 Phase 4 加了理解条）

---

# 6. 建议实施顺序以外的非目标

- 不在本计划更换默认首页（`/` 保持内核实验室）
- 不在本计划做抽取门面 `/api/v30/extract`
- 不在本计划做评测看板、SDTI 新分数
- 不在本计划合并两套 CSS token
- 不在本计划引入 npm 依赖

若产品日后要把 `/` 切到 V3.1：必须另开变更，先改 `test_api.py` 合同并保留 `/lab/` 或 `/index.html` 旧入口。那不是本计划的 Phase。

---

# 7. 每阶段交付物（实施时才写，本文件不写代码）

每个 Frontend Phase 结束应有：

1. `frontend/v31/` 增量文件
2. 对应 `backend/tests/v31_frontend/test_phaseN_*.py`
3. 短报告（建议 `docs/v31_baseline/FRONTEND_PHASE{N}_REPORT.md`）：改了什么、**明确列出未改的旧前端文件**、测试结果、与设计文档的偏差

本实施计划到此结束。下一步若开工，从 Phase 0 单独开任务，只建壳，不接 Copilot。
