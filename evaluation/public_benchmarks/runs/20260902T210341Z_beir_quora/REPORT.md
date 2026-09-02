# beir_quora retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.7393 | 0.6517 | 0.7991 | 0.8929 | 0.8412 | 0.9486 | 0.7347 | 12.11 ms | 5.47 ms | 21.53 ms | 10000 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip
Test qrels SHA-256: `3c5b3e6bd9a26ecf67271bf0f856aa87cc4e71fa3665b32cc0ec906d7711fddb`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
