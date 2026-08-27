# valentine_housing_maintenance schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.6667 | 0.8000 | 8 | 0 | 4 | 0.728 ms |
| token_jaccard | 0.8000 | 0.6667 | 0.7273 | 8 | 2 | 4 | 1.061 ms |
| project_schema_rule_v1 | 0.7273 | 0.6667 | 0.6957 | 8 | 3 | 4 | 22.172 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/Housing_&_Development__Housing_Maintenance_Code_Complaints_and_Problems
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `4fb95b9209d91433f7d1dc07433b7b459025dff2abbb6da85c35075d63ed824a`
Target SHA-256: `873db19234ba05fd6eca261517bfb71d233f1fb13fc080efa4774e5e71d655d4`
Ground truth SHA-256: `71b6c7cc43c7ee7771f3c5fdfacba35351da8c0e2e739401f3d2ae5dfc37134b`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
