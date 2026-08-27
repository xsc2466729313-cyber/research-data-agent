# beir_scifact retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.6040 | 0.8279 | 0.5689 | 7.88 ms |
| Project BM25 tuned v2 | 0.6044 | 0.8284 | 0.5685 | 8.44 ms |
| Project Hybrid (hashing-lexical-v1) | 0.4070 | 0.7007 | 0.3833 | 15.83 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
Test qrels SHA-256: `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
