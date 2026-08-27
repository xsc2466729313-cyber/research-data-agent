# valentine_public_art_inventory schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.1333 | 0.2353 | 2 | 0 | 13 | 1.216 ms |
| token_jaccard | 1.0000 | 0.2000 | 0.3333 | 3 | 0 | 12 | 4.764 ms |
| project_schema_rule_v1 | 0.4444 | 0.2667 | 0.3333 | 4 | 5 | 11 | 69.054 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/Housing_&_Development__Public_Design_Commission_Outdoor_Public_Art_Invent
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `86bbb09d72cfbcc9fc1713acf1663be3a8d6364a69ae5f4146c99517df73e2a8`
Target SHA-256: `de3418d5d4d950a8045c8044ca57e1934f20051a105a1c92c6951b4f51f3f596`
Ground truth SHA-256: `233e18480f71b7fb9268820823eb1e3fd9e7ccc9250f694f9582ce2a8580414d`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
