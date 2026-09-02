# holoclean_hospital data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 509 | 0 |
| column_mode | 0.1137 | 0.0472 | 0.0667 | 0.0453 | 24 | 187 | 485 | 530 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 509 | 0 |
| project_format_profile_v2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 509 | 0 |
| project_fusion_repair_v3 | 1.0000 | 0.8094 | 0.8947 | 1.0000 | 412 | 0 | 97 | 412 |
| project_context_consensus_repair_v4 | 1.0000 | 0.8094 | 0.8947 | 1.0000 | 412 | 0 | 97 | 412 |
| project_date_profile_repair_v5 | 1.0000 | 0.8094 | 0.8947 | 1.0000 | 412 | 0 | 97 | 412 |
| project_source_anchor_repair_v6 | 1.0000 | 0.8094 | 0.8947 | 1.0000 | 412 | 0 | 97 | 412 |

Source: https://github.com/HoloClean/holoclean/tree/master/testdata
Dirty SHA-256: bbb2f60e9e7bbda68b1115b3bbb9a0d70587a9d33384a2373e4d447789fd619a
Clean SHA-256: 5dc89f7701abae92af81308ae9cbeea584c39cba288fdffe3324397e15f8ca2c
Code revision: a7bfb3067f4db5238e1ca855d9ef132e4a173201
