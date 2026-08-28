# Schema Matcher V3 ten-task comparison

> Official Valentine public schema-matching tasks only. This is not a clinical canonical-schema, patient-identity, or SDTI score.

| Method | Tasks | Precision macro | Recall macro | F1 macro |
|---|---:|---:|---:|---:|
| Project schema value-profile v2 | 10 | 0.9286 | 0.7864 | 0.8451 |
| Project schema feature fusion v3 | 10 | 0.8648 | 0.7724 | 0.7994 |

V3 is currently below the existing V2 baseline on this ten-task run (`-0.0457` F1), so V2 remains the default. V3 is retained as an auditable experimental path; its semantic feature is a dependency-free name-similarity proxy, not a downloaded embedding model.

Run directories: `evaluation/public_benchmarks/runs/20260828T104132Z_valentine_*` through `20260828T104136Z_valentine_*`. Each directory contains `run.json`, `REPORT.md`, the official source manifest and SHA-256 values.

Limitations: no breast-cancer canonical-schema Gold Set, no calibrated validation thresholds, and no real Qwen judge invocation were included in this run.
