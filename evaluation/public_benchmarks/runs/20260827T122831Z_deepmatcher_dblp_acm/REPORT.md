# deepmatcher_dblp_acm entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 0.8679 | 0.9324 | 0.8990 | 414 | 63 | 30 | 0.0065 ms |
| title_jaccard | 0.8580 | 0.9662 | 0.9089 | 429 | 71 | 15 | 0.0071 ms |
| project_portability_rule_v1 | 0.8555 | 0.9865 | 0.9163 | 438 | 74 | 6 | 0.0234 ms |
| project_learned_entity_v2 | 0.9435 | 0.9775 | 0.9602 | 434 | 26 | 10 | 0.0423 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `e49adc4590d24c18b1a9bbd96011d9c745e10432e10e93e050d856a206fac394`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
