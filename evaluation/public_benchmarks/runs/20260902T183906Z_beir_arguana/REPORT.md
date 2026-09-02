# beir_arguana retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.3067 | 0.0007 | 0.3172 | 0.6515 | 0.6515 | 0.9054 | 0.1983 | 81.59 ms | 24.17 ms | 124.39 ms | 1406 |
| Project BM25 tuned v2 | 0.3067 | 0.0007 | 0.3172 | 0.6515 | 0.6515 | 0.9054 | 0.1983 | 84.45 ms | 17.66 ms | 115.26 ms | 1406 |
| Project Hybrid (hashing-lexical-v1) | 0.0708 | 0.0000 | 0.0733 | 0.1508 | 0.1508 | 0.3172 | 0.0458 | 127.88 ms | 30.34 ms | 184.48 ms | 1406 |
| VNext BGE-small-en-v1.5 | 0.3836 | 0.0000 | 0.4538 | 0.7688 | 0.7688 | 0.9687 | 0.2601 | 15.85 ms | 0.00 ms | 15.85 ms | 1406 |
| VNext BM25 + BGE fusion | 0.3741 | 0.0000 | 0.4139 | 0.7802 | 0.7802 | 0.9758 | 0.2454 | 89.75 ms | 0.00 ms | 89.75 ms | 1406 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/arguana.zip
Test qrels SHA-256: `0c47b481fa8b47fb9ca5e74bc8a017bdea14518c0e4a5d21345291180b3aca76`
Code revision: `4bce5a36aa7398803241283d3978f6df68113ace`
