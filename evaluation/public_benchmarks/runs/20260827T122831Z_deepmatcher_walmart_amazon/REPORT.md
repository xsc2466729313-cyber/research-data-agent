# deepmatcher_walmart_amazon entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 1.0000 | 0.0466 | 0.0891 | 9 | 0 | 184 | 0.0070 ms |
| title_jaccard | 0.8462 | 0.1710 | 0.2845 | 33 | 6 | 160 | 0.0085 ms |
| project_portability_rule_v1 | 0.7531 | 0.3161 | 0.4453 | 61 | 20 | 132 | 0.0225 ms |
| project_learned_entity_v2 | 0.5066 | 0.3990 | 0.4464 | 77 | 75 | 116 | 0.0397 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `ad23487a5c7f9e719e9b7cbea38b07d05940466b4bf040cd1cbc8fb251a53883`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
