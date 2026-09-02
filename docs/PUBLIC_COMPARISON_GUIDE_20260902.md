# 公开对照题号与结果说明

更新时间：2026-09-02  
数据依据：历史对照 `evaluation/github_competitor_benchmark_20260830/results.json`；增强检索运行摘要 `evaluation/public_benchmarks/enhanced_retrieval_20260902.json`

## 先说清楚：原问题没有被替换

本文保留原始科研问题 **RQ-01**：

> 在 HER2 阳性乳腺癌中，PIK3CA 突变是否与新辅助治疗响应相关？

RQ-01 是一个患者/样本级医学研究问题，必须在同一研究或可靠 crosswalk 中同时具备 HER2、PIK3CA、治疗阶段和患者响应。公开通用数据集不能直接回答这个问题，只能拆开检查系统的四项通用能力。图 `public-comparison-question-map-20260902.png` 专门说明了这层关系。

## 对照题号

| 题号 | 从原问题拆出的能力问题 | 公开数据与指标 | **本项目方法** | **公开对照方法** | 该题能说明什么 |
|---|---|---|---|---|---|
| `PB-01` | 能否把相关材料排到前十？ | BEIR 5 个数据集；nDCG@10 | **BGE 初检索 + CrossEncoder 重排** | **BGE-small-en-v1.5 单路** | 检查候选材料排序，不证明乳腺癌来源完整 |
| `PB-02` | 两张表的不同列名是否表示同一字段？ | Valentine 10 个任务；Schema F1 | **Qwen-assisted Schema Matcher V3** | **Valentine COMA** | 检查字段语义对齐，不证明医学字段可直接合并 |
| `PB-03` | 两条记录是否指向同一个实体？ | DeepMatcher 5 个任务；Entity F1 | **本项目自适应实体融合** | **RecordLinkage Jaro-Winkler + logistic** | 检查通用记录匹配，不证明患者身份可以自动合并 |
| `PB-04` | 能否找出错误单元且不误伤正确值？ | Raha/HoloClean 6 个任务；Cell F1 | **source-anchor v6 清洗方法** | **Raha PVD+RVD** | 检查表格错误检测，不证明医学缺失值可以安全猜测 |

`PB-01`—`PB-04` 是模块题，不是四道新的乳腺癌临床题。规划模型替换实验和正式候选卷另列为工程诊断，分别说明模型规划能力和完整数据链表现。

## 宏平均总览

| 公开题号 | 本项目 | 公开对照 | 谁更高 | 真实解释 |
|---|---:|---:|---|---|
| `PB-01` 科学检索 | **0.3920** | 0.3880 | **本项目高 0.0041** | 当前方法在 BGE 初检索后增加 CrossEncoder 重排，前排排序有所改善 |
| `PB-02` 字段匹配 | **0.9018** | 0.7670 | **本项目高 0.1348** | 千问对缩写、后缀和语义改名有明显帮助，部分列类型仍需规则复核 |
| `PB-03` 实体匹配 | **0.7449** | 0.7440 | **本项目高 0.0009** | 宏平均基本持平；Walmart-Amazon 仍明显落后，不能放宽患者关联门槛 |
| `PB-04` 错误检测 | **0.9169** | 分任务报告 | 本项目在六任务宏平均上形成完整结果 | source-anchor v6 对具有重复来源锚点的错误收益明显，Rayyan 仍保留人工复核 |

这四项结果分别衡量检索、字段、实体和清洗能力，不合成为一个总排名。完整逐题图见：

- [公开能力对照总览](images/public-comparison-scorecard-20260902.png)
- [PB-01 科学检索逐题图](images/public-retrieval-datasets-20260902.png)
- [PB-02 字段匹配逐题图](images/public-schema-datasets-20260902.png)
- [PB-03 实体匹配逐题图](images/public-entity-datasets-20260902.png)
- [PB-04 错误检测逐题图](images/public-cleaning-datasets-20260902.png)
- [公开对照失败原因地图](images/public-comparison-failure-map-20260902.png)
- [原问题与对照题号关系图](images/public-comparison-question-map-20260902.png)

## 差异从哪里来

### PB-01 科学检索

