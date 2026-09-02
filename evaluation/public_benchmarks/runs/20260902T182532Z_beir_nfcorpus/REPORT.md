# beir_nfcorpus retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.2899 | 0.4211 | 0.5697 | 0.6656 | 0.1350 | 0.2209 | 0.5020 | 0.99 ms | 1.26 ms | 3.31 ms | 323 |
| Project BM25 tuned v2 | 0.2902 | 0.4241 | 0.5728 | 0.6687 | 0.1353 | 0.2206 | 0.5061 | 1.36 ms | 1.85 ms | 5.09 ms | 323 |
| Project Hybrid (hashing-lexical-v1) | 0.2493 | 0.3746 | 0.4954 | 0.5851 | 0.1102 | 0.1937 | 0.4417 | 3.70 ms | 2.69 ms | 8.33 ms | 323 |
| VNext BGE-small-en-v1.5 | 0.3315 | 0.4396 | 0.5789 | 0.7028 | 0.1609 | 0.2975 | 0.5257 | 4.17 ms | 0.00 ms | 4.17 ms | 323 |
| VNext BM25 + BGE fusion | 0.3318 | 0.4427 | 0.5789 | 0.7028 | 0.1609 | 0.2975 | 0.5273 | 5.31 ms | 0.00 ms | 5.31 ms | 323 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip
Test qrels SHA-256: `f8fba6ef3d4dd9c3a242a8ba4ae38276fc3622fce7dcbae764766d564542fd2a`
Code revision: `4bce5a36aa7398803241283d3978f6df68113ace`
