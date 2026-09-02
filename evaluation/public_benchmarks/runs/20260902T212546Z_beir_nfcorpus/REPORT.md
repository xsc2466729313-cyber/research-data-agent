# beir_nfcorpus retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VNext BM25 + BGE rank fusion | 0.3427 | 0.4737 | 0.6068 | 0.7121 | 0.1654 | 0.3069 | 0.5536 | 3.91 ms | 0.00 ms | 3.91 ms | 323 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip
Test qrels SHA-256: `f8fba6ef3d4dd9c3a242a8ba4ae38276fc3622fce7dcbae764766d564542fd2a`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
