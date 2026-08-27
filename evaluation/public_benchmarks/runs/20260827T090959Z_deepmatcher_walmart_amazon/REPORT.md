# deepmatcher_walmart_amazon entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 1.0000 | 0.0466 | 0.0891 | 9 | 0 | 184 | 0.0072 ms |
| title_jaccard | 0.8462 | 0.1710 | 0.2845 | 33 | 6 | 160 | 0.0083 ms |
| project_rule_entity_v1 | 0.7531 | 0.3161 | 0.4453 | 61 | 20 | 132 | 0.0246 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `ad23487a5c7f9e719e9b7cbea38b07d05940466b4bf040cd1cbc8fb251a53883`
Code revision: `0be92ca410668d713518e0b43c8573603a503e6a`