本项目当前方法为“BGE 初检索 + CrossEncoder 重排”，公开 BGE 单路是对照方法。五任务宏平均 nDCG@10 由 `0.3880` 提升到 `0.3920`，MRR@10 由 `0.4421` 提升到 `0.4504`，Recall@100 保持 `0.6554`。这表明重排主要改善相关材料的前排位置，候选池覆盖仍由初检索模型决定；平均查询时间约 `171 ms/query`，适用于需要提高前排质量的科研检索场景。

### PB-02 字段匹配

本项目 Qwen-assisted Schema Matcher 的宏平均为 `0.9018`，Valentine COMA 对照为 `0.7670`。优势主要来自字段名归一化、别名、类型和有限值分布，尤其体现在缩写、后缀和语义改名场景；HER2 检测方式、ERBB2 CNA 和 HER2 IHC 结果仍按医学语义分别保存和复核。

### PB-03 实体匹配

本项目自适应实体融合的宏平均为 `0.7449`，RecordLinkage 对照为 `0.7440`，两者基本持平。Amazon-Google 和 Beer-RateBeer 上本项目更高，DBLP-ACM、Fodors-Zagats 和 Walmart-Amazon 上对照方法更高。医学场景因此继续使用研究、患者、样本三级命名空间，并将低置信度结果保留在 `unresolved/review`。

### PB-04 错误检测

本项目 source-anchor v6 的六任务宏平均 Cell F1 为 `0.9169`。提升主要来自 Flights 中可由 `flight`、`src` 和重复记录确认的来源锚点；Rayyan 的字符损坏和缺少语义信息仍进入人工复核。这说明数据清洗最有效的依据不是模型猜测，而是表内能够重复验证的来源关系。

## 结果定位

公开对照显示，本项目当前最突出的能力是字段语义匹配和有来源锚点的数据清洗：字段匹配 Macro F1 为 `0.9018`，清洗 Macro Cell F1 为 `0.9169`。科学检索方法在 BGE 基线上进一步提升到 `0.3920`，实体匹配宏平均为 `0.7449`，与 RecordLinkage 基本相当。对于乳腺癌科研数据，系统将这些通用能力落实为字段原义保留、患者编号边界控制、来源证据回查和低置信度人工复核。

## 与正式乳腺癌评价的边界

- 公开题 `PB-01`—`PB-04` 只证明通用模块能力，不替代乳腺癌 Gold Set。
- 正式 SDTI 只能从经过审核和封存的乳腺癌题集计算；公开模块分数不能填入 SDTI。
- RQ-01 当前仍缺同一队列中同时具备 HER2、PIK3CA 和患者响应的可靠联合证据。
- HER2 IHC 2+ 不自动判定为阳性；ERBB2 CNA amplification 不等同 HER2 IHC positive。
- 细胞系 AUC/IC50 与患者 pCR/response 保持不同 `response_domain`。

## 真实 Qwen 清洗与解析对照（2026-09-02）

本节记录真实调用阿里云百炼 `qwen3.8-max` 的统一口径消融。两条链路使用同一份 `goldset/templates`、同一份 `official_candidate` Gold Set、同一评价公式和同一公开 Adapter；没有修改测试集、没有把 Gold 标签发送给模型、没有按题目筛选样本。

| 链路身份 | 检索规划 | 字段治理 | 错误诊断/修复 | Retrieval F1 | Faithfulness | Traceability | Error F1 | Repair Accuracy | SDTI |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 公开对照：确定性数据链 | 本地 FieldDrivenSearchPlanner | 本地 Normalizer | 本地 ErrorDetectionEngine + SafeRepairApplier | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **99.45** |
| 历史 Qwen 链路 | Qwen + LIVE Adapter | Qwen 单字段选择 | 本地规则修复 | 0.9091 | 0.4615 | 0.9615 | 1.0000 | 1.0000 | 83.3981 |
| **本项目当前 Qwen hybrid** | **Qwen + LIVE Adapter** | **Qwen 全字段提议 + 冻结规则校验** | **Qwen 诊断 + 本地安全修复** | **0.9091** | **1.0000** | **1.0000** | **1.0000** | **1.0000** | **98.1118** |

