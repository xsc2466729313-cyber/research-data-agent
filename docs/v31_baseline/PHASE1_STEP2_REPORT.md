# V3.1 Phase 1 第二刀报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Planner 门面（`POST /api/v30/plan`）
- 前序：Phase 0 基线；Phase 1 Step 1 Router / Copilot / Memory
- 未做：Discovery、Registry、Schema Generator、Evidence Graph、Figure Understanding、自动取数、前端接线

本刀只增加规划入口。它把 Copilot 已澄清的 Session Memory 编译成现有规划服务的 topic，再转调已有 `RequirementAgent` / `ResearchPlanningService` / `ResearchPlanningV2`。不是新的科研规划系统。

---

## 1. 修改文件列表

本刀修改的已有 v30 文件：

- `backend/app/v30/api.py`：挂载 `POST /api/v30/plan`
- `backend/app/v30/models.py`：增加 `PlanRequest` / `PlanResponse`
- `backend/app/v30/runtime.py`：增加 `plan()` 转调门面
- `backend/app/v30/copilot/service.py`：与 Planner 共用 `is_ready_for_planner`
- `backend/tests/v30/test_v30_api.py`：OpenAPI 现包含 `/api/v30/plan`；未 ready 返回 422

`backend/app/main.py` 本刀未再改。Step 1 已挂载 `mount_v30_routes(app)`，新路由写在 v30 API 内部。

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `docs/06_评测指标与SDTI.md`
- `backend/app/sources/**`
- SchemaMatcher 核心算法
- Quality Gate / Quality V2
- `backend/app/agent/service.py`（`ResearchAgentService`）
- RequirementAgent / Research Planning 内部实现

---

## 2. 新增文件列表

```text
backend/app/v30/planner/__init__.py
backend/app/v30/planner/ready.py
backend/app/v30/planner/service.py
backend/tests/v30/test_planner_gate.py
docs/v31_baseline/PHASE1_STEP2_REPORT.md
```

未创建：`registry/`、`discovery/`、`schema_generator/`、`graph/`、`figures/`。

---

## 3. API 说明

`POST /api/v30/plan`

输入：

```json
{ "session_id": "xxx" }
```

服务读取该会话 Memory，必须看到 `goal` / `clarifications` / `constraints`。

闸门：

- `ready_for_planner != true` → HTTP 422
- 响应体：`{"error": "research_goal_not_ready"}`
- 禁止猜测用户目标

| 场景 | 结果 |
|---|---|
| `你好` → CHAT，再 plan | 422 |
| `我想研究HER2阳性乳腺癌耐药机制` 第一轮（ready=false） | 422 |
| 回答 `疗效预测` 后（ready=true） | 200，转调已有规划服务 |
| 未知 session | 404 |

成功响应关键字段：

- `compiled_from_session`
- `topic`（由 Memory 编译，不手写 HER2/response/patient 字段）
- `used_existing_services`
- `contract`：已有 `FrozenResearchContract`（本刀不自动 freeze）
- `planning_v2`：V2 规划摘要
- `memory`

旧接口不变：`POST /api/v3/research/clarify` 仍可直接调用。

---

## 4. Planner 如何调用旧服务

肿瘤路径（`goal.domain == oncology`）：

```text
Session Memory
  → is_ready_for_planner（有对象、有目标、澄清已答）
  → compile_topic（对象 + 目标 + 澄清答案 + 约束）
  → RequirementAgentService.clarify(ClarifyRequest(topic=...))
        内部使用 ResearchPlanningService.create_topic / scan_literature / question_candidates
  → ResearchPlanningService.question_candidates(topic_id)   # 显式再读一次规划结果
  → RequirementAgentService.create_contract(...)            # 得到 FrozenResearchContract
  → ResearchPlanningV2Service.plan(ResearchPlanningV2Request)
```

门面不创建 HER2 / response / patient 字段。这些字段若出现，来自已有 `FrozenContractBuilder` 与规划规则。

本刀不调用 Adapter，不调用 `ResearchAgentService`，不写 CanonicalRecord，不进入 integrate，不自动 freeze。

非肿瘤领域：不冒充已冻结医学合同，只返回“方案草稿，仍需确认领域”。

---

## 5. 测试结果

解释器：仓库 `.venv`（Python 3.11.3，pytest 8.3.5）。`PYTHONPATH=.`。

### 本刀与旁路测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/v30 -q
```

**24 passed / 0 failed**

其中 `test_planner_gate.py` 5 项：

1. CHAT session 调用 plan → 422
2. 研究问题第一轮 ready=false → 422
3. 澄清后 ready=true → 成功转调已有规划，返回 `FrozenResearchContract`
4. Planner 源码不导入 Adapter / `ResearchAgentService`；成功路径中 `ResearchAgentService.run` 被拦截也不会被调用
5. `POST /api/v3/research/clarify` 仍 200

### Phase 0 固定回归

**234 passed / 0 failed**，与 Phase 0 基线一致。未改旧测试期望。

---

## 6. git diff 检查

相对 HEAD `8e023e1ee2b37abf0f9b114ddf53661444d97f7c`：

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| `docs/06_评测指标与SDTI.md` | 无 |
| `backend/app/sources/` | 无 |
| `backend/app/agent/service.py` | 无 |
| Quality Gate / Quality V2 | 无 |
| SchemaMatcher 核心算法 | 无 |

本刀变更集中在 `backend/app/v30/` 与 `backend/tests/v30/`。

---

## 7. 医学链路影响分析

**未影响医学旧链路。**

1. 新代码仍只住在 `backend/app/v30/`，经 `/api/v30/plan` 旁路挂载。
2. 规划能力来自已有 RequirementAgent / ResearchPlanning / V2，没有复制合同规则。
3. 肿瘤合同继续带已有禁止项（例如不得把 HER2 IHC 2+ 自动判为 Positive）。
4. 不取数、不写 CanonicalRecord、不跑 Quality Gate、不改 Adapter。
5. 旧 OpenAPI 路径 `/api/v3/research/clarify`、`/api/agent/tasks` 仍在。
6. Phase 0 回归仍为 234 passed。

---

## 8. 下一阶段是否可以进入 Phase 2

**可以进入，但本任务到此停止，没有开始 Phase 2。**

进入条件已满足：

- Phase 1 两刀完成：Router、Copilot、Memory、Planner 门面
- 冻结文件无 diff
- 医学回归不低于 Phase 0 基线
- `/plan` 有 ready 闸门，不会在闲聊或未澄清时抢跑

Phase 2 才是 Universal Source Registry + Discovery。按任务要求，不实现 Registry、Discovery、Schema Generator、Evidence Graph、Figure Understanding。
