# beir_quora retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Project BM25 tuned v2 | 0.7408 | 0.6540 | 0.7987 | 0.8931 | 0.8418 | 0.9479 | 0.7363 | 10.19 ms | 4.07 ms | 16.96 ms | 10000 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip
Test qrels SHA-256: `3c5b3e6bd9a26ecf67271bf0f856aa87cc4e71fa3665b32cc0ec906d7711fddb`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