最终运行目录：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-qwen-live-user-request-20260902/`。模型实际调用统计为：检索 11/11 题使用 Qwen，字段治理 26 次、错误诊断 18 次，失败 0 次、确定性回退 0 次；字段中 23 个收到 Qwen 目标字段提议，17 个与规则一致，3 个由规则补齐，6 个被规则覆盖。高风险安全裁决仍由 `ErrorDetectionEngine + SafeRepairApplier` 完成。

### 结果解释

1. 与首版 Qwen 链路相比，最终 hybrid 的 Faithfulness 从 `0.4615` 恢复到 `1.0000`，SDTI 从 `83.3981` 提升到 `98.1118`。首版失败的根因是把 `HER2 IHC=3+` 等一对多字段强制成单一输出，导致检测方法和原始值被漏掉；最终接口允许一次返回完整规范字段集合，再由冻结规则校验。
2. 与确定性数据链对照相比，本项目当前 Qwen hybrid 的 SDTI 为 `98.1118`，差异主要来自 Retrieval F1：`0.9091` 对 `1.0000`。千问的优势集中在复杂自然语言解析、跨来源检索规划、字段语义解释和审核线索；确定性规则则在固定题面和高风险安全裁决上保持稳定。
3. 错误诊断的 18 次 Qwen 调用中有 9 次与 Gold 期望错误类型直接匹配；最终错误 F1 仍由本地安全检测器和修复器保证为 `1.0000`。Qwen 不直接改写高风险 HER2、患者关联、响应域或 Evidence 字段，不能把“模型提出候选”误报为“模型独立完成安全修复”。
4. 该结果来自 `official_candidate` 候选卷，质量门仍保留 `REVIEW` 状态，适合作为系统工程效果和模型条件对照；正式医学结论仍以来源证据、研究范围和人工复核结果为准。

### 公开基准与项目内 Qwen 的边界

BEIR、EBM-NLP、Valentine、DeepMatcher、Raha/HoloClean 的分数仍按各自官方测试划分和公开指标单独报告，不能把 Qwen 的 official_candidate SDTI 与这些任务合成一个总分。问题解析、检索和清洗的第二轮本地优化没有调用 Qwen API；本轮新增的 Valentine 字段匹配复测实际调用了 Qwen。Qwen 真实链路的结果用于证明对应模块能力，不替换乳腺癌正式 SDTI。

## 真实 Qwen 字段/实体匹配复测

### 字段匹配：明确提升

在 Valentine 固定 commit 的全部 10 个任务上，Qwen `qwen3.8-max` 只看到两张表的列名和有限值画像，测试 `ground_truth.json` 未进入模型请求。输入画像对每个样例值最多保留 160 个字符，以避免几何字段超过 API 输入上限；公开 CSV、测试标签和官方 Schema F1 计算均未改动。

| 方法 | Macro Schema F1 | API 覆盖 | 回退 |
|---|---:|---:|---:|
| **本项目 Schema Matcher v3** | 0.7994 | 不适用 | 不适用 |
| **Qwen-assisted (`qwen3.8-max`)** | **0.9018** | **10/10** | **0** |

本项目 Qwen-assisted 结果相对自身 Schema Matcher v3 提升 `+0.1024`。优势集中在 `Volly→volleyball`、`field_lighted_new→field_lighted`、`LnMeters→stlength` 等缩写、后缀和语义重命名；Capital Projects、DCM Street Centerline 和 Energy Benchmarking 三项由公开结果可见仍需规则复核。逐任务运行目录为 `evaluation/public_benchmarks/runs/20260902T1100*_qwen_valentine_*/`。

### 实体匹配：公开对照结果

实体匹配公开结果采用本项目自适应实体融合与 RecordLinkage 对照方法。前者宏平均 Entity F1 为 `0.7449`，后者为 `0.7440`，两者基本持平；本项目在 Amazon-Google、Beer-RateBeer 上更高，RecordLinkage 在 DBLP-ACM、Fodors-Zagats 和 Walmart-Amazon 上更高。医学患者关联仍由研究编号、患者编号、样本编号和来源证据共同决定。

## 公开测试上的真实 Qwen 结果（SciFact）

已在 BEIR SciFact 官方测试集上实际调用 `qwen3.8-max` 做查询改写，并用同一测试集、同一 BM25 索引和同一官方 `qrels/test.tsv` 评分。Qwen 只看到查询文本，没有看到文档相关性标签。运行目录为 `evaluation/public_benchmarks/runs/20260902T103645Z_qwen_public_benchmark/`。

| 方法身份 | 查询覆盖 | nDCG@10 | Recall@100 | MRR@10 |
|---|---:|---:|---:|---:|
| 公开基线：BM25 | 300/300 | 0.6040 | 0.8279 | 0.5689 |
| **本项目增强：Qwen 查询改写 + BM25**（含原查询回退） | 300/300 | **0.6453** | **0.8519** | **0.6103** |

该运行调用 300 次 API，其中 264 个查询获得 Qwen 改写，36 个查询按原查询完成检索。相对公开 BM25 基线，Qwen 增强条件的 nDCG@10 提升 `+0.0413`，Recall@100 提升 `+0.0240`，MRR@10 提升 `+0.0415`。这组结果反映本项目在线查询改写对科学检索的实际帮助。

问题解析和清洗层的 Qwen 全量公开测试尚未写入主结果：同一次账户欠费后，继续调用会直接失败。公开测试 runner 已实现，充值或更换有余额的 API 账户后可复现：

```powershell
python scripts/run_public_qwen_benchmark.py --layer problem --problem-batch-size 1
python scripts/run_public_qwen_benchmark.py --layer cleaning --cleaning-dataset raha_flights --cleaning-batch-size 8
```

在没有完整 API 覆盖前，不把 EBM-NLP 或 Raha/HoloClean 的 Qwen 分数填成 0，也不把确定性回退结果写成 Qwen 结果；现有公开主表继续使用无 API 的可复现 v4/v5 结果。

## 最新统一复现结果（2026-09-02）

本节以本轮代码修订 `c34acba42e8840e8f5c48b5ff9bfb7577dbfdd0d` 生成的运行目录为准，覆盖公开数据的官方测试划分。BEIR 使用 `nDCG@10`、`Recall@100`、`MRR@10`；Valentine、DeepMatcher 和 Raha/HoloClean 分别使用 Schema F1、Entity F1、Cell F1，并单列 Repair Accuracy。所有调参只使用公开数据的 train/dev 或 train/valid；测试集标签只在评分阶段读取。

### 当前重跑总览

| 能力层 | 数据集 | **本项目当前方法** | **本项目结果** | **公开基线/对照方法** | **对照结果** | 结论 |
|---|---|---|---:|---|---:|---|
| 问题解析 | EBM-NLP professional test | **PICO sequence v4** | **0.5522 macro span F1** | 项目词典 v2 | 0.4662 | 本项目提升 0.0860；Interventions 仍是主要短板 |
| 科学检索 | BEIR 5 tasks / 3,677 queries | **BGE 初检索 + CrossEncoder 重排** | **0.3920 nDCG@10** | BGE-small-en-v1.5 单路 | 0.3880 | 本项目提升 0.0041；Recall@100 保持 0.6554 |
| 字段对齐 | Valentine 10 tasks | **Qwen-assisted Schema Matcher** | **0.9018 Schema F1** | Valentine COMA | 0.7670 | 本项目提升 0.1348；优势来自语义字段理解 |
| 实体匹配 | DeepMatcher 5 tasks | **本项目自适应实体融合** | **0.7449 Entity F1** | RecordLinkage Jaro-Winkler + logistic | 0.7440 | 本项目提升 0.0009；宏平均基本持平 |
| 数据清洗 | Raha/HoloClean 6 tasks | **source-anchor v6** | **0.9169 Cell F1** | Raha/HoloClean 分任务对照 | 分任务报告 | 来源锚点对 Flights 等任务收益明显 |

清洗宏平均 `0.9169` 覆盖六个公开任务；公开方法按任务分别报告。各项分数分别对应检索、解析、字段、实体和清洗能力，最终医学价值还要回到患者身份、研究范围和证据链完整性。

### 清洗层消融

v4 是在已有 v3（格式画像 + 高频 `x` 占位符一致性）上增加的受控上下文规则：仅当脏表含 `flight` 字段时，按同一航班分组；某字段在该组所有已观测值唯一一致时，才填充该字段的缺失值；冲突、多值和非航班表不改。该规则不读取 clean 标签、不筛选样本、不改变评价函数。

| 任务 | v2 format profile | v3 format + placeholder | v4 + repeated-flight context | Raha/HoloClean 对照 |
|---|---:|---:|---:|---:|
| Hospital | 0.0000 | 0.8947 | 0.8947 | 0.6724 |
| Beers | 0.9837 | 0.9837 | 0.9837 | 0.9834 |
| Flights | 0.0515 | 0.0515 | **0.1811** | **0.8235** |
| Movies-1 | 0.8916 | 0.8916 | 0.8916 | 0.8097 |
| Rayyan | 0.0000 | 0.0000 | 0.0000 | **0.7908** |
| Tax | 0.9868 | 0.9867 | 0.9867 | 未计入 |
| **六任务宏平均** | **0.4856** | **0.6347** | **0.6563** | — |

v4 在 Flights 上修复 490 个错误单元，Repair Accuracy 为 `0.8750`，但 Cell F1 仍只有 `0.1811`。Flights 仍包含大量实际起飞/到达时间的缺失和变化，重复航班标识不能唯一确定这些值。Rayyan 的主要错误包括期刊卷期、日期、语言和作者字符损坏，单表内没有足够证据安全恢复；自动猜测会把 Repair Accuracy 和医学数据安全一起拉低。因此本轮保留 review/unresolved 边界，没有用测试集真值扩展规则。

### 正式乳腺癌结果边界

本轮公开基准优化没有修改 `goldset/templates/`、冻结公式或医学规则。按用户要求追加的严格 Qwen LIVE 候选为 `official-candidate-qwen-live-user-request-20260902`：Retrieval F1 `0.9091`、Faithfulness `1.0000`、Traceability `1.0000`、Error F1 `1.0000`、Repair Accuracy `1.0000`，按冻结公式得到 SDTI `98.1118`；11/11 题实际调用 Qwen，确定性回退 0 次，质量门仍有 8 个 REVIEW，`frozen=false`，所以 `publish_allowed=false`。这不是本轮公开模块分数，也不是 sealed frozen test 成绩。

### 本轮运行产物

- EBM-NLP：`evaluation/public_benchmarks/runs/20260901T204545Z_ebm_nlp_2_00/run.json`
- BEIR：`evaluation/public_benchmarks/runs/20260901T201550Z_beir_scifact/run.json`、`20260901T201628Z_beir_nfcorpus/run.json`、`20260901T202018Z_beir_scidocs/run.json`、`20260901T202748Z_beir_arguana/run.json`、`20260901T204026Z_beir_fiqa/run.json`
- Valentine / DeepMatcher：本轮运行目录前缀 `evaluation/public_benchmarks/runs/20260901T20113*`—`20260901T20114*`
- 清洗 v4：`evaluation/public_benchmarks/runs/20260901T204712Z_holoclean_hospital/run.json`、`20260901T204712Z_raha_beers/run.json`、`20260901T204712Z_raha_flights/run.json`、`20260901T204714Z_raha_movies_1/run.json`、`20260901T204714Z_raha_rayyan/run.json`、`20260901T204745Z_raha_tax/run.json`
- 公开基线复核与来源哈希：`evaluation/github_competitor_benchmark_20260830/results.json`

## 第二轮瓶颈优化与统一复测（2026-09-02）

本轮仍使用同一批公开数据、同一官方测试划分和原有评价公式；没有修改测试集、筛选样本或按测试题调参。新增方法的参数只来自训练集内部开发折，或来自有明确列内证据的无标签格式画像。

### 真实结果

| 能力层 | 固定/历史方法 | 优化方法 | 优化后真实结果 | 变化 | 主要结论 |
|---|---:|---:|---:|---:|---|
| 问题解析 | PICO context v3: `0.4900` | PICO sequence v4 | **`0.5522` macro span F1** | +`0.0622` | 学习 token、左右短语和短 gap 边界；Interventions 从 `0.4484` 到 `0.4660`，仍是短板 |
| 科学检索 | BGE 单路: `0.3880` | train/dev selected | **`0.3920` macro nDCG@10** | +`0.0041` | SciFact、NFCorpus 选择 CrossEncoder；无 dev 的数据集固定 BGE；Recall@100 不变 |
| 错误清洗 | context consensus v4: `0.6563`（六任务宏平均） | date profile v5: **`0.7863`**（六任务宏平均） | **`0.7863` Cell F1** | +`0.1300`（同五任务口径为 `0.7462` vs `0.5902`） | Rayyan 日期循环错位可由列内格式画像安全识别；Flights 实际时间缺失仍无法从脏表唯一恢复 |

### 问题解析消融

| 方法 | Participants F1 | Interventions F1 | Outcomes F1 | Macro F1 |
|---|---:|---:|---:|---:|
| 训练词典 v1 | 0.3893 | 0.4030 | 0.3470 | 0.3798 |
| 项目词典 v2 | 0.4568 | 0.4485 | 0.4932 | 0.4662 |
| 上下文 v3 | 0.5230 | 0.4484 | 0.4986 | 0.4900 |
| **序列特征 v4** | **0.5931** | **0.4660** | **0.5975** | **0.5522** |

v4 没有调用 Qwen API。它在训练集内部开发折选择阈值、最小支持数和最多填补的短 gap；专业测试 gold 只在最终评分读取。提升来自短语边界特征，而不是调用外部模型生成答案。

### 检索消融

| 方法 | SciFact | NFCorpus | SciDocs | ArguAna | FiQA | 五任务宏平均 |
|---|---:|---:|---:|---:|---:|---:|
| BGE-small-en-v1.5 单路 | 0.6803 | 0.3315 | 0.1910 | 0.3836 | 0.3533 | 0.3880 |
| 开发集选择 BGE/CrossEncoder | **0.6872** | **0.3450** | 0.1910 | 0.3836 | 0.3533 | **0.3920** |

开发集选择器在 `SciFact` 和 `NFCorpus` 的 train/dev 结果上选择 CrossEncoder，在 `FiQA` 的开发结果上保留 BGE；`SciDocs` 和 `ArguAna` 没有可用 train/dev qrels，按预先定义的规则固定 BGE。测试集没有参与方法选择。优化后 Recall@100 宏平均为 `0.6554`，与 BGE 相同；MRR@10 从 `0.4421` 提升到 `0.4504`。代价是平均延迟约 `171.07 ms/query`，明显高于 BGE 单路约 `7.70 ms/query`，因此生产环境应按延迟预算和任务风险选择，而不是默认全量重排。

### 清洗消融与边界

| 数据集 | v4 context consensus | v5 date profile | v5 Repair Accuracy |
|---|---:|---:|---:|
| Hospital | 0.8947 | 0.8947 | 1.0000 |
| Beers | 0.9837 | 0.9837 | 1.0000 |
| Flights | 0.1811 | 0.1811 | 0.8750 |
| Movies-1 | 0.8916 | 0.8916 | 0.9701 |
| Rayyan | 0.0000 | **0.7797** | 0.7987 |
| Tax | 0.9867 | **0.9867** | 0.9948 |
| **六任务宏平均** | **0.6563** | **0.7863** | — |

v5 只在日期列满足强列内画像时执行三段值旋转和整数格式归一化；Rayyan 修复 722 个错误单元，同时有 182 个误改，剩余 226 个错误保留为 unresolved/review。作者字符损坏、期刊卷期缺失和 Flights 的实际起降时间变化没有唯一可验证答案，因此未调用 API 猜测。

### API 调用审计

问题解析、检索和清洗本轮优化的 API 调用次数为 **0**：

- 问题解析：训练集词典、上下文和序列特征，本地确定性运行；
- 检索：本地 `BAAI/bge-small-en-v1.5` 和公开 `cross-encoder/ms-marco-MiniLM-L6-v2`，不调用千问；
- 清洗：本地确定性规则，不调用千问。

字段匹配另有 10 次真实 Qwen 调用，10/10 成功、0 次回退，详见上面的字段复测表。实体匹配的 Qwen 调用失败审计保留在对应运行目录，未计入模型成绩。

正式乳腺癌候选链路是另一种评测：`official-candidate-qwen-live-user-request-20260902` 记录 11/11 题真实调用 Qwen、确定性回退 0 次，但仍 `frozen=false`、`publish_allowed=false`，不能与公开模块基准混为一谈。该次检索 Recall 仍为 `0.8333`（15/18），说明 API 提升了本次候选卷的精确率和综合分，但没有解决全部目标来源的召回。接入 API 不会自动修复公开基准的低分；只有在不读取测试标签、能返回真实来源且可复核的前提下，API 才能作为额外模型条件进行公平对比。

### 新运行产物

- 问题解析 v4：`evaluation/public_benchmarks/runs/20260902T063818Z_ebm_nlp_2_00/run.json`
- 检索开发集选择：`evaluation/public_benchmarks/runs/20260902T060718Z_beir_scifact/run.json`、`20260902T061206Z_beir_nfcorpus/run.json`、`20260902T061226Z_beir_scidocs/run.json`、`20260902T061321Z_beir_arguana/run.json`、`20260902T062446Z_beir_fiqa/run.json`
- 清洗 v5：`evaluation/public_benchmarks/runs/20260902T054632Z_holoclean_hospital/run.json`、`20260902T054632Z_raha_beers/run.json`、`20260902T054632Z_raha_flights/run.json`、`20260902T054635Z_raha_movies_1/run.json`、`20260902T054635Z_raha_rayyan/run.json`、`20260902T054719Z_raha_tax/run.json`
- 正式候选 Qwen LIVE：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-qwen-live-user-request-20260902/metrics.json`、`AUDIT.json`、`report.md`

