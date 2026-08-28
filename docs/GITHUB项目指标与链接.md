# GitHub 对比项目、评测指标与链接

> 更新日期：2026-08-28
>
> 本文汇总本项目评测方案中涉及的 GitHub 项目、对应能力层、评测指标和项目链接。公开基准分数用于诊断通用数据能力，不等同于乳腺癌临床效果、患者身份合并效果或正式 SDTI 成绩。

## 1. 快速清单

| 能力层 | GitHub 项目 | 对比用途 | 主指标 | 项目链接 |
|---|---|---|---|---|
| 数据清洗 | Raha + Baran | 错误单元检测与修复 | Cell-level F1、Repair Accuracy | [BigDaMa/raha](https://github.com/BigDaMa/raha) |
| 数据清洗 | HoloClean | 概率图模型数据清洗基线 | Cell-level F1、Repair Accuracy | [HoloClean/holoclean](https://github.com/HoloClean/holoclean) |
| 数据清洗 | Cocoon | 数据清洗与修复结果参考 | F1、Precision、Recall | [Cocoon-Data-Transformation/cocoon](https://github.com/Cocoon-Data-Transformation/cocoon) |
| 数据清洗 | REIN | 多种错误检测/修复方法统一基准 | Detection F1、Repair Accuracy、鲁棒性 | [mohamedyd/rein-benchmark](https://github.com/mohamedyd/rein-benchmark) |
| 数据清洗 | LAED | LLM-Agent 数据错误检测基线 | F1、Precision、Recall | [wangpy-gz/LAED](https://github.com/wangpy-gz/LAED) |
| 科学检索 | BEIR | 统一检索数据集与评测框架 | nDCG@10、Recall@100、MRR@10 | [beir-cellar/beir](https://github.com/beir-cellar/beir) |
| 科学检索 | Contriever | 无监督/预训练密集检索基线 | nDCG@10、Recall@100、MRR@10 | [facebookresearch/contriever](https://github.com/facebookresearch/contriever) |
| 科学检索 | BGE / FlagEmbedding | 中文/多语言密集检索或混合检索基线 | nDCG@10、Recall@100、MRR@10 | [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) |
| Schema Matching | Valentine | 异构表字段匹配基准与算法参考 | Schema Precision、Recall、F1 | [delftdata/valentine](https://github.com/delftdata/valentine) |
| Entity Matching | DeepMatcher | 结构化实体匹配公开数据集与深度模型参考 | Entity Precision、Recall、F1 | [anhaidgroup/deepmatcher](https://github.com/anhaidgroup/deepmatcher) |
| Entity Matching | Ditto | Transformer 实体匹配基线 | Entity Precision、Recall、F1 | [megagonlabs/ditto](https://github.com/megagonlabs/ditto) |

## 2. 数据清洗对比

### 2.1 项目和链接

| 项目 | 主要用途 | 推荐数据集/资料 | 链接 |
|---|---|---|---|
| Raha + Baran | 检测 dirty cell，并与 clean table 对照 | Hospital、Flights、Beers、Rayyan、Movies | [GitHub 仓库](https://github.com/BigDaMa/raha) |
| HoloClean | 使用概率推理进行错误检测和修复 | Hospital dirty/clean | [GitHub 仓库](https://github.com/HoloClean/holoclean)；[Hospital dirty](https://github.com/HoloClean/holoclean/blob/master/testdata/hospital.csv)；[Hospital clean](https://github.com/HoloClean/holoclean/blob/master/testdata/hospital_clean.csv) |
| Cocoon | 数据转换和清洗方法参考 | Hospital、Flights、Beers、Rayyan、Movies | [GitHub 仓库](https://github.com/Cocoon-Data-Transformation/cocoon) |
| REIN | 统一运行多种错误检测/修复方法 | 多数据集、错误注入、鲁棒性和扩展性 | [GitHub 仓库](https://github.com/mohamedyd/rein-benchmark) |
| LAED | LLM-Agent 数据错误检测 | Hospital、Flights、Beers、Rayyan、Movies | [GitHub 仓库](https://github.com/wangpy-gz/LAED) |

### 2.2 指标

- `Cell-level Precision`：被判为错误的单元格中，实际错误单元格的比例。
- `Cell-level Recall`：真实错误单元格中，被正确检测出来的比例。
- `Cell-level F1`：Cell-level Precision 与 Recall 的调和平均，是本层主指标。
- `Repair Accuracy`：被系统修复的单元格中，修复结果等于 Ground Truth 的比例。
- `Latency`：单次运行或单元格/记录级平均耗时，需同时说明统计口径。

### 2.3 本项目已记录的公开基准结果

| 数据集 | 不修复 F1 | 列众数 F1 | 项目格式画像 F1 | Repair Accuracy |
|---|---:|---:|---:|---:|
| HoloClean Hospital | 0.0000 | 0.0667 | 0.0000 | 0.0000 |
| Raha Beers | 0.0000 | 0.0000 | 0.9837 | 1.0000 |
| Raha Flights | 0.0000 | 0.0000 | 0.0515 | 0.6500 |
| Raha Movies-1 | 0.0000 | 0.0002 | 0.8916 | 0.9701 |
| Raha Rayyan | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Raha Tax | 0.0000 | 0.0000 | 0.9868 | 0.9951 |

上述数值来自本项目的公开基准重跑。它们不是 Raha、HoloClean 或 Cocoon 官方 leaderboard 分数，也不能直接解释为医学数据清洗准确率。Hospital、Flights 和 Rayyan 中的缺失恢复、字符替换和语义错误不能仅靠单表格式安全推断，生产系统应进入 review。

## 3. 科学检索对比

### 3.1 项目和链接

| 项目 | 主要用途 | 链接 |
|---|---|---|
| BEIR | 提供异构信息检索 benchmark、数据集和统一 evaluator | [GitHub 仓库](https://github.com/beir-cellar/beir)；[数据集列表](https://github.com/beir-cellar/beir/wiki/Datasets-available) |
| Contriever | 密集向量检索基线，可运行 BEIR | [GitHub 仓库](https://github.com/facebookresearch/contriever) |
| BGE / FlagEmbedding | BGE 系列 embedding、reranker 和检索工具 | [GitHub 仓库](https://github.com/FlagOpen/FlagEmbedding) |
| BM25 官方示例 | BEIR 词法检索基线 | [BM25 评测示例](https://github.com/beir-cellar/beir/blob/main/examples/retrieval/evaluation/lexical/evaluate_bm25.py) |

### 3.2 指标

- `nDCG@10`：前 10 条结果的归一化折损累计增益，是本层主指标，越高越好。
- `Recall@100`：前 100 条结果覆盖相关文档的比例，用于衡量召回完整性。
- `MRR@10`：第一个相关文档排名倒数的平均值，用于衡量首个有效结果出现得有多早。
- `Latency/query`：每个查询的平均检索耗时。

### 3.3 本项目已记录的 BEIR 结果

| 方法 | 数据集数 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 平均查询延迟 |
|---|---:|---:|---:|---:|---:|
| 调参 BM25 | 5 | 0.3147 | 0.5552 | 0.3629 | 54.57 ms |
| BGE-small-en-v1.5 | 5 | 0.3880 | 0.6554 | 0.4421 | 10.72 ms |
| BM25 + BGE Fusion | 5 | 0.3791 | 0.6422 | 0.4277 | 62.73 ms |

五个数据集的 nDCG@10 如下：

| 数据集 | 查询数 | 默认 BM25 | 调参 BM25 | 项目哈希混合 |
|---|---:|---:|---:|---:|
| SciFact | 300 | 0.6040 | 0.6044 | 0.4070 |
| NFCorpus | 323 | 0.2899 | 0.2902 | 0.2493 |
| SciDocs | 1,000 | 0.1490 | 0.1490 | 未计最终结果 |
| ArguAna | 1,406 | 0.3067 | 0.3067 | 0.0708 |
| FiQA | 648 | 0.2197 | 0.2230 | 0.0992 |

BGE 和融合结果来自本项目 VNext 检索实验。当前没有 Contriever、BGE-M3 或 CrossEncoder 的完整同环境真实结果，因此不能把这些 GitHub 项目的理论能力写成已完成对照成绩。

## 4. Schema Matching 对比

### 4.1 项目和链接

| 项目 | 主要用途 | 相关算法/资料 | 链接 |
|---|---|---|---|
| Valentine | 异构表字段匹配 benchmark 和实验套件 | Jaccard、COMA、Cupid、DistributionBased、SimilarityFlooding | [GitHub 仓库](https://github.com/delftdata/valentine)；[官方文档](https://delftdata.github.io/valentine/)；[v1.1 实验套件](https://github.com/delftdata/valentine/tree/v1.1) |
| Valentine Data Fabricator | 生成和管理字段匹配实验数据 | Valentine 实验数据构造 | [GitHub 仓库](https://github.com/delftdata/valentine-data-fabricator) |

### 4.2 指标

- `Schema Precision`：系统预测为匹配的字段对中，正确字段对的比例。
- `Schema Recall`：Ground Truth 中正确字段对被找出的比例。
- `Schema F1`：Schema Precision 与 Recall 的调和平均，是本层主指标。
- `Runtime`：完成一次字段匹配任务的运行时间。

### 4.3 本项目已记录结果

| 方法 | 任务数 | Precision 宏平均 | Recall 宏平均 | F1 宏平均 |
|---|---:|---:|---:|---:|
| 项目值画像规则 v2 | 10 | 0.9286 | 0.7864 | 0.8451 |
| 项目特征融合 v3 | 10 | 0.8648 | 0.7724 | 0.7994 |

项目值画像规则 v2 当前作为默认 Schema Matcher。v3 在该十任务运行中 F1 低于 v2 `0.0457`，所以保留为实验路径，没有切换默认实现。

## 5. Entity Matching 对比

### 5.1 项目和链接

| 项目 | 主要用途 | 推荐数据/资料 | 链接 |
|---|---|---|---|
| DeepMatcher | 结构化实体匹配模型和公开数据集 | DBLP-ACM、Walmart-Amazon、Beer-RateBeer、Fodors-Zagats、Amazon-Google | [GitHub 仓库](https://github.com/anhaidgroup/deepmatcher)；[数据集说明](https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md) |
| Ditto | 基于 Transformer 的实体匹配基线 | 可作为 DeepMatcher 数据集的模型对照 | [GitHub 仓库](https://github.com/megagonlabs/ditto) |

公开数据下载链接：

- [DBLP-ACM 数据集](https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/DBLP-ACM/dblp_acm_exp_data.zip)
- [Walmart-Amazon 数据集](https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Walmart-Amazon/walmart_amazon_exp_data.zip)
- [Dirty DBLP-ACM 数据集](https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Dirty/DBLP-ACM/dirty_dblp_acm_exp_data.zip)

### 5.2 指标

- `Entity Precision`：预测为同一实体的记录对中，真实匹配记录对的比例。
- `Entity Recall`：Ground Truth 匹配记录对中，被找出的比例。
- `Entity F1`：Entity Precision 与 Recall 的调和平均，是本层主指标。
- `Mean latency/pair`：平均每个候选记录对的匹配耗时。

### 5.3 本项目已记录结果

| 方法 | 任务数 | Precision 宏平均 | Recall 宏平均 | F1 宏平均 |
|---|---:|---:|---:|---:|
| 项目学习规则 v2 | 5 | 0.7259 | 0.7668 | 0.7408 |
| 项目实体匹配 v3（固定阈值） | 5 | 0.5860 | 0.4514 | 0.4883 |
| 项目实体匹配 v3（训练/验证集校准） | 5 | 0.5251 | 0.6229 | 0.5579 |

典型任务 F1：

| 数据集 | Exact Title | Title Jaccard | 项目规则 v1 | 项目学习规则 v2 |
|---|---:|---:|---:|---:|
| DBLP-ACM | 0.8990 | 0.9089 | 0.9163 | 0.9602 |
| Beer-RateBeer | 0.4444 | 0.5263 | 0.6667 | 0.8125 |
| Fodors-Zagats | 0.8421 | 0.8421 | 0.9268 | 0.9000 |
| Amazon-Google | 0.0545 | 0.2268 | 0.3489 | 0.5375 |
| Walmart-Amazon | 0.0891 | 0.2845 | 0.4453 | 0.4939 |

这里的公开实体匹配结果不能外推为患者身份合并能力。乳腺癌生产链路仍必须执行患者/样本关联置信度、跨研究检查和 unresolved/review 安全策略；低置信度关联不得自动合并。

## 6. 科研 Agent 评价参考项目

以下项目用于参考科研任务、证据和专家评价设计，不与本项目固定 SDTI 或 Fitness Score 直接合并比较：

| 项目 | 参考方向 | 链接 |
|---|---|---|
| ScienceAgentBench | 真实论文科研任务、任务级 evaluator/rubric | [OSU-NLP-Group/ScienceAgentBench](https://github.com/OSU-NLP-Group/ScienceAgentBench) |
| ScholarQABench | 科研问答、专家 rubric 和证据评价 | [AkariAsai/ScholarQABench](https://github.com/AkariAsai/ScholarQABench) |
| OpenScholar | 科研检索、回答和 citation/evidence 评价参考 | [AkariAsai/OpenScholar](https://github.com/AkariAsai/OpenScholar) |

## 7. 本项目核心指标与 GitHub 对照层的关系

GitHub 公开项目主要支撑通用能力层对比；本项目乳腺癌科研数据智能体的正式评价还必须使用冻结 Gold Set 和医学安全门：

| 项目核心能力 | 正式指标 | GitHub/公开基准对应参考 |
|---|---|---|
| 找得准 | Retrieval Precision、Recall、F1 | BEIR 的 nDCG@10、Recall@100、MRR@10 |
| 找得全 | Retrieval Recall | BEIR 的 Recall@100 |
| 整得真 | Faithfulness | 公开清洗/匹配指标只能作通用能力参考，不能替代医学 Evidence 核验 |
| 查得回 | Traceability | 公开 benchmark 通常不覆盖 source_id、raw_field、raw_value 和 Evidence 链路 |
| 改得对 | Error F1、Repair Accuracy | Raha/HoloClean/Cocoon 的 Cell F1、Repair Accuracy |
| 综合可信度 | SDTI | 只能由经过验证并冻结的乳腺癌 Gold Set 计算 |

## 8. 结果使用边界

1. `Cell F1`、`Schema F1`、`Entity F1` 和 `nDCG@10` 是不同能力层的指标，不能直接相加或合并成一个总分。
2. Entity Matching 公开数据集上的分数不能解释为患者身份匹配准确率。
3. 细胞系药敏 `AUC/IC50` 与患者临床 `pCR/response` 必须通过 `response_domain` 区分。
4. HER2 IHC 2+ 不得直接自动判定为 HER2 Positive；ERBB2 CNA amplification 也不等同于 HER2 IHC positive。
5. 没有真实运行产物、来源记录和冻结评价协议的项目，只能作为参考链接，不能填入正式成绩表。

## 9. 本地来源

- [分层公开基准横向对比](./PUBLIC_BENCHMARK_COMPARISON.md)
- [Benchmark、Baseline 与下载链接](../evaluation_toolkit/docs/02_Benchmark与Baseline链接.md)
- [统一评价体系 v2](./UNIFIED_EVALUATION_SYSTEM_V2.md)
- [评测与 SDTI](./EVALUATION_SDTI.md)
