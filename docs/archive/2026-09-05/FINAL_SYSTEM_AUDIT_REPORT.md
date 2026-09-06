# 最终系统验收报告

- 验收日期：2026-09-05
- 验收人角色：项目负责人
- 原则：只依据当前仓库代码、测试运行结果、目录与 API，不依据过期设计稿推断能力
- 本报告不修改任何代码

---

## 1. 项目最终定位

当前系统是：

**通用入口的科研数据规划智能体 + 医学高质量执行插件。**

它已经能把一句研究想法编译成：会话、理解、方案、来源假说、字段对齐、证据解释。  
医学领域在旧 `ResearchAgentService` 注入后，可以把规划结果交给现有 Adapter / Quality / Evidence 链，产出可追溯数据集。

它**还没有**达到完整口号：

> “通用科研数据发现与可信整合智能体”

原因（来自代码，不是修辞）：

| 口号承诺 | 当前事实 |
|---|---|
| 通用发现 | `DiscoveryFacade` 只枚举 Registry 并写字段假说，`fetched=false`，不搜 GEO/GSE，不调 Adapter |
| 通用整合 | `OncologyIntegrator` 非 oncology 抛 `only_oncology_integrate_supported` |
| 可信主表 | 主表只在 `/api/v30/integration/execute` 成功后由旧 runner 产生；v31 前端没有 Preview / Dataset 页 |
| 智能理解 | Router / Copilot 是规则与关键词，不是通用 LLM 研究秘书 |

更准确的对外表述：

> 有边界的混合式科研数据工作台：规划层通用且诚实，真实取数与清洗只挂在医学插件上。

---

## 2. 完整架构

```text
用户输入
  ↓
Router          POST /api/v30/route
  ↓
Copilot         POST /api/v30/copilot/turn
  ↓
Memory          进程内会话
  ↓
Planner         POST /api/v30/plan
  ↓
Discovery       POST /api/v30/discover
  ↓
Source Selection POST /api/v30/source-selection
  ↓
Schema Pack     POST /api/v30/schema-packs/generate
  ↓
Matcher         POST /api/v30/schema-packs/match
  ↓
Evidence        POST /api/v30/graphs/project
  ↓
Integration     POST /api/v30/integration/preview → prepare
  ↓
Dataset         POST /api/v30/integration/execute → 旧 runner 主表
```

### 每层实际代码位置

| 层 | 代码 | 前端表面 |
|---|---|---|
| 用户输入 | `frontend/v31/app/pages/home.js`；旧入口 `frontend/index.html` | `/v31/#/home`；`/` 仍是内核实验室 |
| Router | `backend/app/v30/router/service.py`、`rules.py`、`configs/v30/router_rules.yaml` | Home 先调 route；Copilot 每轮再调 |
| Copilot | `backend/app/v30/copilot/service.py` | `/v31/#/r/{id}/copilot` |
| Memory | `backend/app/v30/memory/service.py`、`store.py` | SessionStore + 右轨（仅 Copilot 写入 Memory 条） |
| Planner | `backend/app/v30/planner/service.py`、`ready.py`；oncology 转调 `RequirementAgent` + `ResearchPlanningV2` | Copilot「生成研究方案」→ Timeline |
| Discovery | `backend/app/v30/discovery/service.py` | Sources「发现候选」 |
| Source Selection | `backend/app/v30/source_selection/service.py`（复用 `SourceBroker` matcher/selector） | Sources「应用选择」 |
| Schema | `backend/app/v30/schema_generator/service.py`、`configs/v30/schema_packs.yaml` | Mapping「生成或绑定 Schema Pack」 |
| Matcher | `backend/app/v30/matcher_bridge/service.py` → `SchemaMatcherV3` | Mapping「预览映射」 |
| Evidence | `backend/app/v30/graph/service.py`、`store.py`；附图 `backend/app/v30/figures/service.py` | Graph |
| Integration | `backend/app/v30/integration/service.py`；`bridges/execution.py` | **前端未接** |
| Dataset | `backend/app/v30/integration/executor.py` → `ResearchAgentService.run` | **前端未接**；旧页 `/#task-entry` 走独立旧协议 |

挂载：

- API：`backend/app/v30/api.py` → `mount_v30_routes(app)`
- 运行时：`backend/app/v30/runtime.py`（只串 Router / Copilot / Memory / Planner）
- 静态：`backend/app/main.py` `StaticFiles(directory=frontend)`，因此 `/v31/` 在 uvicorn 下可用

---

## 3. 后端模块完成情况

### Router

