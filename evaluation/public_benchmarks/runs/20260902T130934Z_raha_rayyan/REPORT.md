# raha_rayyan data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 948 | 0 |
| column_mode | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 2604 | 948 | 2775 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 948 | 0 |
| project_format_profile_v2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 948 | 0 |
| project_fusion_repair_v3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 948 | 0 |
| project_context_consensus_repair_v4 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 948 | 0 |
| project_date_profile_repair_v5 | 0.7987 | 0.7616 | 0.7797 | 0.7987 | 722 | 182 | 226 | 904 |
| project_source_anchor_repair_v6 | 0.7987 | 0.7616 | 0.7797 | 0.7987 | 722 | 182 | 226 | 904 |

Source: https://github.com/BigDaMa/raha/tree/master/datasets/rayyan
Dirty SHA-256: 7e25e6db262b0c72ca2d9735d5959599cf5a582e1c705459507c7b45d0d1d174
Clean SHA-256: 23159f43c0706782388ed8957ad0c74eb7b88bc98f34d65bd49296e186d4673f
Code revision: a7bfb3067f4db5238e1ca855d9ef132e4a173201
