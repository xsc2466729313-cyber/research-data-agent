# deepmatcher_fodors_zagats entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 1.0000 | 0.7273 | 0.8421 | 16 | 0 | 6 | 0.0040 ms |
| title_jaccard | 1.0000 | 0.7273 | 0.8421 | 16 | 0 | 6 | 0.0036 ms |
| project_portability_rule_v1 | 1.0000 | 0.8636 | 0.9268 | 19 | 0 | 3 | 0.0269 ms |
| project_learned_entity_v2 | 1.0000 | 0.8182 | 0.9000 | 18 | 0 | 4 | 0.0459 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `20b066790d1a5982a360c99c88af6e58ebf13f8d3150b7ff8172720c72f07a24`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
