# beir_nfcorpus retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.2899 | 0.2209 | 0.5020 | 2.45 ms |
| Project Hybrid (hashing-lexical-v1) | 0.2493 | 0.1937 | 0.4417 | 5.18 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip
Test qrels SHA-256: `f8fba6ef3d4dd9c3a242a8ba4ae38276fc3622fce7dcbae764766d564542fd2a`
Code revision: `ef2725046a570f149d3e94266fc8fe02d7bbbf52`
