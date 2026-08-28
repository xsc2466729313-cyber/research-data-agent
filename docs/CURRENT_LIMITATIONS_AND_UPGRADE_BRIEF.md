# 当前效果、问题与升级输入

更新时间：2026-08-28

本文只整理已经运行或已经在代码中确认的事实，供后续方案设计使用。公开基准成绩是能力层诊断，不是乳腺癌临床有效性，也不是 Qwen 模型本身的成绩。

## 一、结论先行

当前系统已经形成了“问题规划—文献检索—数据源发现—字段整合—实体关联—质量审核”的工程骨架。数据处理方面，字段对齐和结构化实体匹配提升最明显；格式型清洗也有效。问题解析和科学文献检索仍偏弱，语义变化大的实体匹配和缺失/语义错误清洗仍是瓶颈。

当前不能得出“Qwen-plus 已经优于其他模型”的结论。最近一次任务记录为 `used_qwen=false`，实际走了确定性备用流程；乳腺癌正式 Gold Set 仍为空，因此正式 SDTI 尚未产生。

## 二、已经取得的真实提升

| 能力层 | 数据集 | 当前方法 | 当前成绩 | 相对基线/说明 |
|---|---|---|---:|---|
| 问题解析 | EBM-NLP professional test | PICO context v3 | 宏平均 F1 `0.4900` | 项目词典 v2 为 `0.4662`，提升 `0.0238`；Participants 从 `0.4568` 到 `0.5230` |
| 文献检索 | BEIR 5 任务 | tuned BM25 | 宏平均 nDCG@10 `0.3147` | 稳定略高于默认 BM25；原哈希混合明显落后，不能继续当主方法 |
| 字段对齐 | Valentine 10 任务 | value-profile v2 | 宏平均 F1 `0.8451` | 当前规则 v1 为 `0.6856`，提升 `0.1595` |
| 实体匹配 | DeepMatcher 5 任务 | learned rule v2 | 宏平均 F1 `0.7408` | 当前规则 v1 为 `0.6608`，提升 `0.0800` |
| 数据清洗 | Raha/HoloClean 6 任务 | format-profile v2 | 宏平均 Cell F1 `0.4856` | 格式型任务高分，但缺失值和语义错误任务为 `0.0000`，不能只看平均值 |

### 具体数据整合效果

- 字段对齐：Capital Projects 从 `0.6667` 提升到 `1.0000`，Public Art Inventory 从 `0.3333` 提升到 `0.8889`，Energy Benchmarking 从 `0.6667` 提升到 `1.0000`。
- 字段对齐仍不稳定：DPR Athletic Facilities 为 `0.5882`，DSNY Disposal Assignments 为 `0.5333`。缩写、布尔列和重复取值会造成歧义。
- 实体匹配：DBLP-ACM 为 `0.9602`，Beer-RateBeer 为 `0.8125`；Amazon-Google 为 `0.5375`，Walmart-Amazon 为 `0.4939`。
- 清洗：Beers、Movies-1、Tax 分别为 `0.9837`、`0.8916`、`0.9868`；Flights 为 `0.0515`，Hospital 和 Rayyan 为 `0.0000`。

这些提升说明“规则、统计特征和数据画像”对结构化任务有帮助，但不能说明系统已经具备通用语义理解能力。

## 三、问题解析为什么只有 0.4900

EBM-NLP 测的是从医学摘要中找出 Participants、Interventions、Outcomes 片段，不是普通问答准确率。当前方法主要是词典、词组概率和局部上下文，因此存在以下原因：

1. **短语边界不准**：能看到 `treatment` 或 `response`，但不一定能准确找出完整干预/结局短语。
2. **上下文范围太短**：同一个词在研究对象、干预措施和结果描述中含义不同，局部窗口不够判断句法关系。
3. **医学表达变化大**：缩写、同义表达、否定句、比较句和复合终点会超出有限词典。
4. **标签粒度与业务目标不完全一致**：EBM-NLP 的 span 标注是通用医学摘要任务，不能直接等价为本项目 Research Contract 生成质量。
5. **当前提升主要来自词组先验**：Participants 有明显提升，但 Interventions 几乎不变，说明干预短语仍是主要错误来源。
6. **没有真正的序列标注模型**：当前还没有在训练集上训练 BIO/Span 分类模型，也没有使用医学预训练编码器做边界识别。

### 能不能提升

