# Gold Set

不要把单一 AI 模型的答案直接作为 Ground Truth。

建议流程：

1. 强模型 A 初标
2. 强模型 B 独立复核
3. 确定性规则检查
4. accession/URL/DOI 真实性验证
5. 高风险或模型分歧样本进入人工 review
6. 冻结版本号后用于 benchmark

模板位于 `templates/`。

## 正式入口 vs development

`templates/` 已由独立审核人 **xsc** 于 2026-08-29 写入 held-out 正式考卷
（来自 `goldset/breast_cancer/official_candidate/`，`gold_set_id=breast-cancer-official-candidate-20260829`）。
行数：retrieval 50 / field 26 / error 18。`frozen=false`，**不是** `frozen_test`。

对本卷已跑正式评测：`official-candidate-20260829T132222Z`，**SDTI = 63.36**，安全门 FAIL，`publish_allowed=false`。
产物在 `goldset/breast_cancer/official_candidate/evaluation_runs/`。重跑：`POST /api/evaluation/official-run` 或 `collect_official_sdti.py`。

`goldset/breast_cancer/development/` 是已审核的 development 分册（千问 LIVE 观察 SDTI 66.94），**不是正式入口**，其观察分不得填入正式栏。

详细接口与审核门槛见 `docs/EVALUATION_SDTI.md`。数据对照见 `docs/DATA_REPORT_20260829.md`。

## 阶段 07 使用方式

- `retrieval_gold.csv`：一行一个 question–dataset pair，`label` 使用
  `relevant/not_relevant`（加载器也接受 `1/0` 和 `true/false`）。
- `field_gold.csv`：一行一个关键原始字段与预期 Canonical 字段/值。
- `error_gold.csv`：同时放入应检出错误和 clean control，否则无法计算 Error Precision。
- 全部审核完成后将 `review_status` 设为 `approved`，然后冻结版本及 SHA-256。
- 高风险错误不得标记为允许自动修复，并必须记录人工复核者。

## 阶段 08 AI 辅助

`/api/goldset/*` 提供模型无关的初标、独立复核、来源验证、
确定性错误构造和 review queue。

这些接口只产生草案和可审计判定：

- 初标模型不能复核自己。
- 复核和 validator 都会重新验证官方来源。
- 分歧、低置信度、高风险医学字段和高风险错误进入人工队列。
- `freeze_eligible` 不等于已冻结，仍需版本化 manifest 和 checksum。

完整规则和接口见 `docs/GOLDSET_AI_CURATION.md`。