- **状态：完成**
- **代码位置：** `backend/app/v30/router/`
- **测试：** `backend/tests/v30/test_router.py`（6）
- **限制：** 确定性 token 路由（CHAT / CONCEPT_QA / CLARIFY / PLAN）。领域靠 `her2`/`超新星` 等关键词。不取数。

### Copilot

- **状态：部分完成**
- **代码位置：** `backend/app/v30/copilot/service.py`
- **测试：** `backend/tests/v30/test_copilot.py`（4）
- **限制：** 规则提取目标，不是 LLM。oncology 固定四条 `not_retrieved` 数据需求。ready 后若路由为 PLAN，回复仍写「本阶段尚未挂载 Planner」——**与已存在的 `/api/v30/plan` 矛盾**。

### Memory

- **状态：完成**
- **代码位置：** `backend/app/v30/memory/`
- **测试：** `backend/tests/v30/test_memory_isolation.py`（4）
- **限制：** 进程内字典，不持久化，不含患者行。重启即空。只存 goal / clarifications / constraints。

### Planner

- **状态：部分完成**
- **代码位置：** `backend/app/v30/planner/`
- **测试：** `backend/tests/v30/test_planner_gate.py`（5）、`test_v30_api.py` 中 422 gate
- **限制：** 未澄清返回 422 `research_goal_not_ready`。oncology 转调旧 RequirementAgent / PlanningV2。非 oncology 只出 notice，不伪造冻结合同。不取数。

### Registry

- **状态：完成**
- **代码位置：** `backend/app/v30/registry/service.py`；`configs/v30/source_registry/{oncology,astronomy,materials}.yaml`
- **测试：** `backend/tests/v30/test_registry.py`（4）
- **限制：** 只读能力目录。`astronomy` / `materials` 禁止 `active + fetch`。notice 写明不是数据本身。

### Discovery

- **状态：部分完成**
- **代码位置：** `backend/app/v30/discovery/service.py`
- **测试：** `backend/tests/v30/test_discovery_honesty.py`（5）
- **限制：** 名不副实：过滤 Registry + 字段假说。恒 `fetched=false`、`integrated=false`、`verification_status=unverified`。不调用 GEO/GDC Adapter，不验证 accession。

### Source Selection

- **状态：完成**
- **代码位置：** `backend/app/v30/source_selection/service.py`
- **测试：** `backend/tests/v30/test_source_selection.py`（5）
- **限制：** 复用 SourceBroker 覆盖选择，不取数。用户约束可排除来源。`join_risk` 含禁止跨研究患者 Join。仍把 `verified` 降格为 `unverified`。

### Schema Pack

- **状态：完成**
- **代码位置：** `backend/app/v30/schema_generator/service.py`
- **测试：** `backend/tests/v30/test_schema_pack.py`（4）
- **限制：** oncology 绑定冻结 `oncology_canonical_v0.1`；astronomy 为任务级 DRAFT。`row_count=0`，`generates_data=false`。内存缓存，重启丢失。领域用关键词 `_is_oncology_task` / `_is_supernova_task`。

### Matcher Bridge

- **状态：完成**
- **代码位置：** `backend/app/v30/matcher_bridge/service.py`
- **测试：** `backend/tests/v30/test_schema_matcher_bridge.py`（3）
- **限制：** 薄包装 `SchemaMatcherV3.match`。不改算法，不产生数据行。

### Evidence Graph

- **状态：完成**（作为投影层）
- **代码位置：** `backend/app/v30/graph/`
- **测试：** `backend/tests/v30/test_graph_constraints.py`（7）
- **限制：** 解释图，不是事实库。禁止 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`。不复制 `raw_value` / 患者行。进程内存储。

### Figure Understanding

- **状态：部分完成**
- **代码位置：** `backend/app/v30/figures/service.py`
- **测试：** `backend/tests/v30/test_figure_understanding.py`（5）
- **限制：** 按 caption / figure_id 关键词分类（光变、KM、热图等）。不读像素，不数字化。`enters_primary_table` 恒 false。缺 `source_id` 返回 422 `source_id_required`。

### Integration Preview

- **状态：完成**（后端）
- **代码位置：** `backend/app/v30/integration/service.py`
- **测试：** `backend/tests/v30/test_integration_preview.py`（5）
- **限制：** `execution_allowed=false`，`would_invoke=false`，`fetched=false`。oncology 写出 `join_policy=forbid_cross_entity` 与 HER2 四条约束。前端未接。

### ExecutionBridge

- **状态：完成**（prepare）；execute 只是委托
- **代码位置：** `backend/app/v30/bridges/execution.py`
- **测试：** `backend/tests/v30/test_execution_bridge.py`（6）
- **限制：** prepare 编译 `ExecutionRequestPreview`，`executed=false`。execute 交给 `OncologyIntegrator`。前端未接。

### Oncology Real Integrate

- **状态：部分完成**
- **代码位置：** `backend/app/v30/integration/executor.py`
- **测试：** `backend/tests/v30/test_oncology_integrate_bridge.py`（7）
- **限制：**
  - 仅 oncology；否则 422 `only_oncology_integrate_supported`
  - `execution_ready` 为假则 422 `execution_not_ready`
  - runner 未注入则 503 `old_runner_not_injected`
  - `use_qwen=False`，走确定性旧链
  - 若工具含 `search_cbioportal`，**硬编码** `focus_accessions=["brca_metabric"]`，可能与用户「排除 METABRIC」约束冲突
  - 本层不直接 import Adapter，但经 `ResearchAgentService.run` 间接取数

---

## 4. 前端完成情况

入口：`http://127.0.0.1:8000/v31/`（uvicorn / FastAPI StaticFiles）。  
Docker Nginx 镜像（`frontend/Dockerfile`）**只复制旧三件套**，`:8888` **没有** `/v31/`。

