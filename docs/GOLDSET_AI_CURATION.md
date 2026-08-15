# AI 辅助 Gold Set（阶段 08）

## 边界

本阶段实现：

```text
Retrieval Gold 初标草案
Field Gold 初标草案
Error case 确定性构造
独立第二模型复核接口
官方来源在线验证
确定性 Schema / 医学规则 validator
高风险、分歧和低置信度 review queue
```

该实现不绑定任何 LLM 供应商，也不会在后端伪造“强模型已审核”。
调用方必须显式提交初标模型 ID、第二模型 ID、标签、置信度与理由。
两个模型 ID 相同时，复核请求直接失败。

本阶段未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `configs/quality_rules.yaml`
- `docs/06_评测指标与SDTI.md` 中的任何公式

也不提前实现阶段 09 Repair 闭环。

## 接口流程

```text
POST /api/goldset/sources/verify
  ↓
POST /api/goldset/retrieval/initial-label
POST /api/goldset/fields/initial-label
POST /api/goldset/errors/construct
  ↓
POST /api/goldset/reviews/retrieval
POST /api/goldset/reviews/field
POST /api/goldset/reviews/error
  ↓
POST /api/goldset/validate
  ↓
approved proposal 或 open review_queue item
```

`initial-label` 接口接收模型候选标签，不是让客户端提交已冻结真值。
初标、复核和 validator 的输出都保留模型 ID、置信度、理由、来源验证 ID 和规则结果。

## 官方来源验证

支持的来源与格式由 `configs/goldset_rules.yaml` 控制：

- GDC / TCGA
- NCBI GEO
- cBioPortal
- AACT / ClinicalTrials.gov
- CIViC

验证器只访问对应来源的 HTTPS 官方域名，并且同时要求：

1. accession 符合该官方来源的格式。
2. URL 中包含该 accession。
3. 起始和重定向后的最终 URL 都保持在允许官方域名，不允许用户信息或非 HTTPS 端口。
4. 官方响应为 HTTP 2xx。
5. 官方响应内容中也包含该 accession。
6. 记录检查时间、最终 URL、HTTP 状态和有界响应摘要 SHA-256。

响应最多读取 1 MB，不会借 Gold Set 验证器下载大型数据文件。
复核和最终 validator 会再次访问官方来源，不信任客户端回传的
`status=verified`。

## 第二模型复核

第二模型必须独立给出：

- Retrieval：`relevant/not_relevant`。
- Field：Canonical field/value，并确认是否保留原始医学含义。
- Error：错误类型、应否检出、预期修复和是否允许自动修复。

任一模型置信度低于 `0.90`、标签分歧或来源未验证，都会进入 review queue。
客户端即使篡改 `agreement=true`，validator 也会按两份实际标签重新计算一致性。

## 确定性规则

Field validator 至少检查：

- Canonical field 是否存在，枚举值是否有效。
- `HER2 IHC 2+` 不得映射为 `Positive`。
- `ERBB2 CNA` 不得冒充 HER2 assay/status。
- AUC / IC50 / viability 必须使用 `preclinical_cell_line` response domain。
- 自动转换必须是确定性 gene/drug alias、大小写或 identity 规则。

`patient_id`、`sample_id`、HER2、response 等高风险字段即使双模型一致，
也会进入人工 review。

## Error case 构造

构造器只从调用方提供的、带真实 `source_id` 的原记录生成明确标记的扰动，
不会自行生成患者或医学事实。支持：

```text
duplicate
missing
gene_alias
drug_alias
schema_mapping_error
her2_assay_error
provenance_missing
patient_sample_conflict
```

每个 seed 还会产生一个未改动的 `clean_control`，用于 Error Precision 的假阳性评测。
只有 duplicate、gene alias 和 drug alias 可标记为低风险自动修复；
HER2 assay、来源缺失和 patient/sample 冲突必须人工 review。

validator 会重建并检查扰动前后差异，不会仅凭客户端声称
`error_type=duplicate` 就接受一条伪造错误。

## Review queue 与冻结

Review queue 项目包含：

```text
queue_id / kind / case_id / priority
reasons / source_id / required_action / status
```

`freeze_eligible=true` 只表示本批三类数据全部通过来源、双模型和规则门槛。
它不会自动生成冻结 Gold Set。正式 benchmark 前仍需要：

1. 完成队列中的人工裁决。
2. 导出并冻结三个 CSV。
3. 建立版本化 `GoldSetManifest` 和内容 checksum。
4. 通过阶段 07 评测器的所有前置检查。

仓库内的 `goldset/templates/*.csv` 仍然只有表头，因此当前仍无真实系统评测成绩。

## 测试

```powershell
python -m pytest backend/tests/test_goldset_source_verifier.py
python -m pytest backend/tests/test_goldset_curation.py
python -m pytest backend/tests/test_goldset_curation_api.py
```

可选的真实 GDC 来源验证：

```powershell
$env:RUN_GOLDSET_SOURCE_INTEGRATION = "1"
python -m pytest backend/tests/test_goldset_source_integration.py -ra
```

测试中的来源响应和 Gold 草案都明确属于 fixture，不是 benchmark 数据或系统成绩。
