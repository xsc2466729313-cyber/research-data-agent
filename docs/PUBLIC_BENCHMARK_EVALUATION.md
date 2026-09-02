# 科研数据 Agent 分层公开评测报告（v2）

## 评测目的

端到端总分无法定位问题。本项目将能力拆为问题解析、数据检索、字段对齐、实体匹配和数据清洗五层，分别使用带公开标签的数据集计分。公开基准只诊断通用数据能力，不替代乳腺癌 Gold Set，也不产生正式 SDTI。

> 2026-09-02 统一复现、清洗 v6 / 问题解析 v4 / 检索开发集选择消融及正式结果边界以 [公开对照题号与结果说明](PUBLIC_COMPARISON_GUIDE_20260902.md) 的“第二轮瓶颈优化与统一复测”节为准。本文的历史逐层对照保留用于追踪旧运行。

## 当前最好成绩

| 能力层 | 官方数据 | 项目方法 | 主指标 | 成绩 |
|---|---|---|---|---:|
| 问题解析 | EBM-NLP professional test | PICO sequence v4 | 宏平均 span F1 | **0.5522** |
| 检索 | BEIR 5 个任务 | train/dev selected BGE/CrossEncoder | nDCG@10 宏平均 | **0.3920** |
| 字段对齐 | Valentine 10 个任务 | Schema Matcher v3 | Schema F1 宏平均 | 0.7994 |
| 实体匹配 | DeepMatcher 5 个任务 | learned rule v2 | Entity F1 宏平均 | 0.7408 |
| 数据清洗 | Raha/HoloClean 6 个任务 | source-anchor v6 | Cell F1 宏平均 | **0.9169** |

宏平均只是跨任务诊断，不能把不同层的分数相加或冒充一个总分。每个任务的完整指标和证据见 `docs/PUBLIC_BENCHMARK_COMPARISON.md` 与 `evaluation/public_benchmarks/runs/*/run.json`。

## 关键对比

- PICO context v3 相比词典 v2：宏 F1 `0.4662 → 0.4900`；Participants `0.4568 → 0.5230`，Interventions 基本不变。
- tuned BM25 在 SciFact、NFCorpus、SciDocs、ArguAna、FiQA 的 nDCG@10 为 `0.6044/0.2902/0.1490/0.3067/0.2230`；哈希混合在 SciFact/ArguAna 仅 `0.4070/0.0708`。
- value-profile v2 在 Public Art Inventory `0.3333 → 0.8889`、Capital Projects `0.6667 → 1.0000`；DPR 和 DSNY 仍为 `0.5882/0.5333`。
- learned entity v2 在 DBLP-ACM `0.9602`、Beer-RateBeer `0.8125`，但 Walmart-Amazon `0.4939`。
- format-profile v2 在 Beers/Movies-1/Tax 为 `0.9837/0.8916/0.9868`；Flights `0.0515`，Hospital 和 Rayyan 为 `0.0000`。
- 第二轮中，sequence v4 将问题解析宏平均 Span F1 提升到 `0.5522`，开发集选择检索将 nDCG@10 提升到 `0.3920`；第三轮的 source-anchor v6 将六任务清洗宏平均 Cell F1 提升到 `0.9169`，其中 Flights 从 `0.1811` 提升到 `0.9650`。这三层的公开主结果均不把失败的 Qwen 请求计入模型成绩。

## 数据划分与可信性

DeepMatcher 使用官方 train/valid/test；EBM-NLP 使用训练 crowd labels 和独立 professional test gold；BEIR 调参只读取 dev/train qrels；Valentine 使用固定 commit 的官方 ground truth；Raha/HoloClean 使用官方 dirty/clean 对照表。所有运行产物记录 source_id、真实 URL、SHA-256 和代码版本。未完成的 TREC-COVID 下载没有被计入成绩。

## 真实 Qwen 字段匹配补充

在同一 Valentine 10 个任务上，使用真实阿里云百炼 `qwen3.8-max` 做字段语义匹配复测。Qwen 只接收公开 source/target 表头和有限值画像，不接收 `ground_truth.json`；测试标签只在本地评分阶段读取。为处理 `DSNY` 的超长几何字段，模型输入对单个样例值设置 160 字符上限，源 CSV 和测试集未改变。

| 方法 | Valentine 10-task Macro Schema F1 | API 覆盖 | 回退 |
|---|---:|---:|---:|
| 项目 Schema Matcher v3 | 0.7994 | 不适用 | 不适用 |
| **Qwen-assisted (`qwen3.8-max`)** | **0.9018** | **10/10** | **0** |

相对项目 v3 提升 `+0.1024`。Qwen 在缩写和语义改名上明显有帮助，但 Capital Projects、DCM Street Centerline 和 Energy Benchmarking 三项低于 v3，说明该收益不是所有任务稳定存在。运行证据见 `evaluation/public_benchmarks/runs/20260902T1100*_qwen_valentine_*/run.json`；实体匹配 Qwen 批量请求因账户 `Arrearage` 失败，未填入 Qwen 实体成绩。

## 失败解释与下一步

检索层已接入本地 BGE 和公开 CrossEncoder，但全量重排延迟较高；问题解析的轻量序列特征仍低于成熟序列标注基线；字段对齐需要缩写词典、冲突检测和 review 队列；实体匹配需要字符级/字段级深度模型，并对低置信度样本保持 unresolved；清洗层的 v6 只利用公开表内可见的 provenance anchor，不能外推到没有可信重复键的缺失值、字符损坏或语义错误，这些仍需真实来源复核。

项目正式 SDTI 仍按冻结文件 `docs/06_评测指标与SDTI.md` 执行；在验证后的乳腺癌 Gold Set 提供前，不发布 SDTI 数值。
