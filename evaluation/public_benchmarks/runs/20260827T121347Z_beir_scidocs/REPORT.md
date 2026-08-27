# beir_scidocs retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.1490 | 0.3372 | 0.2661 | 41.34 ms |
| Project BM25 tuned v2 | 0.1490 | 0.3372 | 0.2661 | 38.96 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip
Test qrels SHA-256: `dcd3d7f77417294bb6f338537f3c28d8a5ea72b30fe6633f407fa85528767e35`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
