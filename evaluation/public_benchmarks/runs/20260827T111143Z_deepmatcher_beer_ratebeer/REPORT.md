# deepmatcher_beer_ratebeer entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 14 | 0.0011 ms |
| title_jaccard | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 14 | 0.0019 ms |
| project_portability_rule_v1 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 14 | 0.0230 ms |
| project_learned_entity_v2 | 0.7333 | 0.7857 | 0.7586 | 11 | 4 | 3 | 0.0423 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `545440994ad998ab96b230f1bbbc240af8b72ee55aa1dbbc583b751859615a5c`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
