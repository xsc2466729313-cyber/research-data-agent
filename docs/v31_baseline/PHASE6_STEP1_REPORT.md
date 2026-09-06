# V3.1 Phase 6-A 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Integration Preview Plan
- 未做：真实 Integrate、Adapter 调用、数据下载、CSV 生成、CanonicalRecord、Quality Gate、`ResearchAgentService.run`

这是执行前规划层，不是实际数据执行。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/integration/preview`
- `backend/app/v30/models.py`：增加 `IntegrationPreviewRequest` / `IntegrationPlan`
- `backend/app/v30/registry/service.py`：增加只读 `get(source_key)`，不取数

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/evidence/evidence_builder.py`
- Quality Gate / Quality V2
- Adapter / `ResearchAgentService`
- SchemaMatcher 核心算法

---

## 2. 新增文件列表

```text
backend/app/v30/integration/__init__.py
backend/app/v30/integration/service.py
backend/tests/v30/test_integration_preview.py
docs/v31_baseline/PHASE6_STEP1_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/integration/preview`

输入：

```json
{
  "selected_sources": ["geo", "gdc"],
  "schema_pack_id": "oncology_canonical_v0.1",
  "field_mappings": [
    {
      "source_field": "her2",
      "target_field": "her2_status",
      "confidence": 0.62,
      "status": "REVIEW",
      "risk_level": "high"
    }
  ],
  "contract_id": "contract-her2-demo"
}
```

`selected_sources` 也可传带 `source_key` 的对象列表。

输出 `IntegrationPlan`：

| 字段 | 说明 |
|---|---|
| `plan_id` | 预览计划 ID |
| `sources` | 选中的来源键 |
| `adapter_candidates` | 若执行将调用的现有工具名（`search_geo` 等），`would_invoke=false` |
| `schema_pack_id` | 绑定的 Schema Pack |
| `field_requirements` | 预计需要对齐的字段 |
| `expected_outputs` | 预计产出，均标明未生成 |
| `join_policy` | 医学患者任务为 `forbid_cross_entity` |
| `execution_allowed` | 恒为 `false` |

`fetched=false`，`integrated=false`，`generates_data=false`，`row_count=0`。

---

## 4. 设计说明

Preview 只读 Registry 的 `fetch_binding` 与 Schema Pack 字段清单，把“如果执行”写成计划：

- 需要调用哪些现有工具
- 需要哪些字段
- 预计输出什么（表 / CanonicalRecord / Quality 报告 / CSV）

当前全部标记为未执行、未生成。没有下载、没有 Adapter 实例、没有写文件。

---

## 5. 医学约束

HER2 / oncology 任务：

- `field_requirements` 必须含 `response_domain`、`patient_id`、`sample_id`
- `join_policy=forbid_cross_entity`，禁止跨研究患者 Join
- 约束声明 HER2 IHC 2+ 不得自动 Positive，细胞系 AUC/IC50 不得当作患者 pCR
- 本阶段不跑 Quality Gate，只把规则写进计划

---

## 6. 测试结果

`backend/tests/v30`：**62 passed / 0 failed**

`test_integration_preview.py`：

1. 可以生成执行计划
2. 不调用 Adapter
3. `execution_allowed=false`
4. 不生成 CSV
5. 医学约束保留（`response_domain`、患者/样本分界、禁止跨研究 Join）

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 7. 医学链路影响

**未影响。** Preview 不进入 `ResearchAgentService.run`，不取数，不写 CanonicalRecord，不跑 Quality Gate。旧 Adapter / Evidence / 导出路径不变。

---

## 8. 下一步

真实 Integrate / Adapter 执行属于后续阶段。本任务到此停止。
