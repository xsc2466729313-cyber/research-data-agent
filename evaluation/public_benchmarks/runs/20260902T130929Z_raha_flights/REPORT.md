# raha_flights data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 4920 | 0 |
| column_mode | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 10 | 4920 | 234 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 4920 | 0 |
| project_format_profile_v2 | 1.0000 | 0.0264 | 0.0515 | 0.6500 | 130 | 0 | 4790 | 200 |
| project_fusion_repair_v3 | 1.0000 | 0.0264 | 0.0515 | 0.6500 | 130 | 0 | 4790 | 200 |
| project_context_consensus_repair_v4 | 1.0000 | 0.0996 | 0.1811 | 0.8750 | 490 | 0 | 4430 | 560 |
| project_date_profile_repair_v5 | 1.0000 | 0.0996 | 0.1811 | 0.8750 | 490 | 0 | 4430 | 560 |
| project_source_anchor_repair_v6 | 1.0000 | 0.9323 | 0.9650 | 0.9903 | 4587 | 0 | 333 | 4632 |

Source: https://github.com/BigDaMa/raha/tree/master/datasets/flights
Dirty SHA-256: 1b5c1afa10aa0e7c20fd7e14d05c56772715b2771aa0f5fa67ed1709e1eecd46
Clean SHA-256: 0acfcfd8985b06fdd363965c9e8d9522c43e7589a93d79ae7dc311e1c37fdf3b
Code revision: a7bfb3067f4db5238e1ca855d9ef132e4a173201