可以提升，但应把目标拆开：

- 先做医学摘要的实体/span 抽取，报告边界级 Precision、Recall、F1；
- 再做 Research Contract 的结构化解析，报告人群、暴露、结局、协变量和数据粒度的字段级准确率；
- 最后做专家认可率和 Evidence 支持率。

推荐技术路线是“规则召回候选 + 医学文本编码器或 LLM 结构化抽取 + 约束校验 + 低置信度人工复核”。不能只继续增加关键词，否则很可能只在当前测试集上小幅变化。

## 四、按能力层整理的缺点

### 1. 问题解析与科研规划

- F1 `0.4900` 仍低，尤其 Interventions F1 `0.4484`、Recall `0.3562`。
- ResearchFormulationAgent 仍保留乳腺癌新辅助治疗的固定候选模板；宽泛主题虽有通用 fallback，但还不是从论文中自主发现问题。
- 候选问题的 novelty、data availability 等部分是保守先验或启发式分数，不是系统综述或真实数据验证结果。
- Literature Evidence 能证明“论文提到过某些词”，不一定能证明完整因果关系或研究结论。
- Research Agent、Orchestrator 已有模块接口，但尚未完成所有 API 和默认端到端链路的统一接入。

### 2. 文献检索

- tuned BM25 宏平均 nDCG@10 只有 `0.3147`，属于可用基线，不是先进语义检索水平。
- 原哈希混合在 SciFact 为 `0.4070`、ArguAna 为 `0.0708`，低于 BM25，说明“加一个向量表示”不等于语义能力提升。
- 当前 Planning RAG 的默认 embedding 仍是 hashing fallback；真实医学 BGE、cross-encoder reranker 尚未完成同条件公开评测。
- 尚未完成 BM25、真实 Embedding、Hybrid、Hybrid+Reranker 的完整五组对照和延迟/成本分析。
- 中文问题、英文论文、医学缩写和跨语言同义表达的检索效果还没有单独统计。

### 3. 字段对齐

- 宏平均 F1 `0.8451` 较好，但任务间波动大，DPR/DSNY 仍明显较弱。
- 当前 v2 主要依赖字段名、别名、值集合重叠、基数和类型；对没有重复值、缩写密集或语义依赖强的列仍不稳。
- 新增的 SchemaMatcherV2 已能输出置信度和 AUTO/REVIEW/REJECT，但还需要用独立验证集校准 `0.90/0.65` 阈值。
- 尚未报告 Wrong Auto-Match Rate、Review Rate、按字段类型分层的误差。
- 公开 Valentine 任务是通用表字段匹配，不能直接代表乳腺癌 canonical schema 的医学字段映射效果。

### 4. 实体匹配与患者/样本关联

- Walmart-Amazon F1 `0.4939`，说明表达变化大的记录召回和精度都不足。
- 商品实体任务不能直接外推到患者身份；医学身份匹配需要更严格的 study、patient、sample 命名空间约束。
- 当前 learned rule v2 不是经过大规模医学实体标注训练的 Transformer matcher。
- 仍缺少医学数据上的实体 Gold Set，因此不能量化真实患者误合并率。
- 高置信度、低置信度和冲突记录的分层统计还不完整，尤其缺少 False Merge Rate 的正式结果。

### 5. 数据清洗与修复

- 宏平均 Cell F1 `0.4856` 被格式型高分拉高，不能理解为通用清洗能力强。
- Hospital、Rayyan 为 `0.0000`，Flights 仅 `0.0515`；缺失值、字符替换、日期语义和医学语义无法从单表安全推断。
- 当前容易做的是大小写、单位、数字格式、时间格式和明确别名；高风险字段仍需人工审核。
- 还没有把 Error Detection 和 Repair 完全作为两个独立任务系统评测。
- Repair Accuracy 高时可能只是修复了少量容易样本，因此必须同时报告 False Repair Rate、Auto Repair Coverage、Review Rate。

### 6. 后端模型与 Agent 评测

- 目前没有 Qwen-plus、DeepSeek、GLM 在同一数据、同一提示、同一工具、同一安全规则下的重复对照。
- 最近任务 `used_qwen=false`，因此当前运行结果不能作为 Qwen-plus 的实测成绩。
- 没有 20 至 50 个固定的乳腺癌科研问题和人工标准答案集。
- 没有完成 Qwen Alone、Qwen+RAG、Full Agent 的端到端对比。
- 没有正式测量模型成本、延迟、重复运行波动、工具选择稳定性和失败恢复率。
- Qwen 输出即使格式正确，也不代表其字段选择、数据源选择和医学解释正确；必须由程序和规则复核。

