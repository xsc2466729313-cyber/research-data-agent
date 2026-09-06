# V3.1 Phase 3-A 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Dynamic Schema Pack Generator
- 未做：Matcher 接线、Integrate、Adapter 调用、CSV 生成、Evidence Graph、Figure Understanding

Schema Generator 只产出字段契约，不产出数据行。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/schema-packs/generate`、`GET /api/v30/schema-packs/{schema_pack_id}`
- `backend/app/v30/models.py`：增加 SchemaPack 模型

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- SchemaMatcher 核心算法
- Quality Gate / Quality V2
- Adapter / `ResearchAgentService`
- 旧测试

---

## 2. 新增文件列表

```text
configs/v30/schema_packs.yaml
backend/app/v30/schema_generator/__init__.py
backend/app/v30/schema_generator/service.py
backend/tests/v30/test_schema_pack.py
docs/v31_baseline/PHASE3_STEP1_REPORT.md
```

`schema_packs.yaml` 只是索引，指向冻结 `configs/canonical_schema.yaml`，不复制字段定义。

---

## 3. API 说明

`POST /api/v30/schema-packs/generate`

输入：domain、research_goal / topic、required_fields、selected_sources、contract_id。

输出 `SchemaPack`：

| 字段 | 含义 |
|---|---|
| `schema_pack_id` | 医学为 `oncology_canonical_v0.1`；通为 `task-*` |
| `domain` | 领域 |
| `entity_type` | 医学 `patient`；超新星 `supernova_observation` |
| `fields[]` | name / field_description / data_type / required / source_requirements / risk_level |
| `row_count` | 恒为 0 |
| `generates_data` | 恒为 false |

`GET /api/v30/schema-packs/{schema_pack_id}` 读取本次进程内已生成或已绑定的 pack。

### 案例 1：HER2 乳腺癌

绑定冻结 Canonical Schema，字段只读来自 `configs/canonical_schema.yaml`。含 `patient_id`、`her2_status`、`response_domain` 等，高风险字段 `risk_level=high`，`frozen=true`。

### 案例 2：Ia 型超新星

生成任务级 DRAFT pack，字段为：

`sn_id`、`observation_time`、`band`、`flux`、`redshift`、`source_id`、`raw_field`、`raw_value`

不含医学高风险字段名。

---

## 4. 测试结果

`backend/tests/v30`：**42 passed / 0 failed**

`test_schema_pack.py` 4 项：

1. oncology 绑定冻结 schema
2. astronomy 生成任务 schema
3. 不生成数据行
4. API 可往返；旧 `/api/v2/schema/match` 仍在；生成后 canonical 文件哈希不变

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 5. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| SchemaMatcher 核心文件 | 无 |
| Quality Gate | 无 |

---

## 6. 医学链路影响

**未影响。** 医学任务只读绑定冻结 schema，不改规则，不调用 Matcher，不取数，不写 CanonicalRecord。

---

## 7. 下一步

把 pack 目标清单交给现有 SchemaMatcher，以及 Integrate，属于后续刀。本任务到此停止。
