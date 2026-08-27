# valentine_dpr_athletic_facilities schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.3000 | 0.4615 | 3 | 0 | 7 | 0.978 ms |
| token_jaccard | 1.0000 | 0.7000 | 0.8235 | 7 | 0 | 3 | 1.593 ms |
| project_schema_rule_v1 | 0.7778 | 0.7000 | 0.7368 | 7 | 2 | 3 | 33.881 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/City_Government__DPR_AthleticFacilities_001
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `ac27b06dc7200eaf55e39017b9bd671194df035ad73734e189e161c5fe31f3d9`
Target SHA-256: `5b844c1088cb9585ff21bbb8005f8f188e5174124ed64d37c31bcf12e414b206`
Ground truth SHA-256: `74c485a39beed8bb0a6b8b8389382ebffe5d45cee329a7a6f4e5cd564e164bae`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
