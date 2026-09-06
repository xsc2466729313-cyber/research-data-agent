# 最终代码审查

- 审查日期：2026-09-05
- 立场：高级代码审查，只读，不改代码
- 范围：`backend/app/v30/**`、`frontend/v31/**`、与旧内核的接缝、测试与仓库卫生
- 不审查：冻结公式是否改写（抽查：v30 不改 `docs/06` / `canonical_schema.yaml` / `medical_rules.yaml`）

---

## 1. 架构问题

### 重复逻辑

1. **`hypothesizedFields` 三份实现，语义不一致。**
   - `frontend/v31/app/pages/sources.js`：读 `discovery.candidates[].field_hypotheses`
   - `frontend/v31/app/pages/mapping.js`：读 selection 的 `hypothesized_fields` **加** candidate hypotheses
   - `frontend/v31/app/pages/graph.js`：只读 selection 的 `hypothesized_fields`
   - 后果：Mapping 与 Graph 的 contract.required_fields 可能对不齐，Graph 投影比 Mapping 更瘦。

2. **领域判定关键词复制多处。**
   - `router/rules.py`、`copilot/service.py`、`schema_generator/service.py`、`integration/service.py`、`bridges/execution.py`、`integration/executor.py`
   - 同一句「HER2 / 乳腺 / supernova」散落，改一处不会同步。

3. **v30.js 死别名。**
   - `listRegistrySources`、`matchSchemaPack` 无引用。

### 模块耦合

优点：`V30Runtime` 声明不调 Adapter；Discovery / Graph / Figure / Preview 的 AST 测试禁止误 import 旧 sources。

问题：

1. **Planner 直接依赖旧 `RequirementAgent` + `ResearchPlanningV2`。** oncology 规划质量绑在旧链上，非 oncology 只能 stub。这是有意的门面，但「通用 Planner」名过重。
2. **Source Selection 依赖 `SourceBroker`。** 选择算法不是 v30 自有，覆盖矩阵仍是旧语义，只是强制 `unverified`。
3. **Matcher Bridge 与 Schema Pack 内存生成器耦合。** pack 重启丢失则 match 404。
4. **Execute 经 `app.state.research_agent`。** v30 与主 Agent 生命周期绑在同一个 FastAPI 进程，这是对的；但 preview/prepare/execute 三步没有把 `session_id` 写成一等公民，规划会话与执行任务对不齐。

### 不合理依赖

1. **executor 在 cBioPortal 路径硬编码 `brca_metabric`。** 这不是 Registry 或用户选择的结果，是执行层偷渡的 accession。
2. **frontend/v31 无构建工具是合理的**；但 `timeline-fixtures.json` 放在 `app/` 运行目录，只给测试用。
3. **Docker 前端镜像不拷贝 v31**，与「产品入口是 /v31/」冲突。

架构判断：规划层分层清楚，执行层仍是「旧内核外包」。这不是错误，但调用方必须承认。

---

## 2. Agent 问题

### 硬编码领域

- Router 用词表分 oncology / astronomy / biomedicine / unknown。
- Copilot 用 regex 抽 HER2 / 乳腺 / 红移；oncology 数据需求四条写死。
- Schema Pack `_is_oncology_task` / `_is_supernova_task`。
- Executor `_is_oncology` 甚至把 `join_policy == forbid_cross_entity` 当成医学旁证。

这不是可插拔插件注册表，是**词表门面**。新领域要改代码。

### 假智能

1. Copilot 看起来像对话，实际是规则机。评委若追问「用了什么模型」，必须答：规划层默认不用千问；旧执行 `use_qwen=False`。
2. Discovery 名叫发现，只是 Registry 展开。
3. Figure Understanding 名叫理解，只是 caption 关键词。`digitization_possible=true` 容易被听成「已经能数字化」。
4. Copilot ready 文案「尚未挂载 Planner」是**过期智能话术**，会在现场打自己脸。

