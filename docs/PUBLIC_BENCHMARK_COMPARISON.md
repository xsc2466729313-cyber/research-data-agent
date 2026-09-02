# 分层公开基准横向对比（v2）

> 当前主报告已迁移到 [`evaluation/github_competitor_benchmark_20260830/report.md`](../evaluation/github_competitor_benchmark_20260830/report.md)。新报告使用同一公开数据、同一划分和同一指标，实际运行 GitHub 外部方法；本文保留为项目内部方法迭代记录。

> 2026-09-02 统一复现和优化结果以 [`PUBLIC_COMPARISON_GUIDE_20260902.md`](PUBLIC_COMPARISON_GUIDE_20260902.md) 的“本轮统一复现与优化”节为准。本文的 v2 数字保留为历史记录，不与当前 v4 清洗运行混用。

> 第二轮结果以 [`PUBLIC_COMPARISON_GUIDE_20260902.md`](PUBLIC_COMPARISON_GUIDE_20260902.md) 为准。本文另记录真实 Qwen 公开字段匹配复测；实体匹配因百炼账户在大批量运行时返回 `Arrearage`，不把确定性回退成绩写成 Qwen 成绩。

> **当前清洗更新（2026-09-02）**：source-anchor v6 已在同一官方 dirty/clean 测试上完成统一重跑，六任务宏平均 Cell F1 为 `0.9169`，替代本文历史 v5 清洗宏平均 `0.7863`。详细逐任务结果、代码规则和运行目录见 [`PUBLIC_COMPARISON_GUIDE_20260902.md`](PUBLIC_COMPARISON_GUIDE_20260902.md) 的“第三轮瓶颈修复”节；下文保留 v2/v4/v5 历史数字用于消融追踪。

## 1. 结论先行

本轮在固定公开测试集上重跑了四个可执行能力层，并增加了两个只使用训练/开发数据拟合的升级方法。

- 问题解析：上下文词组证据使 EBM-NLP 宏平均 F1 从 0.4662 提升到 0.4900。
- 科学检索：调参 BM25 在 SciFact、NFCorpus、SciDocs、ArguAna、FiQA 上均不低于默认 BM25；哈希混合方法仍明显落后。
- 字段对齐：值分布画像方法在 Capital Projects、能源、公共艺术等任务上减少了列名歧义，10 个 Valentine 任务宏平均 F1 为 0.8451。
- 真实 Qwen 字段对齐：同一 Valentine 测试集和官方 ground truth 下，Qwen-assisted 宏平均 F1 为 0.9018，较项目 Schema Matcher v3 的 0.7994 提升 0.1024；10/10 任务调用成功且无回退。
- 实体匹配：DBLP-ACM F1=0.9602，Fodors-Zagats F1=0.9000；Walmart-Amazon 只有 0.4939，商品标题变化仍是主要瓶颈。
- 数据清洗：Beers/Movies/Tax 等格式错误任务达到 0.8916–0.9868；Flights、Hospital、Rayyan 的缺失或语义错误不能仅靠表内格式安全修复。

这些分数是通用数据能力层诊断，不是乳腺癌临床有效性分数，也不构成冻结 Gold Set 的 SDTI 成绩。

## 2. 评测原则

所有成绩来自公开数据的官方测试划分或官方 ground truth。训练集/开发集只用于拟合参数；测试标签只在最终评分时读取。每个运行目录的 `run.json` 保存 `source_id`、来源 URL、数据哈希、代码版本和方法配置。原始公开数据不提交 Git。

## 3. 各层结果

### 3.1 问题解析：EBM-NLP

任务是把医学摘要中的 token 标为 Participants、Interventions、Outcomes。`project_pico_context_v3` 在训练集学习前后词组概率，未读取专业测试标签。

| 方法 | Participants F1 | Interventions F1 | Outcomes F1 | 宏平均 F1 |
|---|---:|---:|---:|---:|
| 训练词典 v1 | 0.3893 | 0.4030 | 0.3470 | 0.3798 |
| 项目词典 v2 | 0.4568 | 0.4485 | 0.4932 | 0.4662 |
| 项目上下文 v3 | 0.5230 | 0.4484 | 0.4986 | 0.4900 |

上下文证据主要改善 Participants；Interventions 几乎没有变化，说明仅靠局部 token 环境仍无法解决干预短语边界问题。

### 3.2 数据检索：BEIR

主指标为 nDCG@10，辅助指标为 Recall@100 和 MRR@10。所有方法使用相同 corpus、query 和 qrels。

