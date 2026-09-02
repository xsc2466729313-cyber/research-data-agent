# 评测与 SDTI 报告

- 评测 ID：`official-candidate-deterministic-live-recall-v7-20260902`
- 评测状态：`EVALUATED`
- Gold Set：breast-cancer-official-candidate-20260829 / official-candidate-v1
- 安全门：`REVIEW`
- 允许自动发布：`false`

## 核心指标

| 指标 | 值 | 状态 | 分子 / 分母 | 目标 |
|---|---:|---|---:|---:|
| `retrieval_precision` | 0.947368 | `EVALUATED` | 18 / 19 | 0.9 |
| `retrieval_recall` | 1.000000 | `EVALUATED` | 18 / 18 | 0.9 |
| `retrieval_f1` | 0.972973 | `EVALUATED` | — | 0.9 |
| `faithfulness` | 1.000000 | `EVALUATED` | 26 / 26 | 0.95 |
| `traceability` | 1.000000 | `EVALUATED` | 26 / 26 | 1 |
| `error_precision` | 1.000000 | `EVALUATED` | 15 / 15 | — |
| `error_recall` | 1.000000 | `EVALUATED` | 15 / 15 | — |
| `error_f1` | 1.000000 | `EVALUATED` | — | 0.9 |
| `repair_accuracy` | 1.000000 | `EVALUATED` | 3 / 3 | 0.9 |
| `sdti` | 99.453519 | `EVALUATED` | — | 90 |

## 公式

- `retrieval_precision`: `TP / (TP + FP)`
- `retrieval_recall`: `TP / (TP + FN)`
- `retrieval_f1`: `2 * retrieval_precision * retrieval_recall / (retrieval_precision + retrieval_recall)`
- `faithfulness`: `faithful_fields / sampled_critical_fields`
- `traceability`: `fields_with_complete_valid_evidence / key_nonempty_fields`
- `error_precision`: `TP_e / (TP_e + FP_e)`
- `error_recall`: `TP_e / (TP_e + FN_e)`
- `error_f1`: `2 * error_precision * error_recall / (error_precision + error_recall)`
- `repair_accuracy`: `correct_repairs / automatic_repairs`
- `sdti`: `100 * (retrieval_f1 * faithfulness * traceability * error_f1 * repair_accuracy) ** (1/5)`

## 安全门与发布阻断

- 发布阻断：7 个实时任务的质量门仍为 REVIEW
- 发布阻断：尚未 sealed frozen_test，禁止当作冻结赛题自动发布

## 原始计数

```json
{
  "automatic_repairs": 3,
  "correct_repairs": 3,
  "errors": {
    "fn": 0,
    "fp": 0,
    "tp": 15
  },
  "faithful_fields": 26,
  "key_nonempty_fields": 26,
  "retrieval": {
    "fn": 0,
    "fp": 1,
    "tp": 18
  },
  "sampled_critical_fields": 26,
  "traceable_fields": 26
}
```

## 声明

本分为 xsc 已审核写入的 official_candidate 正式卷实测，不是 sealed frozen_test；不得把 development 分册成绩填入本栏。
