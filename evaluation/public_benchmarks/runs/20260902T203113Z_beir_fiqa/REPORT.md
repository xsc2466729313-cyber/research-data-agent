# beir_fiqa retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.2197 | 0.1991 | 0.3133 | 0.4568 | 0.2766 | 0.4856 | 0.2721 | 116.48 ms | 50.42 ms | 194.96 ms | 648 |
| Project BM25 tuned v2 | 0.2230 | 0.1991 | 0.3194 | 0.4691 | 0.2824 | 0.4843 | 0.2753 | 117.69 ms | 49.71 ms | 201.00 ms | 648 |
| Project Hybrid (hashing-lexical-v1) | 0.0992 | 0.0833 | 0.1620 | 0.2392 | 0.1302 | 0.2544 | 0.1305 | 200.42 ms | 62.10 ms | 292.98 ms | 648 |
| VNext BGE-small-en-v1.5 | 0.3533 | 0.3534 | 0.5000 | 0.6142 | 0.4071 | 0.6413 | 0.4396 | 5.09 ms | 0.00 ms | 5.09 ms | 648 |
| VNext BM25 + BGE fusion | 0.3533 | 0.3534 | 0.5000 | 0.6142 | 0.4071 | 0.6413 | 0.4396 | 109.52 ms | 0.00 ms | 109.52 ms | 648 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip
Test qrels SHA-256: `6adc2a640dcdd22bb8b3858f89107adef2a7c3db20a63550dfa7a0f71e379e44`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
