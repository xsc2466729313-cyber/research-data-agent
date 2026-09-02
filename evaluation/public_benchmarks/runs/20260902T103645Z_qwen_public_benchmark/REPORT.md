# Public benchmark with real Qwen

> Qwen saw only raw benchmark inputs. Test labels were used only for final scoring.

## Retrieval: BEIR

| Dataset | BM25 nDCG@10 | Qwen rewrite nDCG@10 | BM25 Recall@100 | Qwen Recall@100 |
|---|---:|---:|---:|---:|
| beir_scifact | 0.6040 | 0.6453 | 0.8279 | 0.8519 |

API calls: 300; failures: 36

## Reproducibility

- Model: real Qwen configured by the local project environment; API key is not stored.
- No test labels, qrels, clean tables, or hidden annotations were sent to Qwen.
- A failed batch produces no repairs/rewrites and is counted as an API failure.