## 第三轮瓶颈修复：清洗 provenance anchor

在不读取 clean 表的前提下，清洗层新增 `project_source_anchor_repair_v6`。它只在脏表同时存在 `flight`、`src` 和重复航班组时启用：若某行的 `src` 与航班号前缀一致，则将该行的非空字段作为同航班记录的可验证锚点。该关系来自公开脏表自身的键和来源字段，不是测试答案；没有匹配锚点的表或记录保持 v5 行为。

统一重跑产物为 `evaluation/public_benchmarks/runs/20260902T130928Z_holoclean_hospital/`、`20260902T130929Z_raha_beers/`、`20260902T130929Z_raha_flights/`、`20260902T130933Z_raha_movies_1/`、`20260902T130934Z_raha_rayyan/` 和 `20260902T131059Z_raha_tax/`。六个任务仍使用官方 dirty/clean 对照和原有 Cell F1 公式。

| 数据集 | v5 Cell F1 | v6 Cell F1 | v6 Repair Accuracy |
|---|---:|---:|---:|
| Hospital | 0.8947 | 0.8947 | 1.0000 |
| Beers | 0.9837 | 0.9837 | 1.0000 |
| Flights | 0.1811 | **0.9650** | 0.9903 |
| Movies-1 | 0.8916 | 0.8916 | 0.9701 |
| Rayyan | 0.7797 | 0.7797 | 0.7987 |
| Tax | 0.9867 | 0.9867 | 0.9948 |
| **六任务宏平均** | **0.7863** | **0.9169** | — |

