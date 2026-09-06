# V3.1 Phase 6-B1 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：ExecutionBridge（规划结果 → 旧执行请求预览）
- 未做：真实 Integrate、`ResearchAgentService.run`、Adapter 调用、数据下载、CSV、CanonicalRecord、Quality Gate、导出

本阶段只完成：把 v30 规划结果编译成旧执行系统可以理解的请求预览。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/integration/prepare`
- `backend/app/v30/models.py`：IntegrationPlan 增加 `selected_sources` / `field_mappings`；新增 `ExecutionRequestPreview`

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/agent/service.py`
- `backend/app/evidence/evidence_builder.py`
- Quality Gate / Quality V2
- Adapter / SchemaMatcher
- 旧执行流程任何函数体

---

## 2. 新增文件列表

```text
backend/app/v30/bridges/__init__.py
backend/app/v30/bridges/execution.py
backend/tests/v30/test_execution_bridge.py
PHASE6_STEP2_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/integration/prepare`

输入：`IntegrationPlan`（可由 `/api/v30/integration/preview` 直接回传）

输出：`ExecutionRequestPreview`

| 字段 | 说明 |
|---|---|
| `plan_id` | 沿用规划 ID |
| `contract_id` | 合同引用 |
| `schema_pack_id` | Schema Pack 引用 |
| `selected_sources` | 选中的来源键 |
| `tool_candidates` | 旧工具名，如 `search_geo` / `search_gdc` |
| `required_fields` | 需要对齐的字段 |
| `execution_ready` | 参数已编译完成 |
| `executed` | 恒为 `false` |

`fetched=false`，`integrated=false`，`generates_data=false`，`row_count=0`。

---

## 4. ExecutionBridge 设计

```text
IntegrationPlan
    → ExecutionBridge.prepare
    → ExecutionRequestPreview
```

Bridge 只读：

- IntegrationPlan
- Registry 的 `fetch_binding`
- SchemaPack 字段清单（用于补齐医学必填项）

不读患者原始数据。不实例化 Adapter。不调用旧 runner。

`execution_ready=true` 只表示请求字段齐了，不是允许取数。`executed=false` 表示这一步没有执行。

---

## 5. 与旧 ResearchAgentService 的关系

未来链路：

```text
ExecutionRequestPreview → ResearchAgentService → Adapter
```

本阶段关系：

- `tool_candidates` 使用 Registry 里已经登记的旧工具名（`search_geo`、`search_gdc` 等）
- 这是旧执行引擎认识的名字，但 **没有 import、没有实例化、没有 `.run()`**
- 旧 `backend/app/agent/service.py` 文件哈希不变

---

## 6. 测试结果

`backend/tests/v30`：**68 passed / 0 failed**

`test_execution_bridge.py`：

1. IntegrationPlan 可转为 ExecutionRequestPreview
2. `tool_candidates` 含 `search_geo` / `search_gdc`
3. `execution_ready=true`
4. `executed=false`
5. 不调用旧执行引擎
6. 不调用 Adapter
7. 不生成 CSV
8. 医学约束保留：`response_domain`、patient/sample、`forbid_cross_entity`、IHC 2+、AUC/IC50

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 7. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| `backend/app/agent/service.py` | 无 |
| EvidenceBuilder | 无 |
| Quality / Adapter | 无 |

---

## 8. 医学链路影响分析

**未影响。** Bridge 不进入旧执行、不取数、不写 CanonicalRecord、不跑 Quality Gate。HER2 约束只作为编译后的请求字段保留：`response_domain`、患者/样本分界、禁止跨研究 Join、IHC 2+ 不得自动 Positive、细胞系 AUC/IC50 不得当患者疗效。旧医学主链行为不变。

---

## 9. 下一步

真实 Integrate / `ResearchAgentService.run` / Adapter 执行属于后续阶段。本任务到此停止。