旧 `/` 仍是「千问肿瘤科研数据智能体」，主按钮「发送并开始研究」，`frontend/app.js` **不含** `/api/v30`。

| 页面 | 状态 | 对应文件 | API |
|---|---|---|---|
| Home | 完成 | `frontend/v31/app/pages/home.js` | `POST /api/v30/route`、`POST /api/v30/sessions` |
| Copilot | 完成 | `frontend/v31/app/pages/copilot.js` | `GET .../memory`、`POST /copilot/turn`、`POST /plan` |
| Timeline | 完成 | `frontend/v31/app/pages/timeline.js`、`timeline-store.js` | 无直接 fetch；投影 Store |
| Sources | 完成 | `frontend/v31/app/pages/sources.js` | `GET /registry/sources`、`POST /discover`、`POST /source-selection` |
| Mapping | 完成 | `frontend/v31/app/pages/mapping.js` | `POST /schema-packs/generate`、`GET /schema-packs/{id}`、`POST /schema-packs/match` |
| Graph | 完成 | `frontend/v31/app/pages/graph.js` | `POST /graphs/project`、`GET /graphs/{id}`、`GET .../why/{id}`、`POST /figures/understand` |
| Preview | **未完成** | 无 `preview.js`；`main.js` 显示「本阶段尚未开放」 | 前端不调 `/api/v30/integration/*` |
| Dataset | **未完成** | 无 `dataset.js` | 前端不调 `/api/agent/tasks` |

左轨产品名（`GATE_DEFS`）：

科研问题 → AI理解 → 研究规划 → 数据发现 → 字段映射 → 证据解释 → 执行 → 科研数据资产

后两门 `page: null`，永远 idle，因为 Store 从不写入 `integrationPlan` / `executionResult`。

SessionStore 预留了 `integrationPlan`、`executionPreview`、`executionResult`、`agentTask`，无写入路径。

---

## 5. 测试汇总

验收当日用仓库 `.venv`、`PYTHONPATH=.` 实跑，**禁止编造**。

### 5.1 `backend/tests/v30`

收集 75，通过 75，失败 0。

| 文件 | 收集数 |
|---|---:|
| `test_copilot.py` | 4 |
| `test_discovery_honesty.py` | 5 |
| `test_execution_bridge.py` | 6 |
| `test_figure_understanding.py` | 5 |
| `test_graph_constraints.py` | 7 |
| `test_integration_preview.py` | 5 |
| `test_memory_isolation.py` | 4 |
| `test_oncology_integrate_bridge.py` | 7 |
| `test_planner_gate.py` | 5 |
| `test_registry.py` | 4 |
| `test_router.py` | 6 |
| `test_schema_matcher_bridge.py` | 3 |
| `test_schema_pack.py` | 4 |
| `test_source_selection.py` | 5 |
| `test_v30_api.py` | 5 |
| **合计** | **75** |

### 5.2 `backend/tests/v31_frontend`

收集 31，通过 31，失败 0。

| 文件 | 收集数 |
|---|---:|
| `test_phase0_shell.py` | 8 |
| `test_phase1_copilot.py` | 5 |
| `test_phase2_timeline.py` | 5 |
| `test_phase3_sources_mapping.py` | 7 |
| `test_phase4_graph.py` | 6 |
| **合计** | **31** |

无 `test_phase5_preview_dataset.py`。

### 5.3 原始 234 回归

按 `archive/v31_baseline/REGRESSION.md` 固定文件集实跑：

**234 passed / 0 failed。**

