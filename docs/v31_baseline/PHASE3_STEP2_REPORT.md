# V3.1 Phase 3-B 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Schema Pack 接入 SchemaMatcher（Bridge）
- 未做：Integrate、Adapter 执行、CSV 生成、Evidence Graph、Figure Understanding

Bridge 只更换 Matcher 的目标字段清单，不改匹配算法。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/schema-packs/match`
- `backend/app/v30/models.py`：增加 `SchemaMatchRequest` / `FieldMappingResult`

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/integration/schema_matcher_v2.py`
- `backend/app/integration/schema_matcher_v3.py`
- `backend/app/integration/schema_matcher_v2plus.py`
- Quality Gate / Adapter / `ResearchAgentService`
- 旧 `/api/v2/schema/match`

---

## 2. 新增文件列表

```text
backend/app/v30/matcher_bridge/__init__.py
backend/app/v30/matcher_bridge/service.py
backend/tests/v30/test_schema_matcher_bridge.py
docs/v31_baseline/PHASE3_STEP2_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/schema-packs/match`

输入：

```json
{
  "schema_pack_id": "oncology_canonical_v0.1",
  "source_fields": ["her2", "response_domain"]
}
```

输出 `FieldMappingResult`：

- `source_field`
- `target_field`
- `confidence`
- `status`（沿用 Matcher 的 AUTO / REVIEW / REJECT）
- `risk_level`（来自 SchemaPack）
- `row_count=0`，`generates_data=false`

医学：目标清单来自冻结 Canonical Schema。HER2 / response_domain / patient 边界仍由现有 Matcher 规则处理。

天文示例：`MJD→observation_time`，`band→band`，`mag→flux`，`redshift→redshift`，并保留 `source_id` / `raw_field` / `raw_value`。任务别名只作为 Matcher 构造参数传入，不改算法文件。

---

## 4. 测试结果

`backend/tests/v30`：**45 passed / 0 failed**

`test_schema_matcher_bridge.py`：

1. oncology pack 调用旧 `SchemaMatcherV3.match`，目标含冻结字段
2. astronomy pack 可生成上述映射
3. Matcher 源文件哈希不变
4. 不生成数据行
5. canonical schema 哈希不变

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 5. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| Matcher 核心文件 | 无 |
| Quality / Adapter | 无 |

---

## 6. 医学链路影响

**未影响。** 旧 `/api/v2/schema/match` 仍在。医学任务继续用冻结字段作目标。不取数，不写 CanonicalRecord，不进入 Integrate。

---

## 7. 下一步

Integrate / Adapter 执行属于后续阶段。本任务到此停止。