### 固定流程

八步脊骨是产品流程，不是用户可编排的 Agent。  
Router 只有四态。没有工具选择循环，没有根据中间结果改计划的 v30 编排器。  
闭环与批评仍在旧 `closed_loop` / quality，不在 v30 runtime。

这不是欺骗，但不要把系统讲成自主科研 Agent。它是**编译管道 + 医学插件**。

---

## 3. 数据可信问题

### LLM 生成数据进入主表？

**规划层：没有。**  
Copilot / Router / Figure / Graph / Preview 都不写行。`generates_data=false`，`row_count=0`，`enters_primary_table=false`。

**执行层：旧 runner 可能出表，但 `use_qwen=False`。**  
主表来自 Adapter + 旧整合，不是 v30 让 LLM 编患者。  
风险在旧链本身（确定性 fallback、外部 API），不在 v30 新造假表。

### source 丢失？

- 冻结 schema 与 Mapping 页强调 `source_id`。
- Graph 节点 refs 带 `source_id` / `source_key`，禁止若干 fact payload key。
- **缺口：** v31 执行后无 Dataset，无法在新 UI 核对每行 `source_id`。
- **缺口：** executor 写入 `brca_metabric` 时，这条 accession 不是用户选择图上的节点。

### evidence 丢失？

- Graph **明确不替代** EvidenceBuilder。
- 真实 Evidence 仍在旧 `/api/v3/evidence/field/{record}/{field}`。
- v31 没有证据格。Why Drawer 解释的是规划原因，不是单元格 Evidence。
- 非 finding 节点点击时，前端用节点 `reasons` 拼 `lastWhy`，`finding_id` 被设成 `nodeId`。这不会造数值，但会让「Why API」看起来被调用过。

### quality 绕过？

- Preview / prepare **不跑** Quality Gate。
- Execute 走 `ResearchAgentService.run`，测试期望带回 `quality_gate_report`。
- v30 没有新的 Quality 实现，也没有把 REJECT 改成 PASS 的代码路径。
- **前端无法展示 Quality。** 绕过风险不在算法，在演示时「看不见门就当没有门」。

医学硬规则（IHC 2+、CNA≠IHC、AUC≠pCR、禁 Join）写在 preview 约束和旧 `medical_rules.yaml`。v30 没有放松这些文件。

---

## 4. 前端问题

### 是否污染旧 frontend？

**没有。**

- `frontend/app.js` 无 `/api/v30`
- `/` 仍是「发送并开始研究」
- v31 不 import 旧 `app.js`
- 旧页有自己的进度条和 localStorage；新页禁止 localStorage

隔离是这轮最好的工程决定。

### API 是否混乱？

- v31 业务只打 `/api/v30/*` + `/health`
- 明确不打 `/api/v30/integration/*`、`/api/agent/tasks`、`/api/adapters/*`
- Home 先 `route` 再 `createSession`：第一次路由**没有** `session_id`，与 Copilot 后续带会话的 route 不一致
- Graph Why：有的走 GET why，有的走本地拼装，合同不统一

### 是否存在假状态？

总体诚实：门靠 Store 字段，不靠「题目含 HER2」。

残留风险：

1. 左轨叫「执行 / 科研数据资产」，页面却是「尚未开放」。评委可能以为后两步已产品化。
2. Timeline / Sources / Mapping / Graph 打开右轨 Memory 框，内容为空——像坏了，不像「本页不画」。
3. Sources 无勾选 UI，「应用选择」把 discovery 全量送进 selector，用户以为自己选了。
4. 进入 Graph 不自动 project 是对的；证据门因此不会误亮。这一点保持了。

---

## 5. 工程问题

### 临时文件

仓库可见、不应进演示目录的未跟踪物：

- `tmp-oncology-bridge/cbio/responses/**`（METABRIC 缓存）
- `data/state/agent.sqlite3`
- `.pytest_cache/`（已 gitignore）
- `backend/tests/v31_frontend/__pycache__/`

