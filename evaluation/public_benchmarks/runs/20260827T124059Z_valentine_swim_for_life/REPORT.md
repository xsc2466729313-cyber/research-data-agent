# valentine_swim_for_life schema matching benchmark

> Generic field-alignment test only; this is not a clinical schema or SDTI result.

| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |
|---|---:|---:|---:|---:|---:|---:|---:|
| exact_normalized_name | 1.0000 | 0.2000 | 0.3333 | 1 | 0 | 4 | 0.139 ms |
| token_jaccard | 1.0000 | 0.8000 | 0.8889 | 4 | 0 | 1 | 0.211 ms |
| project_schema_rule_v1 | 0.8000 | 0.8000 | 0.8000 | 4 | 1 | 1 | 5.932 ms |

Source: https://github.com/delftdata/valentine/tree/5d5163f04da304985bd51a476ccf7653de3979c3/experiments/data/Recreation__Swim_for_Life__2016_to_2020
Pinned Valentine commit: `5d5163f04da304985bd51a476ccf7653de3979c3`
Source SHA-256: `1aea7318e570a5ab97c10aa5977af751cc6c68920c28431e6deb93feccc0a3c3`
Target SHA-256: `0662b2c2b86ab1103616a883bc8a7ad8476c7688296c725d30e7448f3b6cf7dc`
Ground truth SHA-256: `02489ddffe49f42d7c6b578c0cb41534bbce4994ac1dde354577ce3d3501fbb7`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
