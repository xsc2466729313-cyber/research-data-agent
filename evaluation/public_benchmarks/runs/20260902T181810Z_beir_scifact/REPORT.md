# beir_scifact retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.6040 | 0.4833 | 0.6400 | 0.7400 | 0.7245 | 0.8279 | 0.5689 | 6.65 ms | 3.14 ms | 12.17 ms | 300 |
| Project BM25 tuned v2 | 0.6044 | 0.4800 | 0.6400 | 0.7400 | 0.7262 | 0.8284 | 0.5685 | 6.25 ms | 2.85 ms | 10.76 ms | 300 |
| Project Hybrid (hashing-lexical-v1) | 0.4070 | 0.3233 | 0.4167 | 0.5233 | 0.5081 | 0.7007 | 0.3833 | 12.75 ms | 4.30 ms | 20.59 ms | 300 |
| VNext BGE-small-en-v1.5 | 0.6803 | 0.5767 | 0.6967 | 0.8133 | 0.7979 | 0.9383 | 0.6499 | 7.74 ms | 0.00 ms | 7.74 ms | 300 |
| VNext BM25 + BGE fusion | 0.6803 | 0.5767 | 0.6967 | 0.8133 | 0.7979 | 0.9383 | 0.6499 | 15.74 ms | 0.00 ms | 15.74 ms | 300 |
| VNext BM25 + BGE + CrossEncoder | 0.6872 | 0.5767 | 0.7133 | 0.8133 | 0.7979 | 0.9383 | 0.6585 | 407.37 ms | 0.00 ms | 407.37 ms | 300 |
| VNext development-selected (hybrid_rerank) | 0.6872 | 0.5767 | 0.7133 | 0.8133 | 0.7979 | 0.9383 | 0.6585 | 414.76 ms | 0.00 ms | 414.76 ms | 300 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
Test qrels SHA-256: `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c`
Code revision: `4bce5a36aa7398803241283d3978f6df68113ace`