比赛机不要打开这些目录当「数据资产」。

### 无用 / 过期代码

- Copilot「尚未挂载 Planner」
- v30.js 两个未使用 export
- `archive/v31_baseline/DEMO_DESIGN_REPORT.md` 仍写「前端尚未接 V3.1」——已被 `/v31/` 证伪，但本审查不改它
- SessionStore 四个 Phase 5 键悬空

### 测试缺失

已有且当日通过：v30 75、v31 31、234 回归 234。

缺失：

- 无 `test_phase5_preview_dataset.py`（与未做页面一致）
- 无浏览器 E2E（前端契约是源码扫描 + TestClient）
- 无「用户排除 METABRIC 后 execute 不得再 focus brca_metabric」的集成测试
- 无 Memory 持久化 / 多进程隔离测试（当前模型也不支持）
- 无 Docker Nginx 提供 `/v31/` 的测试（当前镜像确实没有）

---

## 6. 比赛前必须处理清单

按你的指令，**这里只列，不修。**

### Critical

| 项 | 为什么是 Critical |
|---|---|
| 演示口播与产品范围对齐 | v31 没有 Preview/Dataset。若讲「一键出表」即虚假陈述。脚本见 `FINAL_DEMO_SCRIPT.md` |
| 不要用 Docker Nginx `:8888` 当 V3.1 入口 | 镜像没有 `frontend/v31/`，评委只会看到旧「发送并开始研究」 |

### High

| 项 | 位置 | 风险 |
|---|---|---|
| Copilot 声称 Planner 未挂载 | `backend/app/v30/copilot/service.py` `_research_reply` | 现场自我打脸 |
| Execute 硬编码 `brca_metabric` | `backend/app/v30/integration/executor.py` | 与「排除 METABRIC」演示冲突，来源追踪不诚实 |
| 排除约束未传到 executor | Memory.constraints → 选择层有效，执行层丢 | 规划与取数两套真相 |
| 右轨 Memory 空盒 | `main.js` 显示 block，仅 Copilot 填充 | 像缺陷 |

### Medium

| 项 | 位置 | 风险 |
|---|---|---|
| 三处 `hypothesizedFields` 不一致 | sources / mapping / graph | 映射与图合同漂移 |
| Why 本地伪造信封 | `graph.js` `openWhy` | 评审问「是否调了 why API」时说不清 |
| 会话与执行无同一 `session_id` | integration API | 无法证明「这张表来自刚才那次规划」 |
| 规划态不落盘 | Memory / Graph / Pack | 演示中重启后端，整场会话蒸发 |
| 未跟踪缓存目录 | `tmp-oncology-bridge/`、`agent.sqlite3` | 误提交或被当成结果 |

### Low

| 项 | 位置 |
|---|---|
| 未使用 API 别名 | `frontend/v31/app/api/v30.js` |
| fixtures 放在 app 目录 | `frontend/v31/app/timeline-fixtures.json` |
| 过期 Demo 设计文档 | `archive/v31_baseline/DEMO_DESIGN_REPORT.md` |
| Home 无 session 的 route | `home.js` |

---

## 7. 审查结论

代码质量判断：

- **隔离做得好。** 旧前端、冻结配置、Quality / Evidence 内核没有被 v30 改写。
- **诚实标志做得好。** `fetched` / `integrated` / `enters_primary_table` / `execution_allowed` 在后端一致为保守值。
- **产品完成度不对称。** 规划到 Graph 可交付；执行到资产只有 API。
- **最大工程债不是缺 React，而是执行层偷渡 METABRIC、Copilot 过期文案、以及前端把未做的两步画在脊骨上。**

比赛策略：按 `FINAL_DEMO_SCRIPT.md` 演示到证据解释，把拒绝执行当成能力，而不是把未完成的 Dataset 讲成已完成。
