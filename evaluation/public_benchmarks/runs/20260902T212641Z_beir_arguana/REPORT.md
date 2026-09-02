# beir_arguana retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VNext BM25 + BGE rank fusion | 0.3852 | 0.0000 | 0.4452 | 0.7881 | 0.7881 | 0.9787 | 0.2571 | 19.76 ms | 0.00 ms | 19.76 ms | 1406 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/arguana.zip
Test qrels SHA-256: `0c47b481fa8b47fb9ca5e74bc8a017bdea14518c0e4a5d21345291180b3aca76`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
