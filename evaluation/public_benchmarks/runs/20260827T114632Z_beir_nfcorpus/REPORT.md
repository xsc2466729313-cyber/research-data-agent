# beir_nfcorpus retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.2899 | 0.2209 | 0.5020 | 1.50 ms |
| Project BM25 tuned v2 | 0.2902 | 0.2206 | 0.5061 | 1.50 ms |
| Project Hybrid (hashing-lexical-v1) | 0.2493 | 0.1937 | 0.4417 | 3.99 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip
Test qrels SHA-256: `f8fba6ef3d4dd9c3a242a8ba4ae38276fc3622fce7dcbae764766d564542fd2a`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