### 7. 数据与来源风险

- 外部数据库字段和接口可能变化，当前运行结果需要通过 source manifest 和哈希重新验证。
- 多 cohort 没有 crosswalk 时不能做患者级横向 Join；有同名 patient_id 也不能直接认为是同一个人。
- 公开基准的高分不能代表乳腺癌临床队列的可用性、代表性或外部有效性。
- 当前尚无真实乳腺癌 Gold Set，因此正式 SDTI、临床任务 Research-Ready Rate 和专家认可率都不能发布。

### 8. 前端与用户体验

- 前端已有分阶段规划界面，但当前没有完整的自动化视觉回归测试。
- 用户仍可能不清楚“当前阶段做什么、下一步是什么、为什么进入 REVIEW”。
- 技术指标、数据源、候选问题和最终可下载数据之间的关系需要更明确地串成一条流程。
- API 失败、文献为空、字段不足、数据源不可用和质量门阻断等状态需要统一展示，而不是只显示请求失败。
- 需要把“模型建议”“算法结果”“规则阻断”“人工待审核”四种状态在界面上明确区分。

## 五、不能做的事情

- 不能通过删掉失败任务、换成有利数据集或硬编码答案来提高分数。
- 不能把公开基准宏平均分写成乳腺癌临床效果。
- 不能把 Qwen 未调用时的备用流程成绩写成 Qwen 成绩。
- 不能因为字段匹配高分就自动放宽患者身份合并规则。
- 不能把 HER2 IHC 2+ 自动判为阳性，也不能把 ERBB2 CNA amplification 等同 HER2 IHC positive。
- 不能把细胞系 AUC/IC50 解释为患者 pCR 或临床 response。

## 六、交给 GPT 设计方案时应重点回答的问题

请下一份设计方案至少回答以下 12 个问题，并给出数据集、训练/验证/测试划分、模型、指标、消融实验和失败边界：

1. 如何把问题解析从词典/规则升级为真正的医学 span 或结构化抽取模型？
2. 如何同时优化 Participants、Interventions、Outcomes，而不是只提升某一个类别？
3. 如何把 EBM-NLP span F1 与 Research Contract 字段准确率、专家认可率连接起来？
4. 如何在不泄漏测试标签的前提下接入医学 Embedding 和 Reranker？
5. 如何公平比较 BM25、Embedding、Hybrid 和 Hybrid+Reranker？
6. 如何为乳腺癌 canonical schema 建立字段对齐 Gold Set，并校准 AUTO/REVIEW/REJECT 阈值？
7. 如何测量 Wrong Auto-Match Rate，而不是只报告 F1？
8. 如何建立患者/样本实体匹配 Gold Set，并正式报告 False Merge Rate？
9. 如何把清洗拆成 Error Detection、Repair Candidate 和 Human Review 三个可测模块？
10. 如何在保证医学安全的前提下提高缺失值和语义错误处理能力？
11. 如何设计 Qwen-plus、DeepSeek、GLM 的同条件多次重复端到端实验？
12. 如何建立 20 至 50 个乳腺癌科研问题的 Gold Set，并最终计算正式 SDTI？

## 七、建议的下一阶段验收条件

1. 问题解析：新增医学序列标注/结构化抽取基线，并在固定测试集上报告 span F1 和字段级指标。
2. 检索：完成五组方法的 BEIR 对照，至少报告 nDCG@10、Recall@100、MRR@10、延迟和成本。
3. 字段对齐：建立乳腺癌字段 Gold Set，报告 F1、Wrong Auto-Match Rate 和 Review Rate。
4. 实体匹配：建立患者/样本 Gold Set，报告 Entity F1、False Merge Rate 和 unresolved 比例。
5. 清洗：独立报告 Detection F1、Repair Accuracy、False Repair Rate、Auto Repair Coverage 和 Review Rate。
6. 端到端：用同一批问题比较 Qwen Alone、Qwen+RAG、Full Agent，并至少重复 3 次。
7. 正式发布：只有真实 Evidence、来源完整、规则通过且 Gold Set 评测完成后，才发布 Research-Ready Rate 和 SDTI。
