# valentine_dcm_street_centerline schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.7143 | 0.8333 | 5 | 0 | 2 | 0.221 ms |
| token_jaccard | 1.0000 | 0.8571 | 0.9231 | 6 | 0 | 1 | 0.332 ms |
| project_schema_rule_v1 | 1.0000 | 0.8571 | 0.9231 | 6 | 0 | 1 | 6.028 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/City_Government__DCM_StreetCenterLine
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `62ac0077b9a02e4b72de68d89648c0c112fd4442ea38676f3202983da0043877`
Target SHA-256: `0533b7410cd75a7cbae93491f05021d770f46bebbd9ee62caab74a4ae3ce5c8e`
Ground truth SHA-256: `a7b846c28769add706ba48aa5b4274fb886503ed15bcab52ed14763fb06c9669`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
