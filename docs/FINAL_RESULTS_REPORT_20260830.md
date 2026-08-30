# 结果报告（2026-08-30）

## 1. 结论先行

系统已经完成端到端主链、真实数据 Adapter、医学安全门、两轮缺口闭环、评测体系、Web 工作台和可追溯导出。当前效果可支持科研数据查找、整理、字段审计和独立队列验证，但还不能自动发布科研结论。

正式 `official_candidate` 观察分为 **SDTI 63.36**，目标 90 未达到；安全门 **FAIL**，`publish_allowed=false`。最主要短板是 Retrieval F1 0.449、Faithfulness 0.654 和 Repair Accuracy 0.500。

## 2. 正式指标结果

| 指标 | 当前值 | 目标 | 结论 |
|---|---:|---:|---|
| Retrieval Precision | 0.3548 | 0.90 | 未达标 |
| Retrieval Recall | 0.6111 | 0.90 | 未达标 |
| Retrieval F1 | 0.4490 | 0.90 | 未达标 |
| Faithfulness | 0.6538 | 0.95 | 未达标，触发红线 |
| Traceability | 1.0000 | 1.00 | 达标 |
| Error F1 | 0.6957 | 0.90 | 未达标 |
| Repair Accuracy | 0.5000 | 0.90 | 未达标 |
| **SDTI** | **63.36** | **90** | **未达标** |

评测卷包含 retrieval 50 条、field 26 条、error 18 条；`gold_set_id=breast-cancer-official-candidate-20260829`，checksum 为 `fa87a48ad1b9e90b0d2652b929499a2e4bec860245eabe9b4c70b78ce828a13c`。该卷由 xsc 审核，但 `frozen=false`，不是 sealed frozen test。

## 3. 代表性真实任务结果

任务：研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系。

| 观察 | 第一轮 | 第二轮 | 如何解释 |
|---|---:|---:|---|
| Progress score | 0.915 | 0.960 | 任务内诊断分，不是 SDTI |
| Required field coverage | 1.00 | 1.00 | 组合来源有字段，不等于同患者可 Join |
| Target match | 0.82 | 1.00 | 第二轮补充了目标验证来源 |
| Traceability | 1.00 | 1.00 | 任务内来源审计完整 |
| 数据行 | 141 | 141 | 第二轮没有伪造或重复扩表 |
| 未决 Gap | 2 | 2 | 核心跨队列问题仍存在 |
| 来源登记 | 63 | 68 | 增加 5 个验证来源 |

系统能够找到 GSE76360 的 50 个 baseline 样本及匹配 post 样本，其中 48/50 baseline 有 response，原始缺失率约 4%；该队列不含 PIK3CA。METABRIC/cBioPortal 可提供 PIK3CA 等分子变量，但没有与 GSE76360 患者可靠对应的 crosswalk，因此系统保持两个 cohort 独立，不生成伪患者联合表。

## 4. GitHub 同类方法公开实测

![GitHub 同类方法四模块对比](images/github-benchmark-summary.png)

| 功能 | 公共评测 | 本项目 | 对照方法 | 差值 |
|---|---|---:|---:|---:|
| 科学检索 nDCG@10 | BEIR 5 集 | 0.3791 | BGE 0.3880 | -0.0088 |
| 字段匹配 F1 | Valentine 10 任务 | 0.7994 | COMA 0.7670 | +0.0324 |
| 实体匹配 F1 | DeepMatcher 5 任务 | 0.7449 | RecordLinkage 0.7440 | +0.0009 |
| 错误单元检测 F1 | 共同 5 任务 | 0.5726 | Raha 子集 0.8159 | -0.2433 |

结论：字段匹配有明确优势；实体匹配宏平均基本持平；融合检索略低于纯 BGE；数据清洗检测是最主要模块短板，尤其 Rayyan 为 0、Flights 明显落后。四项指标来自不同任务，不能相加成总分。

## 5. 模型选择结果

小样本 3 题 x 3 次模型替换实验中，Qwen3.8-Max 的 Recall@3/MRR@3/nDCG@3 为 1.0000，DeepSeek 为 0.6667；DeepSeek 平均延迟更低且 Analysis Ready 比例更高。两组 18 次任务均为 REVIEW，因此当前生产继续使用 Qwen3.8-Max，DeepSeek 只保留为工程对照，不能据此形成通用模型排名。

## 6. 已完成与未完成

已完成：自然语言规划、真实多源取数、原始值保留、医学归一化、实体安全关联、Evidence、质量门、两轮闭环、导出、评测、界面和自动测试。

未完成：sealed frozen test、正式 SDTI 90、Faithfulness 红线解除、通用清洗检测增强、跨研究可靠患者级 crosswalk、生产级多实例状态存储。

## 7. 改进优先级

1. P0：补强 Retrieval Precision、Faithfulness 与安全 Repair，先解除正式安全门。
2. P0：对 Rayyan/Flights 增加跨列、缺失与语义异常检测，在独立验证集定阈值。
3. P1：按数据集验证 RRF 权重和 reranker，避免融合弱于 BGE 单路。
4. P1：扩大医学高风险字段和跨域实体测试，不放宽患者关联阈值。
5. P1：封存独立 frozen test，并完成高风险人工复核后再发布成绩。
