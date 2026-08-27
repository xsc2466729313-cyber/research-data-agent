# valentine_education_covid_meals schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.4000 | 0.5714 | 2 | 0 | 3 | 0.086 ms |
| token_jaccard | 1.0000 | 0.4000 | 0.5714 | 2 | 0 | 3 | 0.129 ms |
| project_schema_rule_v1 | 0.6667 | 0.4000 | 0.5000 | 2 | 1 | 3 | 1.397 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/Education__COVID-19_Free_Meals_Locations
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `971cf15d40c884931d89c817fb0f57cf430384c1ca0b15362b8f4b6c5da0a383`
Target SHA-256: `2d33db4a5c1427bb2ff6da526c69b39ab407748ef4bc951bc34ce76fe9e04c49`
Ground truth SHA-256: `edfb3a7c198039c8d544122264b9877b1566373d628141f37812991fdb2a7ade`
Code revision: `6783c0afa7dae69050081ed03431aa23f72d84a4`
