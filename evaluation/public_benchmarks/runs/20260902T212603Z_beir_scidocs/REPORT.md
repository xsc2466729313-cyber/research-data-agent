# beir_scidocs retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VNext BM25 + BGE rank fusion | 0.1828 | 0.2120 | 0.3720 | 0.5600 | 0.1921 | 0.4326 | 0.3137 | 5.53 ms | 0.00 ms | 5.53 ms | 1000 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip
Test qrels SHA-256: `dcd3d7f77417294bb6f338537f3c28d8a5ea72b30fe6633f407fa85528767e35`
Code revision: `4c505bdddfa67842df311f5870413d260cb2abbb`
