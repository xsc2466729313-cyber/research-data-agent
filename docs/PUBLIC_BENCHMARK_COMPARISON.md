# 分层公开基准横向对比（v2）

## 1. 结论先行

本轮在固定公开测试集上重跑了四个可执行能力层，并增加了两个只使用训练/开发数据拟合的升级方法。

- 问题解析：上下文词组证据使 EBM-NLP 宏平均 F1 从 0.4662 提升到 0.4900。
- 科学检索：调参 BM25 在 SciFact、NFCorpus、SciDocs、ArguAna、FiQA 上均不低于默认 BM25；哈希混合方法仍明显落后。
- 字段对齐：值分布画像方法在 Capital Projects、能源、公共艺术等任务上减少了列名歧义，10 个 Valentine 任务宏平均 F1 为 0.8451。
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

## 6. 复现命令

```powershell
python scripts/run_public_problem_benchmark.py --download
python scripts/run_public_retrieval_benchmark.py --download
python scripts/run_public_schema_benchmark.py --download
python scripts/run_public_entity_benchmark.py --download
python scripts/run_public_cleaning_benchmark.py --download
```

TREC-COVID 本轮未计入成绩：下载得到的 `.part` 文件不是完整压缩包，已保留为未完成状态。
