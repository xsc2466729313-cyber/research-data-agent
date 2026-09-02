# 公开数据集统一对照报告

更新时间：2026-09-02  
范围：公开能力层诊断，不是乳腺癌临床有效性，也不替代冻结 SDTI。

## 1. 结论

本报告把问题解析、科学检索、字段匹配、实体匹配和数据清洗放在同一份证据索引中。每层仍使用自己的官方数据、官方测试划分和通用指标；不同层的分数不相加，也不合成为“系统准确率”。测试集、测试标签和评价公式均未修改，参数只在训练集、开发集或脏表自身的无标签证据上确定。

| 能力层 | 公开数据与测试划分 | 当前方法 | 核心指标 | 当前真实结果 | 可复现证据 |
|---|---|---|---|---:|---|
| 问题解析 | EBM-NLP `professional_test_gold` | PICO sequence v4 | Macro span F1 | **0.5522** | `evaluation/public_benchmarks/runs/20260902T063818Z_ebm_nlp_2_00/run.json` |
| 科学检索 | BEIR 五任务 test | 开发集选择 BGE/CrossEncoder | Macro nDCG@10 | **0.3920** | `evaluation/public_benchmarks/runs/20260902T060718Z_beir_scifact` 等 |
| 字段匹配 | Valentine 10 个任务官方 ground truth | Qwen-assisted | Macro Schema F1 | **0.9018** | `evaluation/public_benchmarks/runs/20260902T110023Z_qwen_valentine_education_covid_meals` 等 |
| 实体匹配 | DeepMatcher 五任务官方 test | learned entity rule v2 | Macro Entity F1 | **0.7408** | `evaluation/github_competitor_benchmark_20260830/results.json` |
| 数据清洗 | Raha/HoloClean 六任务 aligned dirty/clean | source-anchor v6 | Macro Cell F1 | **0.9169** | `evaluation/public_benchmarks/runs/20260902T130928Z_holoclean_hospital` 等 |

字段匹配的 Qwen 结果是十个任务完整成功的真实 API 条件实验；问题解析和清洗的全量 Qwen 公开运行没有形成可发布成绩，因此不把回退结果写成 Qwen 分数。检索另有 SciFact API 条件实验，见第 5 节。

## 2. 数据、基线与公平口径

