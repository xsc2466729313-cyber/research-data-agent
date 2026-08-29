# 乳腺癌科研数据 Agent 分层评测与消融实验报告

> 生成时间：2026-08-29T18:51:35.322400+00:00。本报告是内部研发评测，不嵌入产品前端。所有数字来自已保存运行产物；缺失实验不推算。

## 1. 结论摘要

- 当前候选卷运行 `official-candidate-autonomous-v9-20260830` 的 SDTI 为 **100.00**，五个 SDTI 分量均达到目标。
- 同一 official_candidate 上，相对基线 `official-candidate-20260829T132222Z` 的 SDTI 从 **63.36** 变为 **100.00**。
- 当前运行安全门仍为 **REVIEW**，`publish_allowed=false`：有 9 个高风险问题未解决，且该卷不是 sealed frozen test。
- 公开检索能力层中，BGE 的宏平均 nDCG@10 为 **0.3880**，BM25 为 **0.3147**；这不是乳腺癌 SDTI。
- 开发集 12 个问题已全部纳入四类分层；分层结果用于发现泛化短板，不用候选卷 100 分覆盖这些较弱结果。

## 2. 评测范围与解释边界

| 层级 | 数据范围 | 用途 | 是否可作封存正式成绩 |
|---|---|---|---|
| official_candidate | retrieval 50 / field 26 / error 18 | 候选卷版本观察 | 否，`frozen=false` |
| development | 12 个问题、53 条检索判断 | 分层诊断与迭代 | 否 |
| BEIR | 5 个公开数据集、3,677 个查询 | 检索模块能力对照 | 否 |
| 规划模型替换 | 3 个病例 × 3 次 × 2 组 | 内部消融 | 否 |

## 3. 候选卷迭代前后

| 指标 | 基线 | 当前 | 变化 | 目标 |
|---|---:|---:|---:|---:|
| Retrieval Precision | 0.3548 | 1.0000 | +0.6452 | 0.9000 |
| Retrieval Recall | 0.6111 | 1.0000 | +0.3889 | 0.9000 |
| Retrieval F1 | 0.4490 | 1.0000 | +0.5510 | 0.9000 |
| Faithfulness | 0.6538 | 1.0000 | +0.3462 | 0.9500 |
| Traceability | 1.0000 | 1.0000 | +0.0000 | 1.0000 |
| Error Precision | 1.0000 | 1.0000 | +0.0000 | NOT_EVALUATED |
| Error Recall | 0.5333 | 1.0000 | +0.4667 | NOT_EVALUATED |
| Error F1 | 0.6957 | 1.0000 | +0.3043 | 0.9000 |
| Repair Accuracy | 0.5000 | 1.0000 | +0.5000 | 0.9000 |
| SDTI | 63.36 | 100.00 | +36.64 | 90.00 |

### 安全门与原始计数

- 安全门：`REVIEW`；允许自动发布：`false`。
- 检索：TP=18 / FP=0 / FN=0。
- 字段：Faithful=26/26；Traceable=26/26。
- 错误：TP=15 / FP=0 / FN=0；自动修复正确=3/3。
- 发布阻断：9 个高风险问题仍未解决。
- 发布阻断：尚未 sealed frozen_test，禁止当作冻结赛题自动发布。

## 4. Development 全量分层检索

| 分层 | 问题数 | 判断行数 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 临床结局 | 4 | 20 | 5 | 0 | 4 | 1.0000 | 0.5556 | 0.7143 |
| 患者分层 | 5 | 22 | 10 | 0 | 4 | 1.0000 | 0.7143 | 0.8333 |
| 知识与临床前 | 2 | 8 | 2 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| 表达发现 | 1 | 3 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| **合计** | **12** | **53** | **18** | **0** | **8** | **1.0000** | **0.6923** | **0.8182** |

## 5. 检索层对比：BM25、BGE 与融合

| 方法 | 数据集数 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟(ms) |
|---|---:|---:|---:|---:|---:|
| 调参 BM25 | 5 | 0.3147 | 0.5552 | 0.3629 | 54.57 |
| BGE-small-en-v1.5 | 5 | 0.3880 | 0.6554 | 0.4421 | 10.72 |
| BM25+BGE 融合 | 5 | 0.3791 | 0.6422 | 0.4277 | 62.73 |

