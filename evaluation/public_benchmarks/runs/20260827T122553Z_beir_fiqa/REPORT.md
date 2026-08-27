# beir_fiqa retrieval benchmark

> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.

| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |
|---|---:|---:|---:|---:|
| BM25 local reference | 0.2197 | 0.4856 | 0.2721 | 111.04 ms |
| Project BM25 tuned v2 | 0.2230 | 0.4843 | 0.2753 | 130.52 ms |

Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip
Test qrels SHA-256: `6adc2a640dcdd22bb8b3858f89107adef2a7c3db20a63550dfa7a0f71e379e44`
Code revision: `88c9cc09e9d931534cb55466e6bad9648066c7a0`
