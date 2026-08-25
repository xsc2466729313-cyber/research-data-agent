# 02 Benchmark、Baseline 与下载链接

> 本文件尽量选择官方论文仓库/作者仓库。第三方数据的许可证和再分发要求请以各仓库说明为准。

## A. 数据清洗

### Benchmark / Framework

1. Raha + Baran
- Repo: https://github.com/BigDaMa/raha
- 说明：仓库自带 datasets；支持 dirty/clean Benchmark；可直接 `pip install raha`。
- 推荐：Hospital、Flights、Beers、Rayyan、Movies。

2. HoloClean
- Repo: https://github.com/HoloClean/holoclean
- Hospital dirty:
  https://github.com/HoloClean/holoclean/blob/master/testdata/hospital.csv
- Hospital clean:
  https://github.com/HoloClean/holoclean/blob/master/testdata/hospital_clean.csv
- 注意：依赖 PostgreSQL，环境较老，推荐使用 Docker/REIN 隔离运行。

3. Cocoon
- Repo: https://github.com/Cocoon-Data-Transformation/cocoon
- 安装：`pip install cocoon_data -U`
- 论文/结果可用于参考 Hospital/Flights/Beers/Rayyan/Movies 上的 F1 对比。

4. REIN
- Repo: https://github.com/mohamedyd/rein-benchmark
- 用途：统一跑多种 error detection / repair 方法；包含错误注入、鲁棒性、可扩展性实验。
- 推荐将你自己的 Agent 接入 REIN harness。

5. LAED（可选，LLM-Agent 数据错误检测）
- Repo: https://github.com/wangpy-gz/LAED
- 包含 hospital / flights / beers / rayyan / movies 的 aligned dirty-clean pairs。
- 支持 Qwen API，适合作为“LLM agent baseline”补充。

### 最终推荐 Baseline
必须：
- Raha + Baran
- HoloClean
- Cocoon
- Our Agent

可选：
- LAED
- ED2

---

## B. 科学检索

### BEIR
- Repo: https://github.com/beir-cellar/beir
- Datasets: https://github.com/beir-cellar/beir/wiki/Datasets-available

### SciFact
直接下载：
https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip

特点：
- 约 300 test queries
- 约 5K corpus
- 科学论文/事实检索，最适合作为主 Benchmark。

### NFCorpus
直接下载：
https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip

特点：
- 323 test queries
- 约 3.6K corpus
- 生物医学/营养检索，适合作为医学域补充。

### Baselines

1. BM25
- 直接使用 BEIR lexical evaluator。
- BEIR 示例：
  https://github.com/beir-cellar/beir/blob/main/examples/retrieval/evaluation/lexical/evaluate_bm25.py

2. Contriever / Contriever-MS MARCO
- Repo: https://github.com/facebookresearch/contriever
- 支持直接跑 BEIR。

3. BGE-M3
- Repo: https://github.com/FlagOpen/FlagEmbedding
- Model: BAAI/bge-m3
- 推荐 dense 或 hybrid；必须在报告里写清使用模式。

4. Our Agent
- 必须把 Agent 的输出统一适配为 `{query_id: {doc_id: score}}`，然后用同一个 BEIR evaluator 算 nDCG@10。

---

## C. Schema Matching

### Valentine
- 当前 Repo: https://github.com/delftdata/valentine
- Docs: https://delftdata.github.io/valentine/
- 原实验套件 tag:
  https://github.com/delftdata/valentine/tree/v1.1
- 原论文实验数据 archive:
  https://surfdrive.surf.nl/files/index.php/s/QU5oxyNMuVguEku
- Data Fabricator:
  https://github.com/delftdata/valentine-data-fabricator

### Baseline
Valentine 当前实现可直接跑：
- JaccardDistanceMatcher
- COMA
- Cupid
- DistributionBased
- SimilarityFlooding

推荐正式表：
Jaccard / COMA / Cupid / Our Agent。

---

## D. Entity Matching

### DeepMatcher
- Repo: https://github.com/anhaidgroup/deepmatcher
- Dataset page:
  https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md

推荐数据：

#### DBLP-ACM（优先）
- Domain：bibliographic / 学术记录
- 12,363 labeled pairs
- 2,220 positive
- Download:
  https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/DBLP-ACM/dblp_acm_exp_data.zip

#### Walmart-Amazon（压力测试）
- 10,242 labeled pairs
- 962 positive
- Download:
  https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Walmart-Amazon/walmart_amazon_exp_data.zip

#### Dirty DBLP-ACM（可选）
https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Dirty/DBLP-ACM/dirty_dblp_acm_exp_data.zip

### Baselines

1. DeepMatcher
https://github.com/anhaidgroup/deepmatcher

2. Ditto
https://github.com/megagonlabs/ditto

3. Simple Fuzzy/Rule Baseline
自己实现 exact ID + normalized string similarity，作为低门槛基线。

4. Our Agent Entity Matcher

---

## E. 科研适用性评价参考

### ScienceAgentBench
- Repo:
  https://github.com/OSU-NLP-Group/ScienceAgentBench
- 2026 已发布 verified 版本。
- 102 个来自 44 篇同行评议论文的科研任务。
- 重要：完整 benchmark 有特殊下载/再分发约束，按官方说明获取，不应放进公开压缩包。
- 用途：参考“真实论文任务 + task-specific evaluator/rubric”的评测思想，不建议直接把它的分数与本项目 Fitness Score 硬比较。

### ScholarQABench / OpenScholar
- ScholarQABench:
  https://github.com/AkariAsai/ScholarQABench
- OpenScholar:
  https://github.com/AkariAsai/OpenScholar
- 用途：参考 expert rubric、citation/evidence evaluation 和科研问题的多维评价。

### 你的 Domain Benchmark
建议建立 20–30 个 paper-grounded 乳腺癌科研数据任务：
- 每条任务绑定论文/数据 accession
- 任务在运行前生成并冻结 Evaluation Contract
- 所有 baseline 使用同一 Contract
- 最后比较 Mean Fitness / Win Rate / Gate Pass Rate

这部分是“方法创新与域内横向对比”，不是外部 leaderboard。