| 数据集 | 查询数 | BM25 nDCG@10 | 调参 BM25 nDCG@10 | 项目哈希混合 nDCG@10 |
|---|---:|---:|---:|---:|
| SciFact | 300 | 0.6040 | 0.6044 | 0.4070 |
| NFCorpus | 323 | 0.2899 | 0.2902 | 0.2493 |
| SciDocs | 1,000 | 0.1490 | 0.1490 | 未计最终结果 |
| ArguAna | 1,406 | 0.3067 | 0.3067 | 0.0708 |
| FiQA | 648 | 0.2197 | 0.2230 | 0.0992 |

调参 BM25 的参数只在 dev/train qrels 上选择。当前哈希表示增加了计算，却没有形成可靠语义增益；后续应在相同测试集上接入科学/医学嵌入模型。

### 3.3 字段对齐：Valentine

Valentine 固定在 commit `5d5163f04da304985bd51a476ccf7653de3979c3`，使用官方 `ground_truth.json`。值画像 v2 增加有限值集合重叠和基数约束。

| 数据集 | Exact F1 | Token Jaccard F1 | 项目规则 v1 F1 | 值画像 v2 F1 |
|---|---:|---:|---:|---:|
| Education COVID Meals | 0.5714 | 0.5714 | 1.0000 | 1.0000 |
| Capital Projects | 0.7500 | 0.7500 | 0.6667 | 1.0000 |
| DCM Street Centerline | 0.8333 | 0.9231 | 0.9231 | 0.8333 |
| DPR Athletic Facilities | 0.4615 | 0.8235 | 0.7368 | 0.5882 |
| DSNY Disposal Assignments | 0.2222 | 0.5455 | 0.5333 | 0.5333 |
| Energy Benchmarking | 0.5714 | 0.7500 | 0.6667 | 1.0000 |
| Housing Maintenance | 0.8000 | 0.7273 | 0.6957 | 0.8571 |
| Public Art Inventory | 0.2353 | 0.3333 | 0.3333 | 0.8889 |
| Street Resurfacing | 0.5714 | 0.5714 | 0.5000 | 0.7500 |
| Swim for Life | 0.3333 | 0.8889 | 0.8000 | 1.0000 |
| **宏平均** | **0.5355** | **0.6882** | **0.6856** | **0.8451** |

DPR、DSNY 仍有许多缩写、布尔列和重复取值，自动匹配应保留候选与 review 状态。

#### 真实 Qwen 字段匹配复测（2026-09-02）

Qwen `qwen3.8-max` 只接收两张公开表的列名和截断后的值画像，不接收 `ground_truth.json`。官方测试标签仅由本地指标函数读取。为避免超长几何字段导致请求失败，送模型的每个值最多保留 160 个字符；原始 CSV、测试集和评分规则没有修改。

| 数据集 | Qwen-assisted F1 | 项目 Schema Matcher v3 F1 | 变化 | Qwen 调用/回退 |
|---|---:|---:|---:|---:|
| Education COVID Meals | 1.0000 | 0.7500 | +0.2500 | 1/0 |
| Capital Projects | 0.8889 | 1.0000 | -0.1111 | 1/0 |
| DCM Street Centerline | 0.8333 | 0.8571 | -0.0238 | 1/0 |
| DPR Athletic Facilities | 0.9474 | 0.5185 | +0.4288 | 1/0 |
| DSNY Disposal Assignments | 0.7500 | 0.6316 | +0.1184 | 1/0 |
| Energy Benchmarking | 0.8889 | 1.0000 | -0.1111 | 1/0 |
| Housing Maintenance | 0.9091 | 0.8571 | +0.0520 | 1/0 |
| Public Art Inventory | 0.8000 | 0.7407 | +0.0593 | 1/0 |
| Street Resurfacing | 1.0000 | 0.7500 | +0.2500 | 1/0 |
| Swim for Life | 1.0000 | 0.8889 | +0.1111 | 1/0 |
| **宏平均** | **0.9018** | **0.7994** | **+0.1024** | **10/0** |

提升主要来自缩写、字段后缀和跨表语义重命名；Capital Projects、DCM、Energy 的下降说明通用大模型并非每个任务都优于值画像规则。逐任务运行证据保存在 `evaluation/public_benchmarks/runs/20260902T1100*_qwen_valentine_*/`。

### 3.4 实体匹配：DeepMatcher

使用官方 train/valid/test 划分。项目 v2 的权重和阈值只在 train/valid 上选择。

| 数据集 | Exact F1 | Title Jaccard F1 | 项目规则 v1 F1 | 项目学习规则 v2 F1 |
|---|---:|---:|---:|---:|
| DBLP-ACM | 0.8990 | 0.9089 | 0.9163 | 0.9602 |
| Beer-RateBeer | 0.4444 | 0.5263 | 0.6667 | 0.8125 |
| Fodors-Zagats | 0.8421 | 0.8421 | 0.9268 | 0.9000 |
| Amazon-Google | 0.0545 | 0.2268 | 0.3489 | 0.5375 |
| Walmart-Amazon | 0.0891 | 0.2845 | 0.4453 | 0.4939 |
| **宏平均** | **0.4658** | **0.5577** | **0.6608** | **0.7408** |

