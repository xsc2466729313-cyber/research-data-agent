# 评测与 SDTI（阶段 07）

## 边界

本阶段实现以下冻结指标：

```text
retrieval_precision / retrieval_recall / retrieval_f1
faithfulness / traceability
error_precision / error_recall / error_f1
repair_accuracy
sdti
```

公式的唯一来源是 `docs/06_评测指标与SDTI.md`，验收目标与安全门从
`configs/quality_rules.yaml` 读取。本阶段未修改冻结 Schema、医学规则或指标公式，
也不提前实现阶段 08 的 AI Gold Set 辅助和阶段 09 的 Repair 闭环。

## API

- `GET /api/evaluation/goldset/templates`：校验仓库内三个 CSV 模板的表头，并返回行数。
- `POST /api/evaluation/run`：运行未评测声明或经验证的 Gold Set 评测。
- `GET /api/evaluation/artifacts/<evaluation_id>/<metrics.json|report.md>`：下载评测产物。

在尚无真实 Gold Set 时，请求只需：

```json
{
  "evaluation_id": "local-not-evaluated-001"
}
```

返回的十个指标都是：

```json
{
  "value": null,
  "status": "NOT_EVALUATED"
}
```

评测结果会生成：

```text
data/output/evaluation/<evaluation_id>/metrics.json
data/output/evaluation/<evaluation_id>/report.md
```

同一 `evaluation_id` 不会覆盖已有报告；重复请求返回 `409 duplicate_evaluation`。

## Gold Set 门槛

正式计算必须同时满足：

1. Retrieval、Field 和 Error 三类 Gold Set 全部非空。
2. 每行 `review_status=approved`。
3. 初标者和独立复核者不同。
4. 已完成确定性规则、真实来源及高风险复核。
5. Gold Set 已冻结，且逐行内容与 `gold_set_checksum` 相符。
6. 系统观察与 Gold 行逐条一一对齐，不允许缺行、多行或重复 ID。

三个 CSV 模板位于 `goldset/templates/`。`GoldSetCsvLoader` 要求表头与模板完全一致，
支持 UTF-8 / UTF-8 BOM，并将空模板始终视为 `NOT_EVALUATED`。

## 指标数值与空分母

- Precision、Recall、F1、Faithfulness、Traceability 和 Repair Accuracy 使用 `0–1` 比例。
- SDTI 使用 `0–100` 分值。
- 任一公式分母为零时，该项为 `NOT_EVALUATED/null`，不自行定义为 0 或 1。
- SDTI 五个分量任一未评测时，SDTI 也为 `NOT_EVALUATED/null`。
- 有部分指标可计算、但未全部可计算时，总状态为 `PARTIALLY_EVALUATED`。

## 安全门

安全判定与 SDTI 分开：

- 虚假来源率 `> 1%` 或 Faithfulness `< 90%`：`FAIL`。
- Traceability `< 95%`、来源真实性未评测、关键字段缺 Evidence、高风险未解决或指标不完整：`REVIEW`，禁止自动发布。
- 只有指标完整且无红线/发布阻断时，才返回 `PASS` 和 `publish_allowed=true`。

## 测试

```powershell
python -m pytest backend/tests/test_evaluation_metrics.py
python -m pytest backend/tests/test_goldset.py
python -m pytest backend/tests/test_evaluation_service.py
python -m pytest backend/tests/test_evaluation_api.py
```

测试中的 `fixture-only-gold` 只用于验证公式和工程逻辑，不是真实 benchmark，
不得当作本系统的评测成绩。
