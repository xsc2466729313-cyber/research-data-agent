# raha_tax data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 121219 | 0 |
| column_mode | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 202168 | 121219 | 202207 |
| project_portability_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 121219 | 0 |

Source: https://github.com/BigDaMa/raha/tree/master/datasets/tax
Dirty SHA-256: 8dd3429ec4791b2ed1a688c308a57a9f3d1a94f77d1f4e98294a67273270b973
Clean SHA-256: 201290927ae92e65b3940d776b3df5b4d953c5dfd9abb231715a2e65ecca87b0
Code revision: 88c9cc09e9d931534cb55466e6bad9648066c7a0
