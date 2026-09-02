# 公开对照题号与结果说明

更新时间：2026-09-02  
数据依据：历史对照 `evaluation/github_competitor_benchmark_20260830/results.json`；增强检索运行摘要 `evaluation/public_benchmarks/enhanced_retrieval_20260902.json`

## 先说清楚：原问题没有被替换

本文保留原始科研问题 **RQ-01**：

> 在 HER2 阳性乳腺癌中，PIK3CA 突变是否与新辅助治疗响应相关？

RQ-01 是一个患者/样本级医学研究问题，必须在同一研究或可靠 crosswalk 中同时具备 HER2、PIK3CA、治疗阶段和患者响应。公开通用数据集不能直接回答这个问题，只能拆开检查系统的四项通用能力。图 `public-comparison-question-map-20260902.png` 专门说明了这层关系。

## 对照题号

| 题号 | 从原问题拆出的能力问题 | 公开数据与指标 | 本项目方法 | 公开对照 | 该题能说明什么 |
|---|---|---|---|---|---|
| `PB-01` | 能否把相关材料排到前十？ | BEIR 5 个数据集；nDCG@10 | BM25 + BGE + CrossEncoder | BGE-small-en-v1.5 单路 | 检查候选材料排序，不证明乳腺癌来源完整 |
| `PB-02` | 两张表的不同列名是否表示同一字段？ | Valentine 10 个任务；Schema F1 | 本项目 Schema Matcher V3 | Valentine COMA | 检查字段语义对齐，不证明医学字段可直接合并 |
| `PB-03` | 两条记录是否指向同一个实体？ | DeepMatcher 5 个任务；Entity F1 | 本项目自适应融合 | RecordLinkage Jaro-Winkler + logistic | 检查通用记录匹配，不证明患者身份可以自动合并 |
| `PB-04` | 能否找出错误单元且不误伤正确值？ | Raha/HoloClean 6 个任务；Cell F1 | 本项目格式与占位符融合 | Raha PVD+RVD | 检查表格错误检测，不证明医学缺失值可以安全猜测 |

`PB-01`—`PB-04` 是模块题，不是四道新的乳腺癌临床题。规划模型替换实验和正式候选卷另列为工程诊断，不混入这四个公开题号。

## 宏平均总览

| 公开题号 | 本项目 | 公开对照 | 谁更高 | 真实解释 |
|---|---:|---:|---|---|
| `PB-01` 科学检索 | **0.3818** | 0.3880 | 公开对照高 0.0061 | 重排比旧融合 0.3791 提升 0.0027，但在 SciDocs、ArguAna 仍拉低平均值 |
| `PB-02` 字段匹配 | **0.7994** | 0.7670 | **本项目高 0.0324** | 值分布和字段规则对通用列名差异有效，但缩写/布尔列仍有误匹配 |
| `PB-03` 实体匹配 | **0.7449** | 0.7440 | **本项目高 0.0009** | 宏平均基本持平；Walmart-Amazon 仍明显落后，不能放宽患者关联门槛 |
| `PB-04` 错误检测 | 0.5726 | 0.8159 | 公开对照高 0.2433 | Flights、Rayyan 的缺失和语义错误是当前最大短板 |

这四个数不能相加，也不能合成一个“项目总排名”：数据集、任务和指标不同。完整逐题图见：

- [公开能力对照总览](images/public-comparison-scorecard-20260902.png)
- [PB-01 科学检索逐题图](images/public-retrieval-datasets-20260902.png)
- [PB-02 字段匹配逐题图](images/public-schema-datasets-20260902.png)
- [PB-03 实体匹配逐题图](images/public-entity-datasets-20260902.png)
- [PB-04 错误检测逐题图](images/public-cleaning-datasets-20260902.png)
- [公开对照失败原因地图](images/public-comparison-failure-map-20260902.png)
- [原问题与对照题号关系图](images/public-comparison-question-map-20260902.png)

## 为什么有些对照不好

### PB-01 科学检索

重排增强宏平均为 `0.3818`，比旧融合 `0.3791` 提高 `0.0027`，但仍低于 BGE 单路 `0.3880`。它在 SciFact、NFCorpus、FiQA 带来局部提升，差距主要来自 SciDocs 和 ArguAna。原因不是“公开数据不好”，而是当前重排模型对部分长论文/论证型查询的前排相关性判断还不稳定；同时平均查询延迟约 `452.01 ms`，明显高于 BGE 单路。正确提升方式是只在开发集选择融合、单路或重排策略，再用独立测试集确认，不能按测试题逐题挑方法。

### PB-02 字段匹配

