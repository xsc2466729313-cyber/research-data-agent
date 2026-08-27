# 科研数据 Agent：模型评价与选择说明报告

> 版本：2026-08-27
>
> 评价对象：以 Qwen-plus 为默认规划模型的 Full Agent，而不是单独的疾病预测分类器
>
> 结论状态：**可用于方案说明，模型优越性需补充同条件横向实验**

## 技术结论

本项目需要解决的不是“让一个大模型直接回答医学问题”，而是把宽泛科研方向转换成可执行研究方案，并从真实公开数据库生成可追溯、可审计、符合医学安全规则的科研数据集。因此，最终选择的是“Qwen-plus 负责自然语言理解和工具规划，确定性 Adapter、Schema、医学规则、实体对齐、Repair 与 Quality Gate 负责事实和安全”的混合 Agent 架构。

当前选择 Qwen-plus 的依据主要是中文科研问题理解、结构化输出、函数调用和国内 API 接入的工程适配性；**不是因为已经完成了 Qwen、DeepSeek、GLM 等模型的公平横向排名**。截至本报告，冻结 Gold Set 三张表均为 0 行，正式 SDTI 仍为 `NOT_EVALUATED`，最近一次任务也因模型调用未启用而使用了确定性兜底。因此，对外最稳妥的表述是：Qwen-plus 是当前默认规划模型，Full Agent 是当前推荐系统架构；基座模型的最终选择仍需统一实验确认。

## 1. 这个问题需要解决什么

系统要解决五个相互关联的问题：

1. **把宽泛想法变成明确科研问题。** 用户往往只会输入“哪些因素影响乳腺癌新辅助治疗疗效”，系统需要进一步确定研究人群、暴露或比较因素、观察结局、分析单位和数据粒度。
2. **找到真实且相关的数据。** 系统需要从 GEO、GDC、cBioPortal、ClinicalTrials.gov、CIViC 和论文中寻找可核验的 accession、URL、数据字段与证据，而不是生成看似合理的数据库名称。
3. **统一异构数据但不破坏医学语义。** 不同数据库字段命名、粒度和编码不同；标准化后仍必须保留 `source_id`、`raw_field` 和 `raw_value`。
4. **避免危险的数据拼接和医学误判。** 例如 HER2 IHC 2+ 不能直接判为阳性，ERBB2 CNA amplification 不能代替 HER2 IHC，低置信度患者/样本关联不得自动合并，细胞系药敏不能冒充患者临床疗效。
5. **判断结果能不能用于科研。** 不仅要有数据，还要检查研究问题匹配度、缺失、样本量、来源真实性、字段证据、冲突、可复现性和发布安全门。

因此，这不是单一分类、回归或生存模型问题，而是一个包含“问题理解—检索—结构化—整合—质量控制—科研交付”的多阶段科研数据工程问题。

## 2. 建模与系统实现思路

### 2.1 总体方法：概率模型负责理解，确定性系统负责事实

```text
宽泛研究方向
→ 文献与公开数据检索
→ 明确研究问题（Population / Exposure / Outcome）
→ 冻结 Research Contract
→ Source Broker 匹配数据集与字段覆盖
→ 真实 Adapter 采集
→ Canonical Schema 标准化
→ 患者/样本实体对齐
→ 医学规则、Repair、Quality Gate
→ 可分析数据集、Evidence 与评测报告
```

大模型只承担其擅长的语义任务：理解中文科研意图、补全检索关键词、生成结构化计划、选择工具和解释缺口。数据库事实、字段标准化、患者身份关联、医学硬规则和发布决策由可测试的确定性模块完成。

### 2.2 核心模块

| 模块 | 作用 | 为什么不能只交给大模型 |
|---|---|---|
| Research Planning | 从 Topic 形成研究问题和字段需求 | 需要真实论文 Evidence 与可行性门控 |
| Literature / RAG | 提取论文 Methods、数据 accession 和证据片段 | 需要真实 URL、PMID/DOI 和来源追踪 |
| Source Broker | 选择最小数据源组合、计算字段覆盖和 fallback | 需要结构化能力矩阵和访问状态核验 |
| Data Adapter | 调用 GEO、GDC、cBioPortal 等官方入口 | API 返回值不能由模型猜测 |
| Canonical Schema | 统一疾病、受体、基因、治疗和结局字段 | 冻结接口必须稳定、可回归测试 |
| Entity Alignment | 判断患者与样本是否安全关联 | 错误横向 Join 会制造虚假的患者记录 |
| Medical Rules | 执行 HER2、ERBB2 CNA、response_domain 等硬规则 | 医学红线不能由随机生成决定 |
| Repair / Quality Gate | 自动修复低风险错误，阻断高风险结果 | 需要确定性审计和 PASS/REVIEW/REJECT |

