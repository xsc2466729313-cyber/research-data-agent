# Codex 任务 07：评测与 SDTI

实现：
- retrieval_precision
- retrieval_recall
- retrieval_f1
- faithfulness
- traceability
- error_precision
- error_recall
- error_f1
- repair_accuracy
- sdti

指标公式以 `docs/06_评测指标与SDTI.md` 为唯一来源。

要求：
- 支持 Gold Set 模板。
- 生成 `metrics.json` 和可读报告。
- 未有真实 Gold Set 时不得伪造高分。