本项目宏平均高于 COMA。优势主要来自字段名归一化、别名、类型和有限值分布；短板集中在缩写、布尔列、重复值和一对多候选。分数领先不能替代医学安全判断：HER2 检测方式、ERBB2 CNA 和 HER2 IHC 结果仍需要单独的规则与复核。

### PB-03 实体匹配

本项目宏平均只高 `0.0009`，应理解为“基本持平”，不是全面领先。Amazon-Google 和 Beer-RateBeer 上本项目更高，但 DBLP-ACM、Fodors-Zagats 和 Walmart-Amazon 上公开对照更高。Walmart-Amazon 的标题变化说明单纯字符串和字段相似度仍不足；医学场景还要额外加入研究、患者、样本命名空间，宁可保留 `unresolved/review`，也不能为了提高 Recall 自动合并患者。

### PB-04 错误检测

本项目在 Hospital、Beers 和 Movies-1 上不低于公开对照，但 Flights 和 Rayyan 明显落后，造成宏平均被拉低。当前方法擅长数字、单位、缺失标记和明显占位符等格式错误；Flights/Rayyan 中的缺失恢复、字符替换和语义重排无法仅由一张脏表唯一推断。下一轮应加入跨列约束、独立验证阈值，并把“发现错误”“提出修复候选”“自动修复/人工复核”拆开计分。

## “只要我们的最好”应该怎样处理

公开对照不能通过删除失败任务、换指标、换数据集或把未运行方法写成高分来制造“本项目最好”。当前真实结论是：本项目在字段匹配和实体匹配宏平均领先，检索接近但略低，错误检测落后。把领先项展示清楚可以；把落后项隐藏会让材料失去可复核性，也会和 `results.json`、运行哈希及公开来源冲突。

真正能让本项目在更多题上变好的路径是：

1. 检索：在开发划分上校准融合权重和单路选择，再用独立测试集复测。
2. 字段：按缩写、布尔列、重复值分层，新增 Wrong Auto-Match 和 Review Rate。
3. 实体：扩大训练/验证样本，分别报告通用 Entity F1 与患者 False Merge Rate。
4. 清洗：补充跨列和语义异常检测，低置信度不自动改值。

这些是待验证的提升方案，不能提前写成已有成绩。

## 与正式乳腺癌评价的边界

- 公开题 `PB-01`—`PB-04` 只证明通用模块能力，不替代乳腺癌 Gold Set。
- 正式 SDTI 只能从经过审核和封存的乳腺癌题集计算；公开模块分数不能填入 SDTI。
- RQ-01 当前仍缺同一队列中同时具备 HER2、PIK3CA 和患者响应的可靠联合证据。
- HER2 IHC 2+ 不自动判定为阳性；ERBB2 CNA amplification 不等同 HER2 IHC positive。
- 细胞系 AUC/IC50 与患者 pCR/response 保持不同 `response_domain`。

## 真实 Qwen 清洗与解析对照（2026-09-02）

本节记录真实调用阿里云百炼 `qwen3.8-max` 的统一口径消融。两条链路使用同一份 `goldset/templates`、同一份 `official_candidate` Gold Set、同一评价公式和同一公开 Adapter；没有修改测试集、没有把 Gold 标签发送给模型、没有按题目筛选样本。

| 链路 | 检索规划 | 字段治理 | 错误诊断/修复 | Retrieval F1 | Faithfulness | Traceability | Error F1 | Repair Accuracy | SDTI |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 当前确定性基线 | 本地 FieldDrivenSearchPlanner | 本地 Normalizer | 本地 ErrorDetectionEngine + SafeRepairApplier | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **100.0000** |
| 首版 Qwen 清洗接入 | Qwen + LIVE Adapter | Qwen 单字段选择 | 本地规则修复 | 0.9091 | 0.4615 | 0.9615 | 1.0000 | 1.0000 | 83.3981 |
| **最终 Qwen hybrid** | **Qwen + LIVE Adapter** | **Qwen 全字段提议 + 冻结规则校验** | **Qwen 诊断 + 本地安全修复** | **0.9091** | **1.0000** | **1.0000** | **1.0000** | **1.0000** | **98.1118** |

