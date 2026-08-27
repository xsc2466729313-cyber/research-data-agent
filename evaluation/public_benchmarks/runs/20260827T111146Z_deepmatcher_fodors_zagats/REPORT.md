# deepmatcher_fodors_zagats entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 22 | 0.0007 ms |
| title_jaccard | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 22 | 0.0013 ms |
| project_portability_rule_v1 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 22 | 0.0352 ms |
| project_learned_entity_v2 | 1.0000 | 1.0000 | 1.0000 | 22 | 0 | 0 | 0.0428 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `20b066790d1a5982a360c99c88af6e58ebf13f8d3150b7ff8172720c72f07a24`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
