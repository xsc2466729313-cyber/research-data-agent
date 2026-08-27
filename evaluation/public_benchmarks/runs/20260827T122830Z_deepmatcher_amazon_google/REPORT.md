# deepmatcher_amazon_google entity matching benchmark

> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.

| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_title | 0.3043 | 0.0299 | 0.0545 | 7 | 16 | 227 | 0.0057 ms |
| title_jaccard | 0.5789 | 0.1410 | 0.2268 | 33 | 24 | 201 | 0.0066 ms |
| project_portability_rule_v1 | 0.6437 | 0.2393 | 0.3489 | 56 | 31 | 178 | 0.0157 ms |
| project_learned_entity_v2 | 0.4325 | 0.5342 | 0.4780 | 125 | 164 | 109 | 0.0264 ms |

Source: https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md
Test SHA-256: `09e376c0c5391bd4a6c6d8efde148c994441b6043ef6b7f9eab2a8772a6fb362`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
