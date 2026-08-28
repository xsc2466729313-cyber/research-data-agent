# VNext Retrieval 五组公开 Benchmark 汇总

> 仅为检索层 BEIR test 指标，不是临床有效性、全 Agent 质量或 SDTI 成绩。

| 方法 | 数据集数 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 平均查询延迟 |
|---|---:|---:|---:|---:|---:|
| Tuned BM25 | 5 | 0.3147 | 0.5552 | 0.3629 | 54.57 ms |
| VNext BGE-small-en-v1.5 | 5 | 0.3880 | 0.6554 | 0.4421 | 10.72 ms |
| VNext BM25+BGE Fusion | 5 | 0.3791 | 0.6422 | 0.4277 | 62.73 ms |

## 结论

- BGE 与校准融合的结果按实际完成任务汇总；提升幅度因任务而异，不能外推为临床性能。
- 融合权重只使用 train/dev qrels 选择，test qrels 仅用于最终报告；缺失任务不补值。
- 当前没有 CrossEncoder 真实结果；下载、运行和评测完成前不报告 reranker 提升。

## 可追溯产物

- `beir_scifact` / `project_bm25_tuned_v2`: `evaluation/public_benchmarks/runs/20260828T114348Z_beir_scifact`
- `beir_scifact` / `vnext_bge_small_en_v1_5`: `evaluation/public_benchmarks/runs/20260828T090914Z_beir_scifact`
- `beir_scifact` / `vnext_bm25_bge_fusion_v1`: `evaluation/public_benchmarks/runs/20260828T114348Z_beir_scifact`
- `beir_nfcorpus` / `project_bm25_tuned_v2`: `evaluation/public_benchmarks/runs/20260828T114506Z_beir_nfcorpus`
- `beir_nfcorpus` / `vnext_bge_small_en_v1_5`: `evaluation/public_benchmarks/runs/20260828T090951Z_beir_nfcorpus`
- `beir_nfcorpus` / `vnext_bm25_bge_fusion_v1`: `evaluation/public_benchmarks/runs/20260828T114506Z_beir_nfcorpus`
- `beir_scidocs` / `project_bm25_tuned_v2`: `evaluation/public_benchmarks/runs/20260828T114717Z_beir_scidocs`
- `beir_scidocs` / `vnext_bge_small_en_v1_5`: `evaluation/public_benchmarks/runs/20260828T092348Z_beir_scidocs`
- `beir_scidocs` / `vnext_bm25_bge_fusion_v1`: `evaluation/public_benchmarks/runs/20260828T114717Z_beir_scidocs`
- `beir_arguana` / `project_bm25_tuned_v2`: `evaluation/public_benchmarks/runs/20260828T115122Z_beir_arguana`
- `beir_arguana` / `vnext_bge_small_en_v1_5`: `evaluation/public_benchmarks/runs/20260828T093123Z_beir_arguana`
- `beir_arguana` / `vnext_bm25_bge_fusion_v1`: `evaluation/public_benchmarks/runs/20260828T115122Z_beir_arguana`
- `beir_fiqa` / `project_bm25_tuned_v2`: `evaluation/public_benchmarks/runs/20260828T120410Z_beir_fiqa`
- `beir_fiqa` / `vnext_bge_small_en_v1_5`: `evaluation/public_benchmarks/runs/20260828T085638Z_beir_fiqa`
- `beir_fiqa` / `vnext_bm25_bge_fusion_v1`: `evaluation/public_benchmarks/runs/20260828T120410Z_beir_fiqa`

## 限制

- 所有数值均从 `run.json` 读取；缺失结果保持缺失，没有估算或补值。
