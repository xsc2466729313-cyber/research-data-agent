# deepmatcher_beer_ratebeer entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 1.0000 | 0.2857 | 0.4444 | 4 | 0 | 10 | 0.0051 ms |
| title_jaccard | 1.0000 | 0.3571 | 0.5263 | 5 | 0 | 9 | 0.0052 ms |
| project_portability_rule_v1 | 1.0000 | 0.5000 | 0.6667 | 7 | 0 | 7 | 0.0168 ms |
| project_learned_entity_v2 | 0.7222 | 0.9286 | 0.8125 | 13 | 5 | 1 | 0.0523 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `545440994ad998ab96b230f1bbbc240af8b72ee55aa1dbbc583b751859615a5c`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
