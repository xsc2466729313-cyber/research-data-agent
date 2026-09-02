# beir_scidocs retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BM25 local reference | 0.1490 | 0.1830 | 0.3070 | 0.4760 | 0.1557 | 0.3372 | 0.2661 | 46.75 ms | 20.21 ms | 78.50 ms | 1000 |
| Project BM25 tuned v2 | 0.1490 | 0.1830 | 0.3070 | 0.4760 | 0.1557 | 0.3372 | 0.2661 | 42.30 ms | 17.54 ms | 68.02 ms | 1000 |
| Project Hybrid (hashing-lexical-v1) | 0.0907 | 0.1260 | 0.2010 | 0.3160 | 0.0896 | 0.2114 | 0.1783 | 83.47 ms | 24.49 ms | 125.06 ms | 1000 |
| VNext BGE-small-en-v1.5 | 0.1910 | 0.2310 | 0.3980 | 0.5740 | 0.1969 | 0.4312 | 0.3351 | 5.50 ms | 0.00 ms | 5.50 ms | 1000 |
| VNext BM25 + BGE fusion | 0.1563 | 0.1890 | 0.3200 | 0.4960 | 0.1634 | 0.3581 | 0.2763 | 49.94 ms | 0.00 ms | 49.94 ms | 1000 |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip
Test qrels SHA-256: `dcd3d7f77417294bb6f338537f3c28d8a5ea72b30fe6633f407fa85528767e35`
Code revision: `4bce5a36aa7398803241283d3978f6df68113ace`
