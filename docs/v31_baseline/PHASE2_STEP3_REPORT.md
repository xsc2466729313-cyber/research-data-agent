# V3.1 Phase 2-B2 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Source Selection / SourceBroker 组合连接层
- 未做：Integrate、Adapter 调用、Schema Generator、Evidence Graph、Figure Understanding、自动取数

本刀把 Discovery 候选变成 `SelectedSourcePlan`。只排序、筛选和解释，不取数。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/source-selection`
- `backend/app/v30/models.py`：增加选择请求 / `SelectedSourcePlan`

未修改：

- `backend/app/source_broker/**`
- `backend/app/sources/**`
- `backend/app/agent/service.py`
- SchemaMatcher / Quality Gate / Quality V2
- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- 任何旧测试

---

## 2. 新增文件列表

```text
backend/app/v30/source_selection/__init__.py
backend/app/v30/source_selection/service.py
backend/tests/v30/test_source_selection.py
docs/v31_baseline/PHASE2_STEP3_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/source-selection`

输入：

```json
{
  "candidates": [],
  "contract": {
    "research_goal": "HER2阳性乳腺癌耐药疗效预测",
    "required_fields": ["gene_expression"],
    "domain": "oncology",
    "response_domain": "clinical"
  },
  "constraints": { "exclude": ["METABRIC"] }
}
```

`constraints` 也接受字符串列表，例如 `["不要METABRIC"]`。

输出 `SelectedSourcePlan`：

- `selected_candidates`：入选及原因
- `rejected_candidates`：拒绝及原因（`user_constraint` / `planned_source` / `not_in_cover`）
- `coverage_summary`：假说覆盖，`runtime_verified=false`
- `selection_reason`
- `join_risk`：禁止患者级 Join
- `fetched=false`，`integrated=false`

catalog_only / planned 不会被改成 `verified`。`response_domain` 原样传出。

---

## 4. Source Selection 如何调用旧 SourceBroker

不调用 `SourceBroker.plan()`，避免走种子目录再发现、避免被当成已取数。

Bridge 只转调现有对象上的算法：

```text
DiscoveryCandidate
  → 用户约束过滤（排除 METABRIC 等）
  → planned 直接拒绝
  → 按 Registry 模态生成 field_hints（假说，不是覆盖证明）
  → SourceBroker.matcher.build_matrix(...)
  → SourceBroker.selector.select(...)
  → 映射为 SelectedSourcePlan
```

集合覆盖算法仍在 `backend/app/source_broker/source_selector.py`，v30 不复制。

---

## 5. 测试结果

`backend/tests/v30`：**38 passed / 0 failed**

`test_source_selection.py` 5 项：

1. Discovery 候选可排序，表达类缺口优先 GEO/GDC
2. 排除 METABRIC → `rejected_candidates.reason_code=user_constraint`
3. catalog_only 不能变成 verified
4. 不调用 Adapter / `ResearchAgentService` / `SourceBroker.plan`
5. 旧 `/api/agent/tasks`、`/api/v3/research/clarify` 仍在

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 6. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `backend/app/source_broker/**` | 无 |
| `backend/app/sources/**` | 无 |
| `backend/app/agent/service.py` | 无 |
| 冻结 configs | 无 |
| 旧测试 | 无 |

---

## 7. 医学链路影响分析

**未影响。** 不下载数据，不写 CanonicalRecord，不生成 CSV，不进入 `ResearchAgentService`。不自动患者级 Join，不改 `response_domain`，不把候选当成真实数据。

---

## 8. 是否满足进入下一阶段

**工程条件满足，但本任务到此停止。**

已具备：Registry → Discovery 候选 → Source Selection 计划。下一阶段才是 Integrate / Adapter 执行或 Phase 3 Schema Generator。本刀没有开始这些工作。