（进度条 72 + 72 + 72 + 18 = 234。）

### 5.4 三套合计

| 套件 | 通过 | 失败 |
|---|---:|---:|
| v30 | 75 | 0 |
| v31_frontend | 31 | 0 |
| Phase 0 234 | 234 | 0 |
| **合计** | **340** | **0** |

说明：234 与 v30/v31 不重叠。仓库 `backend/tests` 另有 live integration、评测等文件，**未纳入本次三套合计**，也未当作本验收闸门。

---

## 6. 赛题匹配分析

方向：科学数据查找、解析与整合。

| 能力 | 评价 | 依据 |
|---|---|---|
| 1. 科研问题理解 | **中** | Router + Copilot 能分清概念问答与研究请求，能抽出对象/目标/约束。但是关键词规则，不是开放域理解。CONCEPT_QA 不写 goal，这是优点。 |
| 2. 数据源发现 | **中低** | 有 Registry 与 Discover API，界面诚实（unverified / not fetched）。**没有**真实目录检索。天文来源 `catalog_only`/`planned`。 |
| 3. 多源异构处理 | **中（医学强、通用弱）** | 旧内核有 GDC/GEO/cBioPortal/AACT/CIViC/DepMap Adapter 与 234 回归。v30 规划层不取数。非医学无执行插件。 |
| 4. 字段对齐 | **高** | Schema Pack + `SchemaMatcherV3`。医学绑定冻结 Canonical。映射出 AUTO/REVIEW，无行。 |
| 5. 来源追踪 | **高（合同层）** | 冻结字段要求 `source_id` / `raw_field` / `raw_value`。图节点带 source_key。执行后旧 EvidenceBuilder 仍在。v31 不展示主表证据格。 |
| 6. 图表理解 | **低** | 关键词分类，声明「未读取像素」。超新星可标 `digitization_possible` 但仍 `enters_primary_table=false`。 |
| 7. 数据清洗 | **中（旧链有、新 UI 无）** | Quality Gate / normalizers / 234 仍在。v30 execute 会带上 `quality_gate_report`。v31 看不到清洗过程。 |
| 8. 可追溯输出 | **中** | oncology 执行后可走旧 export。v31 无 Dataset/导出条。图理解明确不入库。 |
| 9. 错误修正能力 | **中低** | 旧 `/api/repair/run` 仍在主应用。v30 不封装修复环。前端不提供修正工作面。REVIEW 只解释、不改值。 |

**总评：** 赛题的「查找—解析—整合」在**医学旧内核**上是完整产品；V3.1 把「查找与解析的规划、诚实边界、跨域拒绝」做清楚了，但没有把通用查找和通用整合做实。

---

## 7. 当前限制

真实限制，不隐藏：

1. **非医学不能真实 Integrate。** astronomy / materials → 422 `only_oncology_integrate_supported`。
2. **Discovery 不发现。** 只投影 Registry 假说。
3. **v31 前端停在证据解释。** Preview / Dataset / Execute 页面不存在；左轨「执行」「科研数据资产」是空门。
4. **图理解不读图。** 无 OCR、无数字化、不进主表。
5. **会话与图不落盘。** Memory / Graph / SchemaPack 都在进程内存。
6. **Copilot 不是大模型。** 目标抽取与澄清选项写死。
7. **排除 METABRIC 与执行种子可能打架。** 选择层可按约束排除；executor 在 cBioPortal 路径仍写入 `brca_metabric`。
8. **Docker 前端镜像没有 v31。** 用 Nginx `:8888` 只能看到旧工作台。
9. **右轨 Memory 只在 Copilot 绘制。** Timeline / Sources / Mapping / Graph 会露出空 Memory 块。
10. **Why 抽屉对非 QualityFinding 会本地拼 `lastWhy`。** 不是 invent 数据行，但是 invent 了 why 信封。
11. **旧前端与新前端状态不共享。** 在 `/v31/` 规划完，不能自动出现在内核实验室任务表。
12. **live 外部服务测试不是本验收闸门。** 真实 cBioPortal/GEO 网络失败时，现场 execute 可能空表或超时。

---

## 8. 验收结论

| 问题 | 结论 |
|---|---|
| V3.1 规划链（到 Graph）是否可验收 | **是**。后端 + `/v31/` 六页 + 测试 340/340（本报告三套） |
| 执行与数据资产是否可验收为「前端完成」 | **否**。仅后端 API + 旧内核 |
| 是否可对外称已完成通用可信整合智能体 | **否**。应称：通用规划工作台，医学插件可执行 |
| 是否进入新功能开发 | **按你的指令停止。** 本验收只出报告 |
