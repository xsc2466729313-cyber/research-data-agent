# AGENTS.md

本文件是项目导航与硬约束，不是百科全书。详细需求以 `docs/` 和 `configs/` 为准。

## 开始任务前

1. 阅读 `README_START_HERE.md`。
2. 阅读与当前任务相关的 `docs/` 文档。
3. 阅读 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml`。
4. 检查现有测试，再修改代码。

## 冻结规则

- `configs/canonical_schema.yaml` 为冻结接口。
- `configs/medical_rules.yaml` 为医学安全规则。
- `docs/06_评测指标与SDTI.md` 中公式不得自行改变。
- 如确需修改冻结内容，先创建 `CHANGE_REQUEST.md`，说明理由、影响、迁移和测试。

## 工程要求

- 所有外部数据必须记录 `source_id` 和真实来源。
- 标准化后必须保留 `raw_field` 与 `raw_value`。
- 所有关键模块必须有自动测试。
- 新增依赖必须说明必要性。
- 完成任务后运行相关测试，不得只验证 HTTP 200。
- 不得通过硬编码 benchmark 答案来通过测试。
- 不得生成虚假的系统成绩。

## 医学安全边界

- HER2 IHC 2+ 不得直接自动判为 HER2 Positive。
- ERBB2 CNA amplification 不等同 HER2 IHC positive。
- 低置信度患者/样本关联进入 unresolved/review。
- 高权威来源不可解释冲突不得自动选边。
- 细胞系 `AUC/IC50` 与患者 `pCR/response` 必须用 `response_domain` 区分。
