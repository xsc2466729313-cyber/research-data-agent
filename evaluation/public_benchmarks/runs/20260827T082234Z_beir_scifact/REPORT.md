# beir_scifact retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.6040 | 0.8279 | 0.5689 | 6.54 ms |
| Project Hybrid (hashing-lexical-v1) | 0.4070 | 0.7007 | 0.3833 | 18.19 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
Test qrels SHA-256: `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c`
Code revision: `ef2725046a570f149d3e94266fc8fe02d7bbbf52`
