# V3.1 Phase 6-C1 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Oncology Real Integrate（ExecutionRequestPreview → 现有 ResearchAgentService 执行链）
- 未做：天文真实 Integrate、材料 Integrate、新 Adapter、v30 直接调用 Adapter

本阶段只完成：医学案例可以从 ExecutionRequestPreview 进入现有执行链，并由旧 Quality Gate / Evidence / Export 产出结果。

---

## 1. 修改文件列表

- `backend/app/v30/bridges/execution.py`：增加 `execute()`，委托 `OncologyIntegrator`
- `backend/app/v30/models.py`：`ExecutionRequestPreview` 增加 `domain` / `question`；新增 `ExecutionResult`
- `backend/app/v30/api.py`：增加 `POST /api/v30/integration/execute`
- `backend/app/main.py`：增加 `app.state.research_agent = research_agent_service`（仅注入 runner，不改服务内部）

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/agent/service.py`（`ResearchAgentService` 内部逻辑）
- Adapter（GDC / GEO / cBioPortal 等）
- DatasetBuilder
- Quality Gate / Quality V2
- EvidenceBuilder
- SchemaMatcher 核心算法

---

## 2. 新增文件列表

```text
backend/app/v30/integration/executor.py
backend/tests/v30/test_oncology_integrate_bridge.py
docs/v31_baseline/PHASE6_STEP3_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/integration/execute`

输入：`ExecutionRequestPreview`（可由 `/api/v30/integration/prepare` 回传）

输出：`ExecutionResult`

| 字段 | 说明 |
|---|---|
| `task_id` | 旧执行链任务 ID |
| `status` | 旧执行链状态 |
| `export_available` | 是否可走现有导出服务 |
| `quality_status` | 旧 Quality Gate 总体结论（`PASS` / `REVIEW` / `REJECT`） |
| `evidence_summary` | `source_id` / `raw_field` / `raw_value` / Evidence / 行数 / 医学边界字段是否保留 |
| `executed` | `true`（本阶段已进入旧执行链） |
| `domain` | 仅 `oncology` |
| `join_policy` | 医学案例固定 `forbid_cross_entity` |
| `export_formats` | 有行时含 `csv` / `xlsx` / `json`；始终含 `metadata` / `quality_report` |

错误码：

| HTTP | error | 含义 |
|---|---|---|
| 422 | `only_oncology_integrate_supported` | 天文 / 材料等非 oncology 被拒绝 |
| 422 | `execution_not_ready` | preview 未 ready |
| 503 | `old_runner_not_injected` | 未注入现有 runner |

---

## 4. 执行链路

```text
ExecutionRequestPreview
    → ExecutionBridge.execute()
    → OncologyIntegrator.execute()
    → runner.run(AgentTaskRequest)   # 注入的 ResearchAgentService
    → 已有 Adapter
    → DatasetBuilder
    → Schema
    → Evidence
    → Quality Gate
    → Export
    → ExecutionResult
```

约束：

- v30 **不** import `backend.app.agent.service`
- v30 **不** import `backend.app.sources*`
- v30 **不** 出现 `ResearchAgentService` / Adapter 类名
- runner 由 `app.state.research_agent` 注入
- `executor.py` 只 import `backend.app.agent.models.AgentTaskRequest`

非 oncology：在进入 `runner.run()` 之前拒绝，runner 不被调用。

cBioPortal 预览若选中 `search_cbioportal` / `cbioportal`，会写入 `focus_accessions=["brca_metabric"]`。这是旧引擎已有的 accession 种子规则，不是新 Adapter。

---

## 5. 与旧 ResearchAgentService 的关系

- 调用：`runner.run(AgentTaskRequest)`
- 不修改：`backend/app/agent/service.py` 任何函数体
- 不绕过：Adapter、DatasetBuilder、Quality Gate、Export
- `use_qwen=False`，`data_mode=live`，`iterative_collection=False`
- 医学约束仍由旧链执行：`response_domain`、patient/sample 分界、`forbid_cross_entity`

---

## 6. 测试结果

`backend/tests/v30`：**75 passed / 0 failed**

`test_oncology_integrate_bridge.py`：

1. HER2 案例可以进入真实执行（`executed=true`，有 `task_id`）
2. ExecutionBridge 调用旧执行链（`service.run` 被调用；executor 不 import Adapter / `ResearchAgentService`）
3. Adapter 正常返回（`search_cbioportal` status=`完成`，有建模行）
4. Quality Gate 仍生效（`overall` ∈ `PASS/REVIEW/REJECT`）
5. Evidence 仍生成（`source_id` / Evidence 摘要为真）
6. 导出文件可生成（metadata / quality_report；有行时 CSV）
7. 天文 preview 被 422 拒绝，不进入 runner
8. 冻结文件哈希在执行前后不变

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 7. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| `backend/app/agent/service.py` | 无 |
| EvidenceBuilder | 无 |
| Quality Gate / Quality V2 | 无 |
| Adapter | 无 |
| `backend/app/main.py` | 仅增加 `app.state.research_agent` 注入 |

---

## 8. 医学链路影响分析

**旧医学主链行为不变。** v30 只转调现有 `ResearchAgentService.run()`，不改 Adapter、Quality Gate、canonical_schema、medical_rules。

本阶段仍强制保留：

- `source_id` / `raw_field` / `raw_value` / Evidence
- `response_domain`（细胞系 AUC/IC50 ≠ 患者 pCR）
- `patient_id` / `sample_id` 分界
- `forbid_cross_entity`（禁止跨研究患者 Join）
- HER2 IHC 2+ 不得自动 Positive（由未改动的 medical_rules / Quality Gate 继续执行）

天文 / 材料不会进入这条医学执行链。

---

## 9. 下一步

天文真实 Integrate、材料 Integrate、新 Adapter 不属于本阶段。本任务到此停止。
