# 科研数据 Agent 分层公开评测报告（v2）

## 评测目的

端到端总分无法定位问题。本项目将能力拆为问题解析、数据检索、字段对齐、实体匹配和数据清洗五层，分别使用带公开标签的数据集计分。公开基准只诊断通用数据能力，不替代乳腺癌 Gold Set，也不产生正式 SDTI。

## 当前最好成绩

| 能力层 | 官方数据 | 项目方法 | 主指标 | 成绩 |
|---|---|---|---|---:|
| 问题解析 | EBM-NLP professional test | PICO context v3 | 宏平均 span F1 | 0.4900 |
| 检索 | BEIR 5 个任务 | tuned BM25 v2 | nDCG@10 宏平均 | 0.3147 |
| 字段对齐 | Valentine 10 个任务 | value-profile v2 | Schema F1 宏平均 | 0.8451 |
| 实体匹配 | DeepMatcher 5 个任务 | learned rule v2 | Entity F1 宏平均 | 0.7408 |
| 数据清洗 | Raha/HoloClean 6 个任务 | format-profile v2 | Cell F1 宏平均 | 0.4856 |

宏平均只是跨任务诊断，不能把不同层的分数相加或冒充一个总分。每个任务的完整指标和证据见 `docs/PUBLIC_BENCHMARK_COMPARISON.md` 与 `evaluation/public_benchmarks/runs/*/run.json`。

## 关键对比

- PICO context v3 相比词典 v2：宏 F1 `0.4662 → 0.4900`；Participants `0.4568 → 0.5230`，Interventions 基本不变。
- tuned BM25 在 SciFact、NFCorpus、SciDocs、ArguAna、FiQA 的 nDCG@10 为 `0.6044/0.2902/0.1490/0.3067/0.2230`；哈希混合在 SciFact/ArguAna 仅 `0.4070/0.0708`。
- value-profile v2 在 Public Art Inventory `0.3333 → 0.8889`、Capital Projects `0.6667 → 1.0000`；DPR 和 DSNY 仍为 `0.5882/0.5333`。
- learned entity v2 在 DBLP-ACM `0.9602`、Beer-RateBeer `0.8125`，但 Walmart-Amazon `0.4939`。
- format-profile v2 在 Beers/Movies-1/Tax 为 `0.9837/0.8916/0.9868`；Flights `0.0515`，Hospital 和 Rayyan 为 `0.0000`。

## 数据划分与可信性

DeepMatcher 使用官方 train/valid/test；EBM-NLP 使用训练 crowd labels 和独立 professional test gold；BEIR 调参只读取 dev/train qrels；Valentine 使用固定 commit 的官方 ground truth；Raha/HoloClean 使用官方 dirty/clean 对照表。所有运行产物记录 source_id、真实 URL、SHA-256 和代码版本。未完成的 TREC-COVID 下载没有被计入成绩。

## 失败解释与下一步

检索层应接入科学/医学文本嵌入和重排；问题解析需要序列标注以识别短语边界；字段对齐需要缩写词典、冲突检测和 review 队列；实体匹配需要字符级/字段级深度模型，并对低置信度样本保持 unresolved；清洗层应把检测和修复分开，对缺失值和语义错误交由证据复核。

项目正式 SDTI 仍按冻结文件 `docs/06_评测指标与SDTI.md` 执行；在验证后的乳腺癌 Gold Set 提供前，不发布 SDTI 数值。
