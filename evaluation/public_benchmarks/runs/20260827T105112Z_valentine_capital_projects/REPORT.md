# valentine_capital_projects schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.6000 | 0.7500 | 3 | 0 | 2 | 0.267 ms |
| token_jaccard | 1.0000 | 0.6000 | 0.7500 | 3 | 0 | 2 | 0.303 ms |
| project_schema_rule_v1 | 0.7500 | 0.6000 | 0.6667 | 3 | 1 | 2 | 5.523 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/City_Government__Capital_Projects
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `36b7060e1c6d5aec5fe607c4da676142a053f7cdfaa2602aa60935ff5c5e72cc`
Target SHA-256: `389471f86eb6b1c88f22d106bd51dee43b790199c9f74066947c01d7061af8c0`
Ground truth SHA-256: `9b91b8d8aa9b7b318d3d47a2bc88732a040811313ae21d21ff1f602ab0324881`
Code revision: `66fb402e3acfd6b45a1664fd66bbe258672798f3`