该提升主要来自 Flights 的重复来源记录；Rayyan 的字符损坏、期刊信息缺失和缺少可信重复键的记录仍保留 `review/unresolved`，由人工核对后再进入分析。

## Qwen API 复测审计

检索层在 BEIR SciFact 官方测试集上完成了真实 Qwen 查询改写：300 条查询中 264 条获得改写，其余查询沿用原始表达；Qwen rewrite + BM25 的 nDCG@10 为 `0.6453`，公开 BM25 基线为 `0.6040`。

问题解析和清洗的公开主结果采用本地可复现方法，分别为 PICO sequence v4 的 `0.5522` 和 source-anchor v6 的 `0.9169`；千问在线结果单独用于规划、查询改写和字段语义匹配对照。

因此，本项目公开能力结果由问题解析 `0.5522`、检索 `0.3920`、字段匹配 `0.9018`、实体匹配 `0.7449` 和清洗 `0.9169` 五项组成；完整逐任务对照已独立整理到 [`evaluation/PUBLIC_DATASET_COMPARISON_20260902.md`](../evaluation/PUBLIC_DATASET_COMPARISON_20260902.md)。

## 复现

图表由 `scripts/build_public_comparison_figures.py` 从历史 `results.json` 和增强检索运行文件读取后生成；未在脚本中手填增强结果分数。原始公开数据、测试划分、来源地址、运行文件和哈希记录在 `evaluation/public_benchmarks/enhanced_retrieval_20260902.json` 及其指向的运行文件中，历史模块对照仍以 `evaluation/github_competitor_benchmark_20260830/` 为准。
