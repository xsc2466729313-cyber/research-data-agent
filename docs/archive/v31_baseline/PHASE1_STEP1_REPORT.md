# V3.1 Phase 1 第一刀报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Research Copilot + Router + 最小 Session Memory
- 未做：Planner、Discovery、Registry、Schema Generator、Evidence Graph、Figure Understanding、自动取数、前端接线

本刀只增加科研助手交互入口。已有医学数据链（Research Planning → `ResearchAgentService` → Adapter → Schema → Evidence → Quality Gate → Export）未改行为。

---

## 1. 修改文件列表

本刀对已有代码的允许修改只有 `backend/app/main.py`，且只追加挂载：

```text
from backend.app.v30.api import mount_v30_routes
...
mount_v30_routes(app)
```

未改任何旧 handler 函数体，未改 `/api/agent/*`、`/api/research/*`、`/api/v3/*` 的既有路由定义。

说明：工作区里的 `backend/app/main.py` 在进入本刀之前已有未提交改动（Giiisp 配置、版本号、文献扫描错误码等）。那些改动不属于本刀，也不是本刀引入的医学链路变更。本刀新增内容仅上述两处挂载。

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `../../06_评测指标与SDTI.md`
- `backend/app/sources/**`
- SchemaMatcher 核心算法文件
- Quality Gate / Quality V2
- `backend/app/agent/service.py`（`ResearchAgentService`）

---

## 2. 新增文件列表

```text
backend/app/v30/__init__.py
backend/app/v30/models.py
backend/app/v30/api.py
backend/app/v30/runtime.py
backend/app/v30/router/__init__.py
backend/app/v30/router/rules.py
backend/app/v30/router/service.py
backend/app/v30/copilot/__init__.py
backend/app/v30/copilot/service.py
backend/app/v30/memory/__init__.py
backend/app/v30/memory/service.py
backend/app/v30/memory/store.py
configs/v30/router_rules.yaml
backend/tests/v30/__init__.py
backend/tests/v30/test_router.py
backend/tests/v30/test_copilot.py
backend/tests/v30/test_memory_isolation.py
backend/tests/v30/test_v30_api.py
PHASE1_STEP1_REPORT.md
```

未创建：`planner/`、`registry/`、`discovery/`、`schema_generator/`、`graph/`、`figures/`。

---

## 3. API 说明

新前缀：`/api/v30/*`。全部为旁路，不进入 Adapter，不调用 `ResearchAgentService`，不写 CanonicalRecord。

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/api/v30/sessions` | 创建空会话。记忆只有 `goal / clarifications / constraints`。 |
| `GET` | `/api/v30/sessions/{session_id}/memory` | 读取该会话最小记忆。 |
| `POST` | `/api/v30/route` | 只做路由：`CHAT` / `CONCEPT_QA` / `CLARIFY` / `PLAN`。 |
| `POST` | `/api/v30/copilot/turn` | Router → Copilot → Memory。返回理解结果与可见回复。 |

请求：

```json
{ "message": "我想研究HER2阳性乳腺癌耐药机制", "session_id": "可选" }
```

`POST /api/v30/copilot/turn` 响应关键字段：

- `route`
- `understood_goal`
- `suggested_data_needs`（`retrieval_status=not_retrieved`）
- `clarifying_questions`
- `ready_for_planner`
- `user_visible_reply`
- `blocked_reason`
- `memory`

路由样例：

| 输入 | 路由 |
|---|---|
| `你好` | `CHAT` |
| `什么是HER2` | `CONCEPT_QA` |
| `我想研究HER2阳性乳腺癌耐药机制` | `CLARIFY`，`domain=oncology` |

本刀不提供 `POST /api/v30/plan`。OpenAPI 中无该路径；误请求得到 404/405，不会生成方案。

Session Memory 只保存：

- `goal`（对象 / 目标 / 领域）
- `clarifications`（问答）
- `constraints`（用户约束）

不保存患者行、API Key、历史事实。模型 `extra=forbid`，写入这些字段会校验失败。

行为边界：

- `CHAT` / `CONCEPT_QA`：`ready_for_planner=false`，不写研究目标。
- 耐药机制第一轮会问“机制探索还是疗效预测”，`ready_for_planner=false`。
- 用户回答“疗效预测”后，同一 `session_id` 记录澄清，目标对象仍为 HER2 阳性乳腺癌。
- 建议数据需求只标方向，文案含“尚未检索”，不编造 GSE 或“已找到”。

---

## 4. 测试结果

解释器：仓库 `.venv`（Python 3.11.3，pytest 8.3.5）。工作目录为仓库根目录，`PYTHONPATH=.`。

### 本刀新测试

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/v30 -q
```

**19 passed / 0 failed**

| 文件 | 用例数 |
|---|---|
| `test_router.py` | 6 |
| `test_copilot.py` | 4 |
| `test_memory_isolation.py` | 4 |
| `test_v30_api.py` | 5 |

覆盖：问候/概念/研究/空输入路由、Copilot 不取数、第二轮澄清写入、会话隔离、拒绝患者行与密钥字段、旧 OpenAPI 仍在、`/plan` 未实现、v30 源码不导入医学主链。

### Phase 0 固定回归

按 `REGRESSION.md` 重跑 25 个文件。

**234 passed / 0 failed**

与 Phase 0 基线一致，不低于 234。未改旧测试期望。

未跑全仓库测试、integration、千问 LIVE。

---

## 5. git diff 检查

相对 HEAD `8e023e1ee2b37abf0f9b114ddf53661444d97f7c`：

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| `../../06_评测指标与SDTI.md` | 无 |
| `backend/app/sources/` | 无 |
| `backend/app/agent/service.py` | 无 |
| Quality Gate / Quality V2 逻辑文件 | 无 |
| SchemaMatcher 核心算法文件 | 无 |

本刀新增 diff 集中在 `backend/app/v30/`、`backend/tests/v30/`、`configs/v30/`。  
`backend/app/main.py` 中与本刀相关的只有 `mount_v30_routes` 导入与调用。

工作区另有进入本刀之前就存在的未提交文件（前端、文献规划、审计文档等）。它们不是本刀实现，报告不把它们算作 Phase 1 第一刀变更。

---

## 6. 是否影响医学旧链路

**否。**

依据：

1. 新代码只住在 `backend/app/v30/`，经 `/api/v30/*` 挂载。
2. v30 源码 AST 检查：不导入 `backend.app.sources`、`backend.app.agent.service`、Quality、SchemaMatcher，也不导入 Adapter / `ResearchAgentService`。
3. Copilot 不生成数据行，不检索数据集，不声明已找到具体 GSE。
4. Memory 不能容纳患者表或密钥。
5. 旧 OpenAPI 路径仍在：`/api/agent/tasks`、`/api/v3/research/clarify`。
6. `GET /health` 仍为 200。
7. Phase 0 固定回归仍为 234 passed。

因此：增加了一个科研助手澄清入口，医学旧链路保持原样。

---

## 下一刀（未开始）

Planner 门面属于 Phase 1 第二刀。本刀刻意不创建 `backend/app/v30/planner/`，也不挂 `/api/v30/plan`。
