# beir_scifact retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VNext BM25 + BGE rank fusion | 0.6829 | 0.5533 | 0.7067 | 0.8300 | 0.8167 | 0.9510 | 0.6455 | 8.26 ms | 0.00 ms | 8.26 ms | 300 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
Test qrels SHA-256: `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