Walmart-Amazon 的 v2 Precision=0.4636、Recall=0.5285；不能把商品记录规则匹配能力外推成患者身份合并能力，生产链路必须继续执行 unresolved/review。

本轮尝试用 Qwen 对 DeepMatcher 官方测试对做完整批量判定，但百炼在第一次完整任务中返回 `Arrearage`，2,049/2,049 对均按预设规则回退，审计为 `86` 次失败、`0` 个 Qwen 判定。因此该运行只证明失败可追溯，**不提供 Qwen 实体 F1**，也不把回退的 `0.4453` 写成 Qwen 成绩。实体层当前公开可发布观察仍是项目 v2 宏平均 `0.7408` 对 RecordLinkage `0.7440`，提升路径是获得稳定余额后重跑完整五任务，而不是用缺失 API 的回退结果冒充提升。

### 3.5 数据清洗：Raha/HoloClean

指标是错误单元 Cell F1 和 Repair Accuracy。格式画像 v2 只修复高置信度的数字、单位、缺失标记、时间和 city/state 表示错误。

| 数据集 | 错误单元数 | 不修复 F1 | 列众数 F1 | 格式画像 F1 | Repair Accuracy |
|---|---:|---:|---:|---:|---:|
| HoloClean Hospital | 509 | 0.0000 | 0.0667 | 0.0000 | 0.0000 |
| Raha Beers | 4,362 | 0.0000 | 0.0000 | 0.9837 | 1.0000 |
| Raha Flights | 4,920 | 0.0000 | 0.0000 | 0.0515 | 0.6500 |
| Raha Movies-1 | 7,675 | 0.0000 | 0.0002 | 0.8916 | 0.9701 |
| Raha Rayyan | 948 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Raha Tax | 121,219 | 0.0000 | 0.0000 | 0.9868 | 0.9951 |

Hospital、Flights、Rayyan 的剩余错误主要是字符替换、缺失值恢复或日期语义重排，不能从单表格式唯一推断。列众数在 Hospital 找回 24 个错误单元，却误改 187 个正确单元。

## 4. 模型选择与失败边界

BM25 是当前透明、可复现的词法下界；哈希混合方法在 SciFact 上比 BM25 低 0.1970 nDCG，在 ArguAna 上低 0.2359。字段值画像能减少列名歧义，但 DPR/DSNY 的重复值仍会制造冲突。实体层必须在高 Precision 和高 Recall 之间设置 unresolved 区间。清洗层对格式错误自动修复，对缺失和语义错误检测后复核，避免用高 Repair Accuracy 掩盖低 Cell F1。

## 5. 与项目正式 SDTI 的关系

本报告没有生成 SDTI。只有通过项目验证的乳腺癌 Gold Set 才能计算正式 SDTI；公开 Benchmark 只用于定位通用能力短板。

## 6. 真实 Qwen 公开测试补充

已在 BEIR SciFact 官方测试集 300 个查询上实际调用 `qwen3.8-max` 进行查询改写，并使用相同 BM25 索引和官方测试 qrels 评分。BM25 的 nDCG@10 / Recall@100 / MRR@10 为 `0.6040 / 0.8279 / 0.5689`；Qwen 查询改写加 BM25（含原查询回退）为 `0.6453 / 0.8519 / 0.6103`，对应变化为 `+0.0413 / +0.0240 / +0.0415`。

该运行 300 次 API 调用中 264 个查询获得 Qwen 改写，36 个查询因阿里云真实返回 `Arrearage` 而回退原查询，因此这是含回退的 Qwen-assisted 结果，不是纯 Qwen 全覆盖成绩。运行产物为 `evaluation/public_benchmarks/runs/20260902T103645Z_qwen_public_benchmark/`，其中保存了数据哈希、模型名、失败原因和逐项结果。EBM-NLP 和 Raha/HoloClean 的 Qwen 全量结果暂不填入本报告，直到获得有余额的 API 账户并完成完整测试覆盖。

## 7. 复现命令

```powershell
python scripts/run_public_problem_benchmark.py --download
python scripts/run_public_retrieval_benchmark.py --download
python scripts/run_public_schema_benchmark.py --download
python scripts/run_public_entity_benchmark.py --download
python scripts/run_public_cleaning_benchmark.py --download
```

TREC-COVID 本轮未计入成绩：下载得到的 `.part` 文件不是完整压缩包，已保留为未完成状态。
