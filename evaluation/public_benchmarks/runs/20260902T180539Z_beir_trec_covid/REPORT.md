# beir_trec_covid retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.5133 | 0.7000 | 0.8800 | 1.0000 | 0.0136 | 0.0872 | 0.8077 | 358.24 ms | 78.84 ms | 497.51 ms | 50 |
| Project BM25 tuned v2 | 0.5133 | 0.7000 | 0.8800 | 1.0000 | 0.0136 | 0.0872 | 0.8077 | 336.92 ms | 66.59 ms | 435.63 ms | 50 |
| Project Hybrid (hashing-lexical-v1) | 0.3549 | 0.5000 | 0.7400 | 0.8400 | 0.0083 | 0.0474 | 0.6140 | 885.73 ms | 188.84 ms | 1158.65 ms | 50 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/trec-covid.zip
Test qrels SHA-256: `10669ab7d526cb04f52079139fd88c3d467a0776441b046567f540582798982b`
Code revision: `4bce5a36aa7398803241283d3978f6df68113ace`
