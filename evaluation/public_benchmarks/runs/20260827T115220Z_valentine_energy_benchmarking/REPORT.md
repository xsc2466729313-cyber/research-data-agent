# valentine_energy_benchmarking schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.4000 | 0.5714 | 2 | 0 | 3 | 0.404 ms |
| token_jaccard | 1.0000 | 0.6000 | 0.7500 | 3 | 0 | 2 | 0.651 ms |
| project_schema_rule_v1 | 0.7500 | 0.6000 | 0.6667 | 3 | 1 | 2 | 4.725 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/City_Government__NYC_Municipal_Building_Energy_Benchmarking_Results
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `e05c203ec436bcd89835bdef78b40c5c57f9270ce5d6e9fb8691f33bc90ea170`
Target SHA-256: `06c7d6fc2acfbdfe033854ca0dceb681fd1748142a6bcc0f1856ec92e8e2111a`
Ground truth SHA-256: `0a66be2327182ce2f5a16ba1ac0cfd4329bb0af28420fe31be5a37be688d3ffa`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
