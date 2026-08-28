# VNext Retrieval 五组公开 Benchmark 汇总

> 仅为检索层 BEIR test 指标，不是临床有效性、全 Agent 质量或 SDTI 成绩。

| 方法 | 数据集数 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 平均查询延迟 |
|---|---:|---:|---:|---:|---:|
| Tuned BM25 | 5 | 0.3147 | 0.5552 | 0.3629 | 50.68 ms |
| VNext BGE-small-en-v1.5 | 5 | 0.3880 | 0.6554 | 0.4421 | 10.72 ms |
| VNext BM25+BGE Fusion | 4 | 0.3646 | 0.6126 | 0.4040 | 41.93 ms |

## 结论

- BGE 在五个已完成可比的公开任务上均高于 tuned BM25 的 nDCG@10；提升幅度因任务而异，不能外推为临床性能。
- 固定 0.55/0.45 融合在 SciFact、NFCorpus、SciDocs、ArguAna 均低于纯 BGE，因此暂不把融合设为默认主策略。
- 当前没有 CrossEncoder 真实结果；下载、运行和评测完成前不报告 reranker 提升。

## 可追溯产物

- `beir_scifact`: `evaluation/public_benchmarks/runs/20260828T090914Z_beir_scifact`
- `beir_nfcorpus`: `evaluation/public_benchmarks/runs/20260828T090951Z_beir_nfcorpus`
- `beir_scidocs`: `evaluation/public_benchmarks/runs/20260828T092348Z_beir_scidocs`
- `beir_arguana`: `evaluation/public_benchmarks/runs/20260828T093123Z_beir_arguana`
- `beir_fiqa`: `evaluation/public_benchmarks/runs/20260828T085638Z_beir_fiqa`

## 限制

- FiQA 的 BGE 结果来自已完成的独立配置，Fusion 未完成，不纳入 Fusion 宏平均。
- 所有数值均从 `run.json` 读取；缺失结果保持缺失，没有估算或补值。
