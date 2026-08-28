# Entity Matcher V3 five-task comparison

> Official DeepMatcher test splits only. This is generic entity matching, not patient identity or clinical validity.

| Method | Tasks | Precision macro | Recall macro | F1 macro |
|---|---:|---:|---:|---:|
| Project learned entity rule v2 | 5 | 0.7259 | 0.7668 | 0.7408 |
| Project entity matcher v3 (fixed threshold) | 5 | 0.5860 | 0.4514 | 0.4883 |
| Project entity matcher v3 (train/valid calibrated) | 5 | 0.5251 | 0.6229 | 0.5579 |

Calibrated V3 improves over the fixed threshold by `0.0697` F1 and `0.1715` Recall, but remains `0.1829` F1 below the current baseline and stays experimental. Each run records the upstream source URL and test SHA-256 in its `run.json`.
