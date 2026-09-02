# beir_fiqa retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VNext BM25 + BGE rank fusion | 0.3637 | 0.3503 | 0.5154 | 0.6343 | 0.4260 | 0.6694 | 0.4453 | 7.49 ms | 0.00 ms | 7.49 ms | 648 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip
Test qrels SHA-256: `6adc2a640dcdd22bb8b3858f89107adef2a7c3db20a63550dfa7a0f71e379e44`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
