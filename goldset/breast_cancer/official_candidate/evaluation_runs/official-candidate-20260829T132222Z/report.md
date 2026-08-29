# 评测与 SDTI 报告

- 评测 ID：`official-candidate-20260829T132222Z`
- 评测状态：`EVALUATED`
- Gold Set：breast-cancer-official-candidate-20260829 / official-candidate-v1
- 安全门：`FAIL`
- 允许自动发布：`false`

## 核心指标

| 指标 | 值 | 状态 | 分子 / 分母 | 目标 |
|---|---:|---|---:|---:|
| `retrieval_precision` | 0.354839 | `EVALUATED` | 11 / 31 | 0.9 |
| `retrieval_recall` | 0.611111 | `EVALUATED` | 11 / 18 | 0.9 |
| `retrieval_f1` | 0.448980 | `EVALUATED` | — | 0.9 |
| `faithfulness` | 0.653846 | `EVALUATED` | 17 / 26 | 0.95 |
| `traceability` | 1.000000 | `EVALUATED` | 26 / 26 | 1 |
| `error_precision` | 1.000000 | `EVALUATED` | 8 / 8 | — |
| `error_recall` | 0.533333 | `EVALUATED` | 8 / 15 | — |
| `error_f1` | 0.695652 | `EVALUATED` | — | 0.9 |
| `repair_accuracy` | 0.500000 | `EVALUATED` | 1 / 2 | 0.9 |
| `sdti` | 63.359664 | `EVALUATED` | — | 90 |

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

- 红线：Faithfulness < 90%
- 发布阻断：5 个高风险问题仍未解决
- 发布阻断：尚未 sealed frozen_test，禁止当作冻结赛题自动发布

## 原始计数

```json
{
  "automatic_repairs": 2,
  "correct_repairs": 1,
  "errors": {
    "fn": 7,
    "fp": 0,
    "tp": 8
  },
  "faithful_fields": 17,
  "key_nonempty_fields": 26,
  "retrieval": {
    "fn": 7,
    "fp": 20,
    "tp": 11
  },
  "sampled_critical_fields": 26,
  "traceable_fields": 26
}
```

## 声明

本分为 xsc 已审核写入的 official_candidate 正式卷实测，不是 sealed frozen_test；不得把 development 分册成绩填入本栏。