| 层 | 数据来源 | 公开/通用对照 | 评价规则 |
|---|---|---|---|
| 问题解析 | [EBM-NLP](https://github.com/bepnye/EBM-NLP)，archive SHA-256 `b7357503911ba9f708d04e24c1ab3fe9e0a79833910e53e2472ed21214a44e3f` | 同一训练数据上的词典和上下文消融；本轮没有把未实际运行的 BioBERT/SciBERT 数字写入 | Participants、Interventions、Outcomes token span Precision/Recall/F1，测试 gold 仅评分时读取 |
| 检索 | [BEIR](https://github.com/beir-cellar/beir)，SciFact、NFCorpus、SciDocs、ArguAna、FiQA | BM25、BGE-small-en-v1.5、公开 CrossEncoder | nDCG@10 为主，Recall@100、MRR@10 为辅；有 dev/train 才选择重排，无 dev 固定 BGE |
| 字段匹配 | [Valentine](https://github.com/delftdata/valentine)，固定 commit `5d5163f04da304985bd51a476ccf7653de3979c3` | Valentine COMA | Schema F1；Qwen 只接收表头和值画像，不接收 ground truth |
| 实体匹配 | [DeepMatcher datasets](https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md) | RecordLinkage Jaro-Winkler + logistic | Entity F1；训练/验证用于阈值选择，官方 test 只在评分阶段读取 |
| 清洗 | [Raha](https://github.com/BigDaMa/raha)、[HoloClean](https://github.com/HoloClean/holoclean) testdata | Raha 1.26 PVD+RVD subset | Cell F1 和 Repair Accuracy；项目 v6 只看 dirty 表内 source-anchor，不读取 clean 表 |

所有运行均记录 `source_id`、真实来源、数据哈希和代码版本。原始公开数据不提交仓库。

## 3. 问题解析：EBM-NLP

### 3.1 消融结果

| 方法 | Participants F1 | Interventions F1 | Outcomes F1 | Macro F1 |
|---|---:|---:|---:|---:|
| 训练词典 v1 | 0.3893 | 0.4030 | 0.3470 | 0.3798 |
| 项目词典 v2 | 0.4568 | 0.4485 | 0.4932 | 0.4662 |
| 上下文 v3 | 0.5230 | 0.4484 | 0.4986 | 0.4900 |
| **序列特征 v4** | **0.5931** | **0.4660** | **0.5975** | **0.5522** |

v4 相对 v3 提升 `+0.0622`，但 Interventions 只提升 `+0.0177`，是主要瓶颈。EBM-NLP 测的是医学摘要 token span，不是普通问答或 ResearchSpec JSON 的字段准确率。当前方法仍是训练集词组证据、左右上下文和短 gap 边界特征，没有医学预训练序列标注器；干预常以复合短语、剂量、疗程、比较句和否定句出现，局部词特征很难确定完整边界。这个原因解释了为什么项目真实使用千问时体验可能更好，但公开测试中的规则方法分数仍偏低。

## 4. 科学检索：BEIR

### 4.1 统一测试结果

| 数据集 | 查询数 | BGE nDCG@10 | 优化后 nDCG@10 | BGE Recall@100 | 优化后 Recall@100 | BGE MRR@10 | 优化后 MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | 300 | 0.6803 | **0.6872** | 0.9383 | 0.9383 | 0.6499 | **0.6585** |
| NFCorpus | 323 | 0.3315 | **0.3450** | 0.2975 | 0.2975 | 0.5257 | **0.5587** |
| SciDocs | 1,000 | 0.1910 | 0.1910 | 0.4312 | 0.4312 | 0.3351 | 0.3351 |
| ArguAna | 1,406 | 0.3836 | 0.3836 | 0.9687 | 0.9687 | 0.2601 | 0.2601 |
| FiQA | 648 | 0.3533 | 0.3533 | 0.6413 | 0.6413 | 0.4396 | 0.4396 |
| **宏平均** | **3,677** | **0.3880** | **0.3920** | **0.6554** | **0.6554** | **0.4421** | **0.4504** |

优化策略只在有 train/dev qrels 的任务上选择 CrossEncoder，否则固定 BGE；没有按测试题挑方法。相对 BGE，nDCG@10 提升 `+0.0041`，MRR@10 提升 `+0.0083`，Recall@100 不变。代价是平均查询延迟约 `171 ms/query`，显著高于 BGE 单路约 `7.7 ms/query`。

### 4.2 为什么科学检索仍然低

BEIR 五任务不是单一医学检索集：SciDocs 的论文关系和 ArguAna 的论证关系对语义匹配要求更高；当前 BGE 是轻量通用英文嵌入，不是医学领域检索模型；BM25 又会受到同义词、缩写和词面不一致影响。CrossEncoder 只重排候选集，不能修复候选召回不足，而且在 SciDocs、ArguAna 上没有稳定收益。因此当前结果是“接近通用强基线、局部领先”，不是全面超过专门化公开模型。

## 5. 真实 Qwen API 条件实验

### 5.1 SciFact 查询改写

在同一 SciFact test、同一 BM25 索引和同一 `qrels/test.tsv` 上，Qwen 只看到查询文本，不看到相关性标签。`qwen3.8-max` 查询改写加 BM25 的真实结果如下：

| 方法 | API 调用 | 成功改写 | nDCG@10 | Recall@100 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0 | - | 0.6040 | 0.8279 | 0.5689 |
| Qwen rewrite + BM25（失败请求原查询回退） | 300 | 264 | **0.6453** | **0.8519** | **0.6103** |

相对 BM25 分别提升 `+0.0413`、`+0.0240`、`+0.0415`。该结果来自 `evaluation/public_benchmarks/runs/20260902T103645Z_qwen_public_benchmark/run.json`；36 次 API 请求返回账户欠费错误并回退原查询，因此应标为“Qwen-assisted with fallback”，不能解释为 300 条纯 Qwen 全覆盖。

### 5.2 问题解析与清洗 API 状态

问题解析全量运行 `20260902T125235Z_qwen_public_benchmark` 仅 `1/36` 批成功，其余为网络协议或输出结构失败；清洗 API 试跑未完成六任务覆盖。这些运行只作为失败审计，不计入主结果。原因是 API 可用性和结构化输出稳定性不足，不是把失败回退包装成模型能力。充值后仍应先进行小批量健康检查，再决定是否支付全量运行成本。

## 6. 字段匹配与实体匹配

### 6.1 字段匹配：Valentine

| 数据集 | 项目 Schema v3 | Qwen-assisted | 变化 |
|---|---:|---:|---:|
| Education COVID Meals | 0.7500 | 1.0000 | +0.2500 |
| Capital Projects | 1.0000 | 0.8889 | -0.1111 |
| DCM Street Centerline | 0.8571 | 0.8333 | -0.0238 |
| DPR Athletic Facilities | 0.5185 | 0.9474 | +0.4288 |
| DSNY Disposal Assignments | 0.6316 | 0.7500 | +0.1184 |
| Energy Benchmarking | 1.0000 | 0.8889 | -0.1111 |
| Housing Maintenance | 0.8571 | 0.9091 | +0.0520 |
| Public Art Inventory | 0.7407 | 0.8000 | +0.0593 |
| Street Resurfacing | 0.7500 | 1.0000 | +0.2500 |
| Swim for Life | 0.8889 | 1.0000 | +0.1111 |
| **宏平均** | **0.7994** | **0.9018** | **+0.1024** |

Qwen 对缩写、后缀和语义改名有明显帮助，但三个任务下降，说明不能宣称“API 在所有任务最优”。医学字段仍需规则和 review，特别是 HER2/ERBB2 等不同测量维度。

### 6.2 实体匹配：DeepMatcher

| 数据集 | 项目 learned rule v2 | RecordLinkage 对照 | 差值 |
|---|---:|---:|---:|
| Amazon-Google | 0.5551 | 0.3532 | +0.2019 |
| Beer-RateBeer | 0.8125 | 0.7273 | +0.0852 |
| DBLP-ACM | 0.9632 | 0.9689 | -0.0057 |
| Fodors-Zagats | 0.9000 | 1.0000 | -0.1000 |
| Walmart-Amazon | 0.4939 | 0.6708 | -0.1769 |
| **宏平均** | **0.7449** | **0.7440** | **+0.0009** |

项目方法在 Amazon-Google、Beer-RateBeer 上更好，但在 Walmart-Amazon 明显落后，所以实体层只能结论为宏平均基本持平。通用商品/论文实体匹配不能外推患者身份合并；生产规则仍要求同研究命名空间、低置信度 `review/unresolved` 和冲突拒绝自动合并。

## 7. 数据清洗：Raha/HoloClean

### 7.1 v5 到 v6 消融

| 数据集 | v5 Cell F1 | v6 Cell F1 | v6 Repair Accuracy | Raha PVD+RVD 对照 |
|---|---:|---:|---:|---:|
| Hospital | 0.8947 | 0.8947 | 1.0000 | 0.6724 |
| Beers | 0.9837 | 0.9837 | 1.0000 | 0.9834 |
| Flights | 0.1811 | **0.9650** | 0.9903 | 0.8235 |
| Movies-1 | 0.8916 | 0.8916 | 0.9701 | 0.8097 |
| Rayyan | 0.7797 | 0.7797 | 0.7987 | 0.7908 |
| Tax | 0.9867 | 0.9867 | 0.9948 | 未完成 |
| **六任务宏平均** | **0.7863** | **0.9169** | - | - |

v6 仅利用 dirty 表中的 `flight`、`src`、重复键和同组唯一非空值，未读取 clean 表。Flights 从 `0.1811` 提升到 `0.9650`，证明可验证 provenance anchor 对特定错误类型有效；Rayyan 的字符损坏和缺失语义信息没有足够表内证据，因此保留 review，不猜测。

## 8. 论文可引用的综合分析

公开测试支持三点结论。第一，数据处理收益最明显：来源锚点把清洗六任务宏平均从 `0.7863` 提高到 `0.9169`。第二，Qwen 在已完成的字段匹配和 SciFact 查询改写条件实验中有明显收益，但 API 稳定性、成本和回退覆盖必须单独审计。第三，问题解析和检索的低分有明确技术边界：前者缺少医学序列标注模型并受干预短语边界影响，后者受到领域差异、候选召回和轻量嵌入模型限制。论文应客观写成“在字段语义改名、特定来源锚定清洗和 SciFact 查询改写上具有优势；在通用复杂检索、干预 span 边界和商品实体匹配上未达到最优”。

## 9. 复现入口

```powershell
python scripts/run_public_problem_benchmark.py --download
python scripts/run_public_retrieval_benchmark.py --download
python scripts/run_public_schema_benchmark.py --download
python scripts/run_public_entity_benchmark.py --download
python scripts/run_public_cleaning_benchmark.py --download
```

机器可读索引见 [`PUBLIC_DATASET_COMPARISON_20260902.json`](PUBLIC_DATASET_COMPARISON_20260902.json)，逐次运行证据见 `evaluation/public_benchmarks/runs/`。本报告不包含任何硬编码测试答案，也没有修改冻结 Schema、医学规则或评价公式。
