# holoclean_hospital data cleaning benchmark

> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.

| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_repair | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 509 | 0 |
| column_mode | 0.1137 | 0.0472 | 0.0667 | 0.0453 | 24 | 187 | 485 | 530 |
| project_consensus_clean_v1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 509 | 0 |

Source: https://github.com/HoloClean/holoclean/tree/master/testdata
Dirty SHA-256: bbb2f60e9e7bbda68b1115b3bbb9a0d70587a9d33384a2373e4d447789fd619a
Clean SHA-256: 5dc89f7701abae92af81308ae9cbeea584c39cba288fdffe3324397e15f8ca2c
Code revision: 0be92ca410668d713518e0b43c8573603a503e6a
