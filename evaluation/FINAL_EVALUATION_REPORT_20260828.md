# 最终评测报告（2026-08-28）

> 历史说明：本报告中的公开检索、查询理解和闭环数值仍可按各自运行产物复核。旧 DeepSeek Judge、三模型共识和 AI 代理 SDTI 流程已停用；当前生产、两轮闭环与辅助评审均使用 Qwen，DeepSeek 只用于独立的中间智能体替换消融。

## 1. 评测范围

本报告分开报告三类证据：检索模型横向比较、查询理解自消融、任务级两轮闭环。它们使用不同评价对象，不能合并成一个 SDTI。

## 2. 检索模型横向比较

五个公开 BEIR 数据集：SciFact、NFCorpus、SciDocs、ArguAna、FiQA。历史完整运行在相同语料、切分、top-100 和参数选择逻辑下：

| 方法 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 证据 |
| --- | ---: | ---: | ---: | --- |
| tuned BM25 | 0.3147 | 0.5552 | 0.3629 | `evaluation/vnext_retrieval_calibrated_macro_20260828.md` |
| **BGE-small-en-v1.5** | **0.3880** | **0.6554** | **0.4421** | 同上 |
| BM25+BGE 校准融合 | 0.3791 | 0.6422 | 0.4277 | 同上 |

在这组检索层实验中，BGE 的 nDCG@10 高于 BM25；融合低于纯 BGE，因此当前没有把融合强行设为默认。这个结果不能外推为患者级临床效果。

本轮另重跑 SciFact、NFCorpus、SciDocs、ArguAna 四个数据集（**3,029 个查询**）。**BGE nDCG@10 宏平均 `0.3966`**，tuned BM25 为 `0.3376`；融合为 `0.3856`。FiQA 在本轮资源窗口未完成，未计入本轮宏平均。逐数据集、样本量、延迟和运行 ID 见 `evaluation/PUBLIC_BENCHMARK_STRATIFIED_REPORT_20260828.md`。

## 3. 查询理解自消融

`evaluation/query_understanding/ablation_20260828.json` 使用同一 tuned BM25 完成 A/B：

| 方法 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟 |
| --- | ---: | ---: | ---: | ---: |
| **A 原始 query** | **0.314678** | **0.555205** | **0.362859** | 54.30 ms |
| B 规则 + RRF | 0.314664 | 0.553234 | 0.361934 | 115.79 ms |

B 相对 A 的 nDCG@10 为 **`-0.000014`**，且延迟增加约 **`61.49 ms`**，没有通过部署门槛。C 单改写、D 多查询、E 完整 Qwen 方案因没有真实结构化 Qwen 计划缓存，均为 **`NOT_EVALUATED`**。这不是失败隐藏，而是实验条件未满足。

## 4. 两轮闭环运行

`evaluation/closed_loop/live_two_round_smoke_20260828.json` 记录历史真实数据模式：两轮各 8 次工具调用，输入哈希不同，首轮和二轮 **progress score 均为 `0.96`**。本轮计划模式诊断 `evaluation/closed_loop/two_round_final_20260828.json` 在无真实数据输入时得到 `0.00 -> 0.00` 并保持 **`REVIEW`**，证明闭环不会将空计划伪装成改进。两者都不是 Gold Set 分数，也不证明二轮必然提高指标。

## 5. 模型对比状态

**Qwen-plus 已完成真实连接、鉴权和结构化 Agent 探测**，见 `evaluation/model_integration_probe_20260828.json`。此外，`evaluation/planner_replacement_ablation_20260829/` 已完成一次真实的中间智能体替换消融：生产路径、数据总结和辅助评审保持 Qwen，只把问题解析、规划和工具选择替换为 DeepSeek。3 条 provisional 乳腺癌题目各重复 3 次，两组均完成 9/9 次 Agent 运行。

| 角色 | 中间智能体 | Recall@3 | MRR@3 | nDCG@3 | 平均延迟 | Analysis Ready | 质量门 |
|---|---|---:|---:|---:|---:|---:|---|
| **生产对照组（本项目）** | **Qwen-plus** | **0.6667** | **0.5000** | **0.5436** | **43.88 s** | **66.67%** | **9/9 REVIEW** |
| 外部替换实验组 | DeepSeek Chat | 1.0000 | 0.9259 | 0.9444 | 19.23 s | 55.56% | 9/9 REVIEW |

DeepSeek 在该小样本的检索排名和延迟上更好，但差异主要由唯一一条 medium 题目产生；easy 与 hard 题两组 Recall@3 均为 1.0。Qwen 的 Analysis Ready 高 11.11 个百分点。两组均为 REVIEW，且题集未冻结，因此这不是正式模型排名。首次运行的 Qwen 辅助评审只有 Qwen 组 5/9、DeepSeek 组 3/9 成功解析；解析修复后的重跑又遇到 DashScope `Arrearage`，故不完整的 Judge 分不参与胜负判断。GLM 仍为 `NOT_EVALUATED`。

## 6. 最终判断

- 已证实：BGE 检索层在已报告公开运行中优于当前 tuned BM25；Qwen 本地结构化 Agent 探测通过；Qwen/DeepSeek 中间智能体替换脚本可运行；两轮闭环和安全审计可运行。
- 未证实：查询理解规则带来宏平均提升；Qwen/DeepSeek/GLM 谁在完整科研数据任务上最好；正式 Retrieval F1、Faithfulness、Repair Accuracy 和 SDTI。
- 生产建议：继续使用 Qwen 生产主链和显式 `compat` 默认；冻结乳腺癌 Gold Set、扩充题目并恢复完整 Qwen 辅助评审后，再形成正式模型排名。
