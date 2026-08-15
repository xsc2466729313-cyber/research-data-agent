# 标准化与融合（阶段 06）

## 边界

端点：`POST /api/integration/normalize`

输入：

```text
task_id
+ SourceItem[]
+ RawSourceRecord[]
+ FieldMapping[]
+ PatientSampleLinkCandidate[]（可选）
```

输出：

```text
CanonicalRecord[]（逐原始字段的原子记录）
+ EvidenceCell[]（逐标准化字段）
+ LinkDecision[]
+ FieldConflict[]
+ MergedRecord[]（非破坏性融合视图）
+ MappingIssue[] / blocked_record_ids
```

本阶段不修改冻结的 `configs/canonical_schema.yaml`，不发布最终数据集，不计算评测分数，也不执行 Gold Set、Repair 或前端完善阶段。

## 为什么采用原子 CanonicalRecord

冻结 Canonical Schema 每条记录只有一组 `raw_field/raw_value/source_id/confidence`。如果直接把多个来源和多个原始字段压成一条 CanonicalRecord，会丢失字段级来源关系。

因此实现遵循：

```text
一个原始字段
→ 一条原子 CanonicalRecord
→ 一个或多个 EvidenceCell
```

例如 `HER2_IHC = 2+` 会生成一条原子 CanonicalRecord，其中保留：

```text
her2_status = Equivocal
her2_assay = IHC
her2_raw_value = 2+
raw_field = HER2_IHC
raw_value = 2+
source_id = 原始来源
```

对应的 `her2_status`、`her2_assay`、`her2_raw_value` 各有独立 EvidenceCell。融合结果存入单独的 `MergedRecord`，不会覆盖或删除原子记录。

## 实现模块

```text
backend/app/normalization/gene_normalizer.py
backend/app/normalization/drug_normalizer.py
backend/app/normalization/biomarker_normalizer.py
backend/app/normalization/schema_mapper.py
backend/app/integration/patient_sample_linker.py
backend/app/integration/merge_engine.py
backend/app/integration/conflict_detector.py
backend/app/evidence/evidence_builder.py
```

### GeneNormalizer

- 大小写标准化。
- 只使用内置、版本化的确定性别名，例如 `HER2/HER-2/ERBB-2 → ERBB2`。
- 不符合受支持 symbol 语法的自由文本进入 `unresolved`。

### DrugNormalizer

- 只执行确定性别名，例如 `Herceptin → Trastuzumab`、`Piqray → Alpelisib`。
- 未知名称保留原值，不猜测药物实体。
- `A + B` 等组合文本保留并进入 `review`，避免把组合方案伪装成单药。

### BiomarkerNormalizer

- `HER2 IHC 0/1+ → Negative`
- `HER2 IHC 2+ → Equivocal`
- `HER2 IHC 3+ → Positive`
- FISH/ISH/CISH/SISH 只对明确的 `amplified/non-amplified/positive/negative/equivocal` 术语映射。
- 数字 FISH ratio 不自行应用未知实验室阈值。
- ER/PR 百分比不自行应用未知方案阈值。
- `ERBB2 CNA amplification` 只生成 `gene=ERBB2, variant=Amplification`，绝不生成 HER2 IHC status。

### SchemaMapper

- `FieldMapping.canonical_field` 必须存在于冻结 CanonicalRecord。
- provenance 字段由系统生成，用户不能通过 mapping 覆盖。
- 高风险字段强制使用专用 normalizer，不能用 passthrough 绕过医学规则。
- 支持 `source_id` 限定的 source-specific mapping。
- 每条原始记录必须能映射 `study_id` 和 `disease`；缺失时整条记录进入 `blocked_record_ids`，不补造。
- CanonicalRecord 的 `raw_value` 按冻结 string 类型确定性表示；MappedCanonicalRecord 和 EvidenceCell 另保留原始数据类型和值。

## response_domain 安全规则

允许域完全沿用冻结 Schema：