最终运行目录：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-qwen-hybrid-final-20260902/`。模型实际调用统计为：检索 11/11 题使用 Qwen，字段治理 26 次、错误诊断 18 次，失败 0 次、确定性回退 0 次；字段中 23 个收到 Qwen 目标字段提议，17 个与规则一致，3 个由规则补齐，6 个被规则覆盖。高风险安全裁决仍由 `ErrorDetectionEngine + SafeRepairApplier` 完成。

### 结果解释

1. 与首版 Qwen 链路相比，最终 hybrid 的 Faithfulness 从 `0.4615` 恢复到 `1.0000`，SDTI 从 `83.3981` 提升到 `98.1118`。首版失败的根因是把 `HER2 IHC=3+` 等一对多字段强制成单一输出，导致检测方法和原始值被漏掉；最终接口允许一次返回完整规范字段集合，再由冻结规则校验。
2. 与当前确定性基线相比，Qwen hybrid 的 SDTI 低 `1.8882` 个百分点，差距完全来自 Retrieval F1：`0.9091` 对 `1.0000`。因此当前公开候选卷不能证明 Qwen 在专门化来源选择上胜过本地规则；Qwen 的优势边界是复杂自然语言解析、跨来源检索规划、字段语义解释和审核线索，而不是已经被规则覆盖的精确题面。
3. 错误诊断的 18 次 Qwen 调用中有 9 次与 Gold 期望错误类型直接匹配；最终错误 F1 仍由本地安全检测器和修复器保证为 `1.0000`。Qwen 不直接改写高风险 HER2、患者关联、响应域或 Evidence 字段，不能把“模型提出候选”误报为“模型独立完成安全修复”。
4. 9 个实时任务质量门为 `REVIEW`，且卷面仍是 `official_candidate`、`frozen=false`；所以 `publish_allowed=false`。`98.1118` 是真实候选观察分，不是 sealed frozen_test 成绩。

### 公开基准与项目内 Qwen 的边界

BEIR、EBM-NLP、Valentine、DeepMatcher、Raha/HoloClean 的分数仍按各自官方测试划分和公开指标单独报告，不能把 Qwen 的 official_candidate SDTI 与这些任务合成一个总分。问题解析、检索和清洗的第二轮本地优化没有调用 Qwen API；本轮新增的 Valentine 字段匹配复测实际调用了 Qwen。Qwen 真实链路的结果用于证明对应模块能力，不替换乳腺癌正式 SDTI。

## 真实 Qwen 字段/实体匹配复测

### 字段匹配：明确提升

在 Valentine 固定 commit 的全部 10 个任务上，Qwen `qwen3.8-max` 只看到两张表的列名和有限值画像，测试 `ground_truth.json` 未进入模型请求。输入画像对每个样例值最多保留 160 个字符，以避免几何字段超过 API 输入上限；公开 CSV、测试标签和官方 Schema F1 计算均未改动。

| 方法 | Macro Schema F1 | API 覆盖 | 回退 |
|---|---:|---:|---:|
| 项目 Schema Matcher v3 | 0.7994 | 不适用 | 不适用 |
| **Qwen-assisted (`qwen3.8-max`)** | **0.9018** | **10/10** | **0** |

Qwen 相对 v3 提升 `+0.1024`。优势集中在 `Volly→volleyball`、`field_lighted_new→field_lighted`、`LnMeters→stlength` 等缩写、后缀和语义重命名；Capital Projects、DCM Street Centerline 和 Energy Benchmarking 三项反而下降，所以不能写成“Qwen 在所有任务最优”。逐任务运行目录为 `evaluation/public_benchmarks/runs/20260902T1100*_qwen_valentine_*/`。

### 实体匹配：本轮未形成 Qwen 成绩

实体匹配已实现批量 Qwen 判定接口，设计上使用 DeepMatcher 官方 test 对，训练集仅作为少量正负示例，测试标签仅在本地评分。但完整 `Walmart-Amazon` 运行期间百炼返回 `Arrearage`，86 个批次全部回退到项目规则，Qwen 覆盖为 `0/2049`；该运行不计作 Qwen Entity F1。当前可发布的公开实体结果仍是项目 v2 宏平均 `0.7408`、RecordLinkage 对照 `0.7440`。稳定余额后应完整重跑五个任务，再决定是否能客观宣称提升；在此之前，论文不填 Qwen 实体分数。

## 公开测试上的真实 Qwen 结果（SciFact）

已在 BEIR SciFact 官方测试集上实际调用 `qwen3.8-max` 做查询改写，并用同一测试集、同一 BM25 索引和同一官方 `qrels/test.tsv` 评分。Qwen 只看到查询文本，没有看到文档相关性标签。运行目录为 `evaluation/public_benchmarks/runs/20260902T103645Z_qwen_public_benchmark/`。

| 方法 | 查询覆盖 | nDCG@10 | Recall@100 | MRR@10 |
|---|---:|---:|---:|---:|
| BM25 | 300/300 | 0.6040 | 0.8279 | 0.5689 |
| Qwen 查询改写 + BM25（含原查询回退） | 300/300 | **0.6453** | **0.8519** | **0.6103** |

该运行调用 300 次 API，其中 264 个查询获得 Qwen 改写，36 个查询因阿里云返回 `Arrearage`（账户余额/欠费）而按预先定义回退到原查询；因此这组数是“Qwen-assisted with raw-query fallback”，不是纯 Qwen 300/300 成绩。相对 BM25 的真实变化为 nDCG@10 `+0.0413`、Recall@100 `+0.0240`、MRR@10 `+0.0415`，但受 36 个回退影响，不能据此声称纯 Qwen 在全部查询上取得同样增益。

问题解析和清洗层的 Qwen 全量公开测试尚未写入主结果：同一次账户欠费后，继续调用会直接失败。公开测试 runner 已实现，充值或更换有余额的 API 账户后可复现：

```powershell
python scripts/run_public_qwen_benchmark.py --layer problem --problem-batch-size 1
python scripts/run_public_qwen_benchmark.py --layer cleaning --cleaning-dataset raha_flights --cleaning-batch-size 8
```

在没有完整 API 覆盖前，不把 EBM-NLP 或 Raha/HoloClean 的 Qwen 分数填成 0，也不把确定性回退结果写成 Qwen 结果；现有公开主表继续使用无 API 的可复现 v4/v5 结果。

## 本轮统一复现与优化（2026-09-02）

本节以本轮代码修订 `c34acba42e8840e8f5c48b5ff9bfb7577dbfdd0d` 生成的运行目录为准，覆盖公开数据的官方测试划分。BEIR 使用 `nDCG@10`、`Recall@100`、`MRR@10`；Valentine、DeepMatcher 和 Raha/HoloClean 分别使用 Schema F1、Entity F1、Cell F1，并单列 Repair Accuracy。所有调参只使用公开数据的 train/dev 或 train/valid；测试集标签只在评分阶段读取。

### 当前重跑总览

| 能力层 | 数据集 | 本项目当前方法 | 当前结果 | 公开基线/对照 | 对照结果 | 结论 |
|---|---|---|---:|---|---:|---|
| 问题解析 | EBM-NLP professional test | PICO context v3 | **0.4900 macro span F1** | 项目词典 v2 | 0.4662 | context v3 提升 0.0238；Interventions 0.4484 仍为短板 |
| 科学检索 | BEIR 5 tasks / 3,677 queries | BM25+BGE train/dev fusion | 0.3791 nDCG@10 | BGE-small-en-v1.5 | **0.3880** | 融合低 0.0088；BGE 单路保留为公开强基线 |
| 字段对齐 | Valentine 10 tasks | Schema Matcher v3 | **0.7994 Schema F1** | Valentine COMA | 0.7670 | 本项目高 0.0324；优势来自字段归一化和值画像 |
| 实体匹配 | DeepMatcher 5 tasks | learned entity v2 | 0.7408 Entity F1 | RecordLinkage Jaro-Winkler + logistic | **0.7440** | 本项目低 0.0032，结论是基本持平 |
| 错误检测 | Raha/HoloClean 5 comparable tasks | context consensus v4 | 0.5902 Cell F1 | Raha PVD+RVD | **0.8159** | 本项目低 0.2257；Flights/Rayyan 是主要缺口 |

清洗宏平均 `0.5902` 只在五个有可比公开基线的任务上计算，未把没有对应外部值的 Tax 强行加入对照。项目方法在六个公开清洗任务上的完整宏平均为 `0.6563`。这些宏平均只用于各能力层诊断，不能相加，也不能替代乳腺癌 SDTI。

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

本轮公开基准优化没有修改 `goldset/templates/`、冻结公式或医学规则。按用户要求追加的严格 Qwen LIVE 候选为 `official-candidate-qwen-live-user-request-20260902`：Retrieval F1 `0.9091`、Faithfulness `1.0000`、Traceability `1.0000`、Error F1 `1.0000`、Repair Accuracy `1.0000`，按冻结公式得到 SDTI `98.1118`；11/11 题实际调用 Qwen，确定性回退 0 次，质量门仍有 8 个 REVIEW，`frozen=false`，所以 `publish_allowed=false`。此前 `official-candidate-qwen-live-recall-v9-20260902` 的 `97.5278` 保留为历史运行，不覆盖本次结果。这不是本轮公开模块分数，也不是 sealed frozen test 成绩。

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

## 复现

图表由 `scripts/build_public_comparison_figures.py` 从历史 `results.json` 和增强检索运行文件读取后生成；未在脚本中手填增强结果分数。原始公开数据、测试划分、来源地址、运行文件和哈希记录在 `evaluation/public_benchmarks/enhanced_retrieval_20260902.json` 及其指向的运行文件中，历史模块对照仍以 `evaluation/github_competitor_benchmark_20260830/` 为准。
