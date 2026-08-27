# raha_movies_1 data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 7675 | 0 |
| column_mode | 0.0001 | 0.0008 | 0.0002 | 0.0001 | 6 | 48364 | 7669 | 53994 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 7675 | 0 |
| project_format_profile_v2 | 1.0000 | 0.8044 | 0.8916 | 0.9701 | 6174 | 0 | 1501 | 6364 |

Source: https://github.com/BigDaMa/raha/tree/master/datasets/movies_1
Dirty SHA-256: bed752115dd0a5925ea36db443ff6835d10a5a8d2f549299535b14f8ac324316
Clean SHA-256: 22a84e70d153d809341c55cf8e8154beebe1836456f617bf8277b953a762bfca
Code revision: 88c9cc09e9d931534cb55466e6bad9648066c7a0
