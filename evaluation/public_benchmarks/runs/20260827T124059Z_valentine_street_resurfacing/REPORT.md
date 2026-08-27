# valentine_street_resurfacing schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.4000 | 0.5714 | 2 | 0 | 3 | 0.203 ms |
| token_jaccard | 1.0000 | 0.4000 | 0.5714 | 2 | 0 | 3 | 0.291 ms |
| project_schema_rule_v1 | 0.6667 | 0.4000 | 0.5000 | 2 | 1 | 3 | 3.659 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/Transportation__DOT_In-house_Street_Resurfacing_Projects
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `23c793ad9be40a34a33b58363d433a338bdfb6d58aba3f5b4ee2dbb7d7d176f7`
Target SHA-256: `6aee22b8f6f0365e8a5ba2fa9fd30e694d18236e46912444e4d7474de0214f2a`
Ground truth SHA-256: `204357713b7bd6b64910663d8e33dc6485297a62795d1fbe65a4052c0928e374`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
