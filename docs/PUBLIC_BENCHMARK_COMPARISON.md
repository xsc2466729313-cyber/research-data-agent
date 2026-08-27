# 分层公开评测对比结果

## 结论

目前已完成四层可复现的公开数据评测：检索、字段对齐、实体匹配和数据清洗。结果不能合成一个总分，因为四层解决的是不同问题，分数的分母也不同。

最重要的发现有三个：

1. 当前项目的离线哈希检索低于 BM25；这说明它还没有获得可靠的语义检索增益。
2. Valentine 字段对齐结果具有任务依赖性：教育任务中值形态规则找回全部 5 个映射，Capital Projects 中为 3/5 且有 1 个误匹配，因此仍需冲突检测与人工复核。
3. 在实体匹配的学术记录数据上，保守规则有较高 F1；但在商品记录数据上召回率明显不足。它不能直接迁移为患者或样本身份合并能力。

## 已完成测试

| 能力层 | 数据集与测试规模 | 当前项目/适配方法 | 对照方法 | 最关键结果 | 解读 |
|---|---:|---|---|---|---|
| 科学检索 | BEIR SciFact，300 queries | 哈希-词法混合检索 | BM25 | nDCG@10 0.4070 vs 0.6040 | 当前检索未超过关键词检索 |
| 医学检索 | BEIR NFCorpus，323 queries | 哈希-词法混合检索 | BM25 | nDCG@10 0.2493 vs 0.2899 | 医学检索同样需要正式嵌入模型 |
| 字段对齐 | Valentine Education COVID Meals，5 gold pairs | 字段名/值形态规则 | 精确字段名、Token Jaccard | F1 1.0000 vs 0.5714 | 值形态规则识别地址/城市/编号，避开 location→longitude 歧义 |
| 字段对齐 | Valentine Capital Projects，5 gold pairs | 字段名/值形态规则 | 精确字段名、Token Jaccard | F1 0.6667（3 TP、1 FP、2 FN） | 出现 1 个误匹配，不能自动发布 |
| 实体匹配 | DBLP-ACM，2,473 test pairs，444 positive | 可移植保守规则 | 标题精确匹配、标题 Jaccard | F1 0.9163 | 学术文献记录能利用题名、作者、年份等重复结构 |
| 实体匹配压力测试 | Walmart-Amazon，2,049 test pairs，193 positive | 可移植保守规则 | 标题精确匹配、标题 Jaccard | F1 0.4453，Recall 0.3161 | 商品标题格式变化大，规则漏掉 132/193 个正例 |
| 数据清洗 | HoloClean Hospital，1,000 rows，19,000 cells，509 dirty cells | 可移植共识规则 | 不修复、列众数修复 | F1 0.0000 | 保守规则没有产生自动修复；不能将其描述为已具备通用修复能力 |

“可移植”指为公开表格数据写的无领域知识适配器，用来检验项目规则设计能否迁移。它不是当前乳腺癌生产链路的患者/样本合并分数，也不是临床有效性分数。

## 检索层详细对比

| 数据集 | 方法 | nDCG@10 | Recall@100 | MRR@10 |
|---|---|---:|---:|---:|
| SciFact | BM25 | 0.6040 | 0.8279 | 0.5689 |
| SciFact | 项目哈希-词法混合检索 | 0.4070 | 0.7007 | 0.3833 |
| NFCorpus | BM25 | 0.2899 | 0.2209 | 0.5020 |
| NFCorpus | 项目哈希-词法混合检索 | 0.2493 | 0.1937 | 0.4417 |

## 字段对齐层详细对比

| 数据集 | 方法 | Precision | Recall | F1 | TP / FP / FN |
|---|---|---:|---:|---:|---:|
| Education COVID Meals | 精确字段名 | 1.0000 | 0.4000 | 0.5714 | 2 / 0 / 3 |
| Education COVID Meals | Token Jaccard | 1.0000 | 0.4000 | 0.5714 | 2 / 0 / 3 |
| Education COVID Meals | 字段名/值形态规则 | 1.0000 | 1.0000 | 1.0000 | 5 / 0 / 0 |
| Capital Projects | 精确字段名 | 1.0000 | 0.6000 | 0.7500 | 3 / 0 / 2 |
| Capital Projects | Token Jaccard | 1.0000 | 0.6000 | 0.7500 | 3 / 0 / 2 |
| Capital Projects | 字段名/值形态规则 | 0.7500 | 0.6000 | 0.6667 | 3 / 1 / 2 |

