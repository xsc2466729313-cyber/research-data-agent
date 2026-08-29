# 评测与 SDTI 报告

- 评测 ID：`development-xsc-20260829`
- 评测状态：`EVALUATED`
- Gold Set：breast-cancer-development-20260829 / development-v1
- 安全门：`FAIL`
- 允许自动发布：`false`

## 核心指标

| 指标 | 值 | 状态 | 分子 / 分母 | 目标 |
|---|---:|---|---:|---:|
| `retrieval_precision` | 0.500000 | `EVALUATED` | 11 / 22 | 0.9 |
| `retrieval_recall` | 0.423077 | `EVALUATED` | 11 / 26 | 0.9 |
| `retrieval_f1` | 0.458333 | `EVALUATED` | — | 0.9 |
| `faithfulness` | 0.771429 | `EVALUATED` | 27 / 35 | 0.95 |
| `traceability` | 1.000000 | `EVALUATED` | 35 / 35 | 1 |
| `error_precision` | 1.000000 | `EVALUATED` | 8 / 8 | — |
| `error_recall` | 0.421053 | `EVALUATED` | 8 / 19 | — |
| `error_f1` | 0.592593 | `EVALUATED` | — | 0.9 |
| `repair_accuracy` | 0.500000 | `EVALUATED` | 1 / 2 | 0.9 |
| `sdti` | 63.685517 | `EVALUATED` | — | 90 |

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

## 原始计数

```json
{
  "automatic_repairs": 2,
  "correct_repairs": 1,
  "errors": {
    "fn": 11,
    "fp": 0,
    "tp": 8
  },
  "faithful_fields": 27,
  "key_nonempty_fields": 35,
  "retrieval": {
    "fn": 15,
    "fp": 11,
    "tp": 11
  },
  "sampled_critical_fields": 35,
  "traceable_fields": 35
}
```

## 声明

指标仅代表该冻结 Gold Set 与本次系统观察的评测结果；不得将测试 fixture 或未审核数据冒充真实系统成绩。
