# Schema Matcher V3 Phase D

Phase D 在保留 `SchemaMatcherV2` baseline 的前提下新增 `backend/app/integration/schema_matcher_v3.py`。

## 决策链

```text
lexical + alias + value profile + type + cardinality
+ semantic name + table context + ontology
→ AUTO / REVIEW / REJECT
→ selective judge（仅边界、review band 或语义冲突）
```

所有结果保留特征字典、`decision_source` 和 judge reason。judge 不可用时进入 REVIEW，不能绕过规则直接写入。

## 真实对照

使用已下载的 Valentine 官方任务 `valentine_education_covid_meals`（固定 commit 和 SHA-256 见运行产物）：

| 方法 | Precision | Recall | F1 |
|---|---:|---:|---:|
| project_schema_profile_v2 | 1.0000 | 1.0000 | 1.0000 |
| project_schema_v3 | 1.0000 | 0.6000 | 0.7500 |

产物：[run.json](../evaluation/public_benchmarks/runs/20260828T103533Z_valentine_education_covid_meals/run.json) 和 [REPORT.md](../evaluation/public_benchmarks/runs/20260828T103533Z_valentine_education_covid_meals/REPORT.md)。这是通用字段对齐 benchmark，不是乳腺癌临床效果、患者实体效果或 SDTI。

V3 当前没有超过该任务的 V2 baseline，因此不切换默认 matcher；结果用于暴露特征融合仍需在完整十任务和领域 Gold Set 上校准的事实。完整十任务宏平均见 [evaluation/schema_v3_macro_20260828.md](../evaluation/schema_v3_macro_20260828.md)，V3 F1 `0.7994`，V2 F1 `0.8451`。

## 边界与回滚

- 默认不调用 Qwen，`qwen_invocation_count` 仅在注入 judge callback 时增加。
- 当前 embedding feature 是无依赖的语义名称相似度 proxy，不应表述为真实 embedding 模型成绩。
- 真实 Qwen Judge、confidence calibration、乳腺癌 canonical 字段 Gold Set 和十任务宏平均仍未完成。
- 回滚时继续使用 `SchemaMatcherV2`；V3 为独立模块，不修改冻结配置。