Valentine 已固定到 commit 5d5163f04da304985bd51a476ccf7653de3979c3，结果是通用字段对齐诊断，不是临床 Canonical Schema 映射能力的正式证明。教育任务包含 location→siteaddress 与 longitude 的公开歧义；Capital Projects 的 1 个假阳性说明生产链路必须保留候选、证据和 review 状态，并继续保留每个字段对齐的来源与原始值审计。

## 实体匹配层详细对比

| 数据集 | 方法 | Precision | Recall | F1 | TP / FP / FN |
|---|---|---:|---:|---:|---:|
| DBLP-ACM | 标题精确匹配 | 0.8679 | 0.9324 | 0.8990 | 414 / 63 / 30 |
| DBLP-ACM | 标题 Jaccard | 0.8580 | 0.9662 | 0.9089 | 429 / 71 / 15 |
| DBLP-ACM | 可移植保守规则 | 0.8555 | 0.9865 | 0.9163 | 438 / 74 / 6 |
| Walmart-Amazon | 标题精确匹配 | 1.0000 | 0.0466 | 0.0891 | 9 / 0 / 184 |
| Walmart-Amazon | 标题 Jaccard | 0.8462 | 0.1710 | 0.2845 | 33 / 6 / 160 |
| Walmart-Amazon | 可移植保守规则 | 0.7531 | 0.3161 | 0.4453 | 61 / 20 / 132 |

## 清洗层详细对比

| 数据集 | 方法 | Cell Precision | Cell Recall | Cell F1 | Repair Accuracy | TP / FP / FN |
|---|---|---:|---:|---:|---:|---:|
| Hospital | 不修复 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 / 0 / 509 |
| Hospital | 列众数修复 | 0.1137 | 0.0472 | 0.0667 | 0.0453 | 24 / 187 / 485 |
| Hospital | 可移植共识规则 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 / 0 / 509 |

这里的结论应当很严格：列众数修复虽然找回 24 个错误单元，但误改了 187 个正确单元，不能用于科研数据自动修复。项目的保守规则选择不自动修改，避免了误改，但也没有修复能力。后续应先做“检测 + 人工复核”，再逐步引入带可追溯证据的修复。

## 尚未产生分数的层

| 能力层 | 官方数据/框架 | 当前状态 | 原因 |
|---|---|---|---|
| 问题解析 | EBM-NLP | 未运行 | 需要把 Agent 的研究契约输出映射为 PICO spans，并严格区分训练与专业测试标签 |
| 工具规划 | BFCL V4 | 未运行 | 需要固定模型、工具集合和执行沙箱；它测的是函数调用，不是自由文本 |
| 正式 Raha + Baran | Raha/Baran | 未运行 | 当前 Windows/Python 3.14 下该旧版基线的多进程运行不兼容；不会将其论文结果抄作本项目对照成绩 |
| 端到端科研执行 | ScienceAgentBench verified | 未运行 | 官方数据有访问及再分发约束，需要按其流程取得数据 |
| Kaggle 工程任务 | MLE-bench Lite | 未运行 | Lite 约 158 GB，当前本机空间不满足 |

## 复现与证据

- python scripts/run_public_retrieval_benchmark.py --download
- python scripts/run_public_schema_benchmark.py --download
- python scripts/run_public_entity_benchmark.py --download
- python scripts/run_public_cleaning_benchmark.py --download

每次运行的 run.json 保存数据来源、SHA-256、执行代码版本和原始计数。数据文件不提交到 Git；评测结果和报告可提交，以便审查与复跑。

本次报告引用的最终运行产物为：

- 检索：`20260827T082234Z_beir_scifact`、`20260827T082239Z_beir_nfcorpus`
- 字段对齐：`20260827T105112Z_valentine_education_covid_meals`、`20260827T105112Z_valentine_capital_projects`
- 实体匹配：`20260827T103717Z_deepmatcher_dblp_acm`、`20260827T103717Z_deepmatcher_walmart_amazon`
- 数据清洗：`20260827T103716Z_holoclean_hospital`

每个目录内的 `run.json` 和 `REPORT.md` 是对应分数的直接证据；`unified_results.csv` 用于横向汇总。运行耗时受本机状态影响，只作为参考，不用于跨机器性能排名。
