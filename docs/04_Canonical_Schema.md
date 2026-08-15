# 04 Canonical Schema v0.1

冻结字段以 `configs/canonical_schema.yaml` 为准。

## 核心字段

### 标识
- study_id
- patient_id
- sample_id

### 疾病与临床
- disease
- subtype
- stage

### 生物标志物
- er_status
- pr_status
- her2_status
- her2_assay
- her2_raw_value

### 基因与变异
- gene
- variant
- mutation_status

### 治疗与响应
- drug
- treatment
- response_domain
- response_type
- response

### 证据
- source_id
- raw_field
- raw_value
- confidence

## response_domain

允许值：

- clinical
- preclinical_cell_line
- clinical_trial
- knowledge_evidence