### 按公开数据集分层

| 数据集 | 查询数 | BM25 nDCG@10 | BGE nDCG@10 | 融合 nDCG@10 | BGE 相对 BM25 |
|---|---:|---:|---:|---:|---:|
| SciFact | 300 | 0.6044 | 0.6803 | 0.6803 | +0.0759 |
| NFCorpus | 323 | 0.2902 | 0.3315 | 0.3318 | +0.0413 |
| SciDocs | 1000 | 0.1490 | 0.1910 | 0.1563 | +0.0420 |
| ArguAna | 1406 | 0.3067 | 0.3836 | 0.3741 | +0.0768 |
| FiQA | 648 | 0.2230 | 0.3533 | 0.3533 | +0.1304 |

## 6. 查询理解消融

| 变体 | 状态 | nDCG@10 | Recall@100 | MRR@10 | 平均延迟(ms) |
|---|---|---:|---:|---:|---:|
| `A_raw` | `EVALUATED` | 0.3147 | 0.5552 | 0.3629 | 54.30 |
| `B_rules` | `EVALUATED` | 0.3147 | 0.5532 | 0.3619 | 115.79 |
| `C_qwen_single` | `NOT_EVALUATED` | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED |
| `D_qwen_multi` | `NOT_EVALUATED` | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED |
| `E_rules_qwen` | `NOT_EVALUATED` | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED |

A_raw 与 B_rules 已完成；C/D/E 缺少真实结构化 Qwen 计划缓存，保持 `NOT_EVALUATED`。规则改写相对原始查询没有提升，因此未作为改进宣传。

## 7. 中间规划模型替换消融

| 组别 | 运行数 | Recall@3 | nDCG@3 | 平均延迟(ms) | 评审有效率 | 平均证据支持率 | 正式 SDTI |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen 中间智能体（对照组） | 9 | 0.6667 | 0.5436 | 43882.76 | 0.5556 | 0.6600 | `NOT_EVALUATED` |
| DeepSeek 替换中间智能体（实验组） | 9 | 1.0000 | 0.9444 | 19230.30 | 0.3333 | 0.7967 | `NOT_EVALUATED` |

DeepSeek 组在本次小样本检索排序上更高，但 Qwen 评审有效率更低；该消融不能推导通用模型排名，也不自动替换生产主链。

## 8. 未完成实验

| 实验 | 状态 | 原因 |
|---|---|---|
| Qwen 单查询改写 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |
| Qwen 多查询扩展 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |
| 规则 + Qwen 完整查询理解 | `NOT_EVALUATED` | 缺少同协议真实计划缓存 |
| sealed frozen test | `NOT_EVALUATED` | 当前 official_candidate 未冻结封存 |

## 9. 复现与产物

```powershell
.\.venv\Scripts\python.exe goldset\breast_cancer\official_candidate\collect_official_sdti.py --retrieval planner --evaluation-id official-candidate-autonomous-v9-20260830
.\.venv\Scripts\python.exe scripts\build_agent_stratified_ablation_report.py
```

- 当前候选卷：`data/output/evaluation/official-candidate-autonomous-v9-20260830/metrics.json`
- 报告 JSON：`evaluation/agent_stratified_ablation_20260829/report.json`
- 本报告：`evaluation/agent_stratified_ablation_20260829/report.md`
- 输入文件 SHA-256 已记录在 `report.json -> input_artifacts`。

## 10. 研究解释

候选卷上的满分说明当前确定性规划、字段规范化、错误检测和安全修复已覆盖该卷的已审核案例；它不证明对未见队列、未见字段或真实临床研究任务具有同等表现。开发集临床结局与患者分层仍有漏召回，规划模型替换评审也存在无效样本。后续应优先构建独立 sealed test，并扩大临床结局同域、HER2 IHC/ISH 与 ERBB2 CNA 区分、跨来源身份冲突等高风险分层。