### 2.3 评价方法

评价分四层，不能混为一个总分：

1. **冻结 Gold Set + SDTI：**正式核心成绩。SDTI 为检索 F1、Faithfulness、Traceability、Error F1、Repair Accuracy 的五项几何平均乘 100。Gold Set 未冻结时必须为空。
2. **外部 Benchmark：**Cleaning F1、BEIR nDCG@10、Schema F1、Entity F1，用于和公开方法横向比较。
3. **Task-Adaptive Fitness：**评价当前数据是否适合当前科研问题，包括研究相关性、分析充分性、可追溯性与可靠性、可复用性。
4. **Quality Gate：**输出 PASS、REVIEW 或 REJECT；这是发布门槛，不是综合分数。

## 3. 为什么当前选择 Qwen-plus + Full Agent

### 3.1 选择 Qwen-plus 作为规划模型的原因

- **中文科研语义适配较好。** 本项目输入、字段解释和报告均以中文为主，同时包含 HER2、PIK3CA、pCR、RCB 等中英文混合术语。
- **结构化输出和函数调用适合 Agent 编排。** 模型需要输出 ResearchSpec，并在多个真实 Adapter 之间选择工具，而不是只生成自由文本答案。
- **API 接入和部署路径匹配当前工程。** 项目已完成 Qwen 兼容接口、临时会话、超时、确定性兜底和连接状态管理。
- **模型可以被替换。** Qwen 被限制在规划层，不是数据事实来源；即使模型不可用，确定性流程仍可运行，降低单一厂商和单一模型依赖。

需要强调：以上是**工程选择理由**，不是“Qwen-plus 已经在本项目横向实验中排名第一”的证据。

### 3.2 选择 Full Agent 而不是单模型的原因

Full Agent 的优势不在于回答更流畅，而在于它同时提供：

- 真实来源、accession、`source_id` 与行级溯源；
- 冻结 Canonical Schema 和原始值保留；
- 多源互证但禁止无依据的患者级跨库 Join；
- 确定性医学安全规则；
- 字段缺口、冲突和失败原因可见；
- Repair 审计和发布 Quality Gate；
- CSV、Excel、Parquet、字段字典和质量报告交付。

这些能力直接对应题目的核心验收目标：找得准、找得全、整得真、查得回、改得对。

## 4. 为什么其他方案不能直接替代

### 4.1 规则或关键词系统

**优点：**稳定、便宜、可复现，适合医学硬规则和字段校验。

**主要问题：**难以理解宽泛科研意图、同义表达、复合 PICO 条件和论文语境；很难自主形成研究方案。

**结论：**不能单独作为主规划器，但必须保留为 Full Agent 的安全底座。

### 4.2 Qwen-only 或普通聊天大模型

**优点：**问题改写和文字解释能力强。

**主要问题：**没有真实 Adapter、冻结 Schema、行级来源、实体对齐和 Quality Gate 时，容易把合理文本误当事实，把“找到数据集”误当“关键字段已经存在”。

**结论：**适合作为规划模型，不适合单独承担数据生产和发布决策。

### 4.3 单数据源 Agent

**优点：**链路简单、速度较快、身份边界容易控制。

**主要问题：**一个数据库往往只覆盖临床、组学、治疗或知识证据中的一部分。例如 METABRIC 可能有基因组和部分临床信息，但未必包含目标新辅助治疗响应；GEO 可能有表达与 pCR，却没有突变数据。

**结论：**可作低风险基线，但经常无法覆盖完整科研问题。

### 4.4 多数据源但没有规则和质量门

**优点：**表面字段覆盖率可能更高。

**主要问题：**最危险。它可能把不同研究、不同患者、不同 response domain 的记录拼在一起，把 CNA、IHC 和患者疗效混为一谈。覆盖率提高不代表科学真实性提高。

**结论：**不能用于自动发布；多源能力必须和 Join Policy、医学规则、Evidence、冲突处理一起使用。

### 4.5 DeepSeek、GLM 或其他大模型

当前 DeepSeek 用作主要 AI Judge，GLM 用作独立复核模型，并没有在同一批冻结任务、相同数据范围、相同工具权限和相同重复次数下作为 Subject Agent 与 Qwen-plus 公平对比。因此，目前不能严谨地说它们“不行”或“比分更低”。

