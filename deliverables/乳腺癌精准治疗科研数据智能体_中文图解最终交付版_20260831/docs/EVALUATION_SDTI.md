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

## v2 统一评价扩展层

新增的统一评价体系见 `docs/UNIFIED_EVALUATION_SYSTEM_V2.md` 与
`configs/evaluation_system_v2.yaml`。v2 不改变本文件实现的冻结 SDTI 指标，
而是在其外层增设：

- 外部 Benchmark 横向比较：Cleaning、Retrieval、Schema Matching、Entity Matching。
- 模型/系统变体对比：`rule_keyword`、`qwen_only`、`single_source_agent`、
  `multi_source_no_gate`、`full_agent`。
- 横向结果表：统一长表模板为 `data/evaluation_templates/unified_results_template.csv`。
- 分层对比：按 benchmark、科研任务类型、乳腺癌亚型、来源类型、`response_domain`、
  Evidence 等级、患者/样本关联置信度、错误类型和风险等级切分。
- Task-Adaptive Fitness：先冻结 Evaluation Contract，再评价科研适用性。

这些扩展结果不得替代真实 Gold Set SDTI，也不得在未真实运行时填入推测成绩。

## API

- `GET /api/evaluation/goldset/templates`：校验仓库内三个 CSV 模板的表头，并返回行数。
- `POST /api/evaluation/run`：运行未评测声明或经验证的 Gold Set 评测。
- `POST /api/evaluation/official-run`：对本套 `goldset/templates/`（held-out official_candidate）采集系统观察并计算 SDTI。默认执行千问 + LIVE Adapter，禁止静默确定性兜底；CLI：`python goldset/breast_cancer/official_candidate/collect_official_sdti.py`。
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
支持 UTF-8 / UTF-8 BOM。空模板视为 `NOT_EVALUATED`；模板已有行但缺少系统观察时，
看板正式 SDTI 保持 `NOT_EVALUATED`，不得用 development 观察分填充。

当前 `templates/` 已由 xsc 写入 held-out 正式考卷（retrieval 50 / field 26 / error 18）。
对本卷的系统观察评测 ID 为 `official-candidate-20260829T132222Z`，**SDTI = 63.36**，
`publish_allowed=false`，**不是** sealed `frozen_test`（manifest `frozen=false`，
本次评分使用 `allow_reviewed_unfrozen=True`）。数字见 `docs/DATA_REPORT_20260829.md`。
development 分册观察分（66.94）不得填入正式栏。

上列 1–6 条仍是 sealed 终考门槛。未完成来源/规则复验与 `frozen=true` 之前，
63.36 只是正式卷实测，不能当成冻结赛题自动发布。

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

正式运行的来源真实性统计只使用本次 Adapter 实际返回的 `source_items`，检查 `source_id`、官方 HTTPS 域名和 Adapter 状态；不再用 Gold Set 标准答案 ID 代替运行时来源校验。正确检出并拒绝自动修复的高风险用例表示安全规则生效，不计为“未解决”；只有高风险漏检或越权自动修复才计入阻断。由于当前 `official_candidate` 尚未 sealed/frozen，即使其他门槛通过仍保持 `REVIEW`、`publish_allowed=false`。

## 测试

```powershell
python -m pytest backend/tests/test_evaluation_metrics.py
python -m pytest backend/tests/test_goldset.py
python -m pytest backend/tests/test_evaluation_service.py
python -m pytest backend/tests/test_evaluation_api.py
```

测试中的 `fixture-only-gold` 只用于验证公式和工程逻辑，不是真实 benchmark，
不得当作本系统的评测成绩。
