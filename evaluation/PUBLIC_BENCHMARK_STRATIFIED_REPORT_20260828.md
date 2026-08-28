# 公开数据集分层对比报告（2026-08-28）

## 结论范围

本报告回答的是“检索层在公开数据集上的可复现实测表现”。它不代表乳腺癌临床有效性、完整 Agent 能力，也不产生冻结公式定义的 SDTI。所有指标均来自 BEIR 官方 test qrels；BM25 调参和融合权重只读取 train/dev qrels。

本次重跑完成了 4 个数据集、4 种方法，共 3,029 个测试查询：SciFact（300）、NFCorpus（323）、SciDocs（1,000）、ArguAna（1,406）。FiQA（648）在本次资源窗口内未完成，因此没有被纳入本次宏平均；仓库中的 FiQA 旧运行仅作为历史参考单列。

## 本轮逐数据集分层结果

指标定义：nDCG@10 衡量前 10 位排序质量，Recall@100 衡量前 100 位覆盖率，MRR@10 衡量首个相关文档位置；延迟为本地 CPU 运行的平均毫秒/查询。`n` 为 test qrels 中实际评测查询数。

| 数据集（n） | 方法 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟 ms/查询 | 本轮 run |
|---|---|---:|---:|---:|---:|---|
| SciFact (300) | BM25 local reference | 0.6040 | 0.8279 | 0.5689 | 5.49 | `20260828T153046Z_beir_scifact` |
| SciFact (300) | Project BM25 tuned v2 | 0.6044 | 0.8284 | 0.5685 | 5.56 | `20260828T153046Z_beir_scifact` |
| SciFact (300) | VNext BGE-small-en-v1.5 | 0.6803 | 0.9383 | 0.6499 | 7.52 | `20260828T153046Z_beir_scifact` |
| SciFact (300) | VNext BM25+BGE fusion | 0.6803 | 0.9383 | 0.6499 | 13.89 | `20260828T153046Z_beir_scifact` |
| NFCorpus (323) | BM25 local reference | 0.2899 | 0.2209 | 0.5020 | 0.94 | `20260828T153112Z_beir_nfcorpus` |
| NFCorpus (323) | Project BM25 tuned v2 | 0.2902 | 0.2206 | 0.5061 | 0.95 | `20260828T153112Z_beir_nfcorpus` |
| NFCorpus (323) | VNext BGE-small-en-v1.5 | 0.3315 | 0.2975 | 0.5257 | 4.16 | `20260828T153112Z_beir_nfcorpus` |
| NFCorpus (323) | VNext BM25+BGE fusion | 0.3318 | 0.2975 | 0.5273 | 4.98 | `20260828T153112Z_beir_nfcorpus` |
| SciDocs (1,000) | BM25 local reference | 0.1490 | 0.3372 | 0.2661 | 33.16 | `20260828T153317Z_beir_scidocs` |
| SciDocs (1,000) | Project BM25 tuned v2 | 0.1490 | 0.3372 | 0.2661 | 32.64 | `20260828T153317Z_beir_scidocs` |
| SciDocs (1,000) | VNext BGE-small-en-v1.5 | 0.1910 | 0.4312 | 0.3351 | 4.90 | `20260828T153317Z_beir_scidocs` |
| SciDocs (1,000) | VNext BM25+BGE fusion | 0.1563 | 0.3581 | 0.2763 | 37.94 | `20260828T153317Z_beir_scidocs` |
| ArguAna (1,406) | BM25 local reference | 0.3067 | 0.9054 | 0.1983 | 56.63 | `20260828T153814Z_beir_arguana` |
| ArguAna (1,406) | Project BM25 tuned v2 | 0.3067 | 0.9054 | 0.1983 | 54.91 | `20260828T153814Z_beir_arguana` |
| ArguAna (1,406) | VNext BGE-small-en-v1.5 | 0.3836 | 0.9687 | 0.2601 | 16.59 | `20260828T153814Z_beir_arguana` |
| ArguAna (1,406) | VNext BM25+BGE fusion | 0.3741 | 0.9758 | 0.2454 | 73.50 | `20260828T153814Z_beir_arguana` |

## 四数据集宏平均（本轮）

宏平均先对每个数据集等权，再平均，不按查询量加权。

| 方法 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟 ms/查询 | 相对 tuned BM25 的 nDCG |
|---|---:|---:|---:|---:|---:|
| BM25 local reference | 0.3374 | 0.5729 | 0.3838 | 24.05 | -0.1% |
| Project BM25 tuned v2 | 0.3376 | 0.5729 | 0.3847 | 23.51 | 基线 |
| VNext BGE-small-en-v1.5 | 0.3966 | 0.6589 | 0.4427 | 8.29 | +17.5% |
| VNext BM25+BGE fusion | 0.3856 | 0.6424 | 0.4247 | 32.58 | +14.2% |

逐数据集看，BGE 在四个数据集的 nDCG@10 均高于 tuned BM25；融合在 SciDocs 上低于纯 BGE，在其余三个数据集仍高于 tuned BM25。融合 Recall@100 在 ArguAna 达到 0.9758，但延迟较高。结果支持将 BGE 作为公开检索诊断中的强候选，同时保留 BM25 作为低成本生产默认，直到完成更大规模资源评测和乳腺癌 Gold Set 验证。

## FiQA 状态

FiQA 本次重跑未完成，原因是本地资源窗口不足，未生成新的完整 run。仓库中最近的历史运行 `20260828T120410Z_beir_fiqa` 只包含 tuned BM25（nDCG@10 0.2230）和 BM25+BGE fusion（0.3533），没有本次四方法统一重跑的证据；因此这些数值不参与上面的本轮宏平均，也不用于宣称“本轮五数据集完成”。

## 证据与复现

每个 run 目录包含 `run.json`、`unified_results.csv` 和 `REPORT.md`，记录数据集来源 URL、语料/查询/qrels SHA-256、代码版本和评测范围。数据集定义见 `configs/public_benchmarks.yaml`；执行命令为：

```powershell
python scripts/run_public_retrieval_benchmark.py `
  --dataset beir_scifact --dataset beir_nfcorpus --dataset beir_scidocs `
  --dataset beir_arguana --dataset beir_fiqa `
  --method bm25 --method project_bm25_tuned_v2 `
  --method vnext_semantic --method vnext_hybrid
```

交叉编码器方法已实现批量重排接口并有回归测试，但本次大规模运行在 FiQA 之前未完成，故不报告其公开数据集成绩。正式临床结论仍需乳腺癌冻结 Gold Set、医学安全门和完整证据链评测。