它们可能存在的工程差异包括结构化输出稳定性、函数调用成功率、中文医学语义、延迟、成本和私有部署方式，但这些都需要真实运行数据验证。正确结论是：**其他基座模型不是被证明失败，而是尚未完成同条件替换实验。**

## 当前评价结果：能说明什么，不能说明什么

### 当前真实任务级诊断

最近一次任务产出 50 行、21 列数据，Task-Adaptive Fitness 为 88.41；四个维度分别为研究相关性 78.82%、分析充分性 80.61%、可追溯性与可靠性 98.00%、可复用性 98.11%。Quality Gate 为 `REVIEW`，因此不允许自动发布。

工具包还得到清洗残留清除率 100%、任务内 nDCG@10 98.96%、内部 Integration Macro-F1 83.33%。这些数值只能描述当前任务和当前候选集合，不能冒充 Hospital、BEIR、Valentine 或冻结 Gold Set 成绩。

### AI Judge 小样本探针

3 个检索案例中，Recall@3 为 100%，nDCG@3 为 75.40%，平均 Faithfulness 为 4.67/5，但平均 Claim Support Rate 仅为 46.67%，平均 Completeness 为 2.33/5。另一个 5 条记录的三模型候选评审中，模型一致率 80%，真实来源验证率 100%，但只有 40% 可进入待人工确认候选，60% 仍需人工复核。

这说明当前系统较擅长找到真实来源并保持叙述忠实，但“关键字段是否真的足以回答研究问题”仍是主要短板。

### 尚不能发布的结论

- 正式 Retrieval Precision、Recall、F1、Faithfulness、Traceability、Error F1、Repair Accuracy 和 SDTI 均未评测。
- Qwen-plus、DeepSeek、GLM、规则基线和不同 Agent 变体尚未完成公平横向实验。
- AI provisional SDTI 只能用于开发诊断，不能作为正式项目成绩。
- 最近一次任务 `used_qwen=false`，说明该任务实际验证的是确定性兜底链路，不是 Qwen-plus 的真实调用效果。

## 推荐的正式模型选择实验

1. 人工冻结 20–30 个 paper-grounded 科研任务和 Evaluation Contract。
2. 对 `rule_keyword`、`qwen_only`、`single_source_agent`、`multi_source_no_gate`、`full_agent` 使用完全相同的任务、数据版本、候选范围和评价脚本。
3. 对 Qwen-plus、DeepSeek、GLM 等基座模型分别运行至少 3 次，建议 5 次。
4. 报告均值、标准差、95% bootstrap CI、Win Rate、Gate Pass Rate、延迟和成本。
5. 同时展示 Schema F1 与 Entity F1，不只展示 Macro-F1；按疾病亚型、数据源、response domain、患者/样本关联置信度和风险等级分层。
6. 只有冻结 Gold Set、正式 SDTI 和关键安全层均通过后，才能把某一模型写成最终优胜模型。

## 最终答辩表述建议

“我们选择的不是一个直接给医学结论的大模型，而是一套以 Qwen-plus 为语义规划器、以真实数据库工具和确定性医学规则为事实与安全底座的 Full Agent。Qwen-plus 的优势是中文科研意图理解、结构化输出和函数调用适合当前工程；但我们不把它当 Ground Truth。规则基线缺少语义理解，纯大模型缺少来源与质量控制，单源方案覆盖不足，多源无门控方案存在错误患者拼接和医学语义混淆风险。当前任务级诊断显示系统可追溯性和可复用性较强，但研究相关性和分析充分性仍需提升，Quality Gate 仍为 REVIEW。基座模型谁最终最优，将通过同一冻结任务集上的多次横向实验决定，而不是凭主观判断。”

## 证据与口径

- 冻结公式：[`docs/06_评测指标与SDTI.md`](06_评测指标与SDTI.md)
- 统一评价体系：[`docs/UNIFIED_EVALUATION_SYSTEM_V2.md`](UNIFIED_EVALUATION_SYSTEM_V2.md)
- 评价配置：[`configs/evaluation_system_v2.yaml`](../configs/evaluation_system_v2.yaml)
- AI Judge 探针：[`evaluation/results_deepseek/comparison.json`](../evaluation/results_deepseek/comparison.json)
- 三模型候选评审：[`evaluation/ai_evaluation_result.json`](../evaluation/ai_evaluation_result.json)
