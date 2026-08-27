# valentine_dsny_disposal_assignments schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.1250 | 0.2222 | 1 | 0 | 7 | 0.489 ms |
| token_jaccard | 1.0000 | 0.3750 | 0.5455 | 3 | 0 | 5 | 0.669 ms |
| project_schema_rule_v1 | 0.5714 | 0.5000 | 0.5333 | 4 | 3 | 4 | 60.748 ms |
| project_schema_profile_v2 | 0.5714 | 0.5000 | 0.5333 | 4 | 3 | 4 | 1005.454 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/City_Government__DSNY_Districts_With_Disposal_Vendor_Assignments
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `78e031e099fa128699a32a8bff6200f6d1e731b2dd1773daca2e5136d1344f9e`
Target SHA-256: `abc9b9d8071da88188358f1773d1abbac22a2e915f9e6405d50c89dd8860a553`
Ground truth SHA-256: `9733ba1b4d1713d4c0acf4034e6d059220497dc14cd75cc56c07fd789dad910d`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