```text
clinical
preclinical_cell_line
clinical_trial
knowledge_evidence
```

`response` 必须有显式 domain。`AUC`、`IC50`、`viability` 只能映射到 `preclinical_cell_line`；如果试图放入 `clinical` 或其他域，该 response 字段被阻断并生成 `unsafe_response_domain` issue。

冲突和融合的语义键包含 `response_domain + response_type`，所以细胞系 AUC 与患者 pCR 不会互相覆盖或产生伪冲突。

## 患者与样本关联

自动关联阈值固定为 `0.90`：

- 同 study 且 sample ID 完全相同：可自动合并。
- 同 study、patient ID 相同且两边都是 patient-level：可自动合并。
- patient ID 相同但 sample 不同或一边有 sample：只登记 `linked_patient_only`，样本记录不合并。
- 候选关联置信度 `< 0.90`：`unresolved`，禁止自动合并。
- 明确 patient/sample ID 冲突：`rejected`。
- 跨 study 候选：不自动合并。

## 冲突检测与融合

冲突按语义维度检测：

```text
HER2 status     → assay
response        → response_domain + response_type
variant/status  → gene + variant
drug            → drug identity
```

因此 IHC 2+ 与 FISH amplified 作为不同 assay 观察保留，不会错误互相覆盖；同一 IHC 维度的 `Equivocal` 与 `Positive` 才构成冲突。

所有冲突均保留多个 observed value 和 Evidence ID，`selected_value = null`、状态为 `unresolved`。当至少两个不同高权威来源支持不同值时，额外标记 `high_authority_conflict=true`，禁止自动选边。

## Evidence

Evidence ID 由以下内容确定性计算：

```text
mapped_record_id + canonical field + canonical value
```

每个 EvidenceCell 保留：

- canonical field/value
- 原始 field/value（包括原始数据类型）
- source_id
- normalization_method
- confidence
- `verified/review` 状态

所有 MergedField 必须引用已生成的 Evidence ID；出现悬空引用时流水线直接失败。

## 请求示例

```json
{
  "task_id": "task_norm_001",
  "source_items": [
    {
      "source_id": "source:study-1",
      "task_id": "task_norm_001",
      "source_name": "Registered source",
      "source_type": "database",
      "accession": "STUDY-1",
      "url": "https://example.org/study-1",
      "status": "retrieved"
    }
  ],
  "records": [
    {
      "record_id": "raw-1",
      "source_id": "source:study-1",
      "source_authority": "high",
      "fields": {
        "study": "STUDY-1",
        "patient": "P001",
        "sample": "S001",
        "disease": "Breast Cancer",
        "HER2_IHC": "2+"
      },
      "default_confidence": 1.0
    }
  ],
  "mappings": [
    {
      "mapping_id": "study",
      "raw_field": "study",
      "canonical_field": "study_id",
      "normalizer": "passthrough",
      "confidence": 1.0
    },
    {
      "mapping_id": "disease",
      "raw_field": "disease",
      "canonical_field": "disease",
      "normalizer": "passthrough",
      "confidence": 1.0
    },
    {
      "mapping_id": "her2-ihc",
      "raw_field": "HER2_IHC",
      "canonical_field": "her2_status",
      "normalizer": "biomarker",
      "confidence": 1.0
    }
  ],
  "link_candidates": []
}
```

示例中的 `example.org` 只是请求结构占位符。真实运行必须使用已登记的真实 SourceItem；未登记 source_id 返回 `unregistered_source`。

## 测试

```powershell
python -m pytest backend/tests/test_normalizers.py
python -m pytest backend/tests/test_integration_pipeline.py
python -m pytest backend/tests/test_integration_api.py
```

测试覆盖：HER2 高风险规则、ERBB2 CNA 隔离、数字阈值不猜测、别名标准化、原始值与类型保留、response domain 阻断、低置信度关联、跨样本不合并、高权威冲突、Evidence 完整性、来源登记和 API 错误结构。
