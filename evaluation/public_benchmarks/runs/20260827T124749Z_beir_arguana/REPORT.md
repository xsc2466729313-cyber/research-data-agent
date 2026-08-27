# beir_arguana retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.3067 | 0.9054 | 0.1983 | 83.69 ms |
| Project BM25 tuned v2 | 0.3067 | 0.9054 | 0.1983 | 68.02 ms |
| Project Hybrid (hashing-lexical-v1) | 0.0708 | 0.3172 | 0.0458 | 126.63 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/arguana.zip
Test qrels SHA-256: `0c47b481fa8b47fb9ca5e74bc8a017bdea14518c0e4a5d21345291180b3aca76`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
