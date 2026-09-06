# V3.1 Phase 0 医学回归入口

- 盘点日期：2026-09-05
- 原则：只记录如何运行现有测试，不修改任何测试文件
- 解释器：仓库 `.venv`（Python 3.11.3，pytest 8.3.5）
- 工作目录：仓库根目录
- 环境：`$env:PYTHONPATH="."`

## 如何运行（整包，可选）

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

`pyproject.toml` 已设置 `testpaths = ["backend/tests"]` 与 `pythonpath = ["."]`。  
带 `@pytest.mark.integration` 的用例会访问真实外部服务，Phase 0 默认不把它们当作合并闸门。

## Phase 0 固定回归集（本阶段已执行）

下列文件覆盖规划、主 Agent、Adapter 单测、Schema、Quality、Parser、Evaluation 加载。不含 live integration。

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m pytest `
  backend/tests/test_research_planning.py `
  backend/tests/test_research_planning_v2.py `
  backend/tests/test_requirement_agent.py `
  backend/tests/test_v3_api.py `
  backend/tests/test_research_agent.py `
  backend/tests/test_closed_loop.py `
  backend/tests/test_goal_loop.py `
  backend/tests/test_quality_gate.py `
  backend/tests/test_quality_agent.py `
  backend/tests/test_quality_v2.py `
  backend/tests/test_schema_entity_v2.py `
  backend/tests/test_schema_matcher_v3.py `
  backend/tests/test_v2plus_matchers.py `
  backend/tests/test_normalizers.py `
  backend/tests/test_integration_pipeline.py `
  backend/tests/test_parsers.py `
  backend/tests/test_official_evaluation.py `
  backend/tests/test_goldset.py `
  backend/tests/test_gdc_adapter.py `
  backend/tests/test_geo_adapter.py `
  backend/tests/test_cbioportal_adapter.py `
  backend/tests/test_aact_adapter.py `
  backend/tests/test_civic_adapter.py `
  backend/tests/test_depmap_adapter.py `
  backend/tests/test_models.py `
  --tb=no
```

## 测试入口分类

### 规划测试

- `backend/tests/test_research_planning.py`
- `backend/tests/test_research_planning_v2.py`
- `backend/tests/test_requirement_agent.py`
- `backend/tests/test_v3_api.py`
- `backend/tests/test_research_brief.py`（未纳入本次固定集）
- `backend/tests/test_planning_rag.py`（未纳入本次固定集）

### Agent 测试

- `backend/tests/test_research_agent.py`
- `backend/tests/test_closed_loop.py`
- `backend/tests/test_goal_loop.py`
- `backend/tests/test_orchestrator_research_agent.py`（未纳入本次固定集）
- `backend/tests/test_study_design.py`（未纳入本次固定集）

### Adapter 测试

单测（本次固定集）：

- `test_gdc_adapter.py`
- `test_geo_adapter.py`
- `test_cbioportal_adapter.py`
- `test_aact_adapter.py`
- `test_civic_adapter.py`
- `test_depmap_adapter.py`

Live / API / integration（本次未跑，需网络与外部服务）：

- `test_gdc_integration.py`、`test_geo_integration.py`、`test_cbioportal_integration.py`
- `test_aact_integration.py`、`test_civic_integration.py`
- `test_*_api.py` 中访问真实端点的用例

### Schema 测试

- `test_schema_entity_v2.py`
- `test_schema_matcher_v3.py`
- `test_v2plus_matchers.py`
- `test_entity_matcher_v3.py`（未纳入本次固定集）
- `test_normalizers.py`
- `test_integration_pipeline.py`
- `test_models.py`（含 CanonicalRecord 与冻结字段对齐）

### Quality 测试

- `test_quality_gate.py`
- `test_quality_agent.py`
- `test_quality_v2.py`
- `test_critic.py`（未纳入本次固定集）
- `test_repair_loop.py`（未纳入本次固定集）

### Parser 测试

- `test_parsers.py`

### Evaluation 测试

- `test_official_evaluation.py`
- `test_goldset.py`
- `test_evaluation_api.py`、`test_evaluation_service.py`、`test_evaluation_metrics.py`（未纳入本次固定集）

## 每次后续 Phase 合并前

1. 重跑上方固定回归集。
2. 通过数不得低于 Phase 0 记录（见 `PHASE0_REPORT.md`）：**234 passed / 0 failed**。
3. 不得为让新功能通过而改旧测试期望。
4. 冻结文件 `git diff` 必须为空。

## 前端语法检查（可选，非本阶段闸门）

```powershell
node --check frontend\app.js
```

Phase 0 未把该命令作为医学回归闸门，也未改前端。
