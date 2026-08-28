# 最终评测报告（2026-08-28）

## 1. 评测范围

本报告分开报告三类证据：检索模型横向比较、查询理解自消融、任务级两轮闭环。它们使用不同评价对象，不能合并成一个 SDTI。

## 2. 检索模型横向比较

五个公开 BEIR 数据集：SciFact、NFCorpus、SciDocs、ArguAna、FiQA。相同语料、切分、top-100 和参数选择逻辑下：

| 方法 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 证据 |
| --- | ---: | ---: | ---: | --- |
| tuned BM25 | 0.3147 | 0.5552 | 0.3629 | `evaluation/vnext_retrieval_calibrated_macro_20260828.md` |
| BGE-small-en-v1.5 | 0.3880 | 0.6554 | 0.4421 | 同上 |
| BM25+BGE 校准融合 | 0.3791 | 0.6422 | 0.4277 | 同上 |

在这组检索层实验中，BGE 的 nDCG@10 高于 BM25；融合低于纯 BGE，因此当前没有把融合强行设为默认。这个结果不能外推为患者级临床效果。

## 3. 查询理解自消融

`evaluation/query_understanding/ablation_20260828.json` 使用同一 tuned BM25 完成 A/B：

| 方法 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟 |
| --- | ---: | ---: | ---: | ---: |
| A 原始 query | 0.314678 | 0.555205 | 0.362859 | 54.30 ms |
| B 规则 + RRF | 0.314664 | 0.553234 | 0.361934 | 115.79 ms |

B 相对 A 的 nDCG@10 为 `-0.000014`，且延迟增加约 `61.49 ms`，没有通过部署门槛。C 单改写、D 多查询、E 完整 Qwen 方案因没有真实结构化 Qwen 计划缓存，均为 `NOT_EVALUATED`。这不是失败隐藏，而是实验条件未满足。

## 4. 两轮闭环运行

`evaluation/closed_loop/live_two_round_smoke_20260828.json` 记录真实数据模式：两轮各 8 次工具调用，输入哈希不同，首轮和二轮 progress score 均为 `0.96`。它证明闭环执行和审计链路生效，但不是 Gold Set 分数，也没有声称二轮一定提高指标。

## 5. 模型对比状态

Qwen-plus、DeepSeek、GLM 的统一模型测试接口已接入；真正的横向语言模型比较必须满足同一问题集、同一数据权限、独立 API 会话、至少 3 次重复和冻结 Gold Set。当前已有 DeepSeek 作为独立评委的 3 案例运行：recall@3 `1.0`、nDCG@3 `0.754`、平均忠实度 `4.67/5`、关键说法支持率 `0.467`，但样本只有 3 个，不能作为模型排名。

## 6. 最终判断

- 已证实：BGE 检索层优于当前 tuned BM25；两轮闭环和安全审计可运行；前端已聚焦主要评委信息。
- 未证实：查询理解规则带来宏平均提升；Qwen/DeepSeek/GLM 谁在完整科研数据任务上最好；正式 Retrieval F1、Faithfulness、Repair Accuracy 和 SDTI。
- 生产建议：继续使用显式 `compat` 默认；在获得 Qwen 计划缓存和冻结乳腺癌 Gold Set 后，再运行 C/D/E 和多模型重复对照。
