# raha_beers data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 4362 | 0 |
| column_mode | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 2567 | 4362 | 2656 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 4362 | 0 |
| project_format_profile_v2 | 1.0000 | 0.9679 | 0.9837 | 1.0000 | 4222 | 0 | 140 | 4222 |
| project_fusion_repair_v3 | 1.0000 | 0.9679 | 0.9837 | 1.0000 | 4222 | 0 | 140 | 4222 |
| project_context_consensus_repair_v4 | 1.0000 | 0.9679 | 0.9837 | 1.0000 | 4222 | 0 | 140 | 4222 |
| project_date_profile_repair_v5 | 1.0000 | 0.9679 | 0.9837 | 1.0000 | 4222 | 0 | 140 | 4222 |
| project_source_anchor_repair_v6 | 1.0000 | 0.9679 | 0.9837 | 1.0000 | 4222 | 0 | 140 | 4222 |

Source: https://github.com/BigDaMa/raha/tree/master/datasets/beers
Dirty SHA-256: 7110bf4931a9445a1675e544d6c996817c739136239f8a2b02e088c7ec0a1f68
Clean SHA-256: 373227df59ad197e154dd5149125789e415019535c7223355e9486ee1b3b93de
Code revision: a7bfb3067f4db5238e1ca855d9ef132e4a173201
