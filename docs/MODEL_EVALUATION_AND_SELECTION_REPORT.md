# 科研数据 Agent：问题定义、系统架构与模型评价

> 版本：2026-08-27
>
> 评价对象：以 Qwen-plus 为默认语义规划器的科研数据 Full Agent
>
> 评价状态：系统架构具备工程验证结果；基座模型优越性尚待冻结实验确认

## 摘要

本项目研究如何将宽泛的乳腺癌科研意图，转换为可执行、可验证、可审计的科研数据任务。直接使用大语言模型生成答案虽然能够改善自然语言交互，却不能可靠保证数据来源、字段含义、患者—样本关联和医学判断的真实性。问题的核心矛盾因此不是“模型能否回答”，而是“开放式语义理解能否与严格的数据真实性和医学安全约束同时成立”。

为解决这一矛盾，系统采用混合式科研数据 Agent：Qwen-plus 负责研究意图理解、问题形式化和工具规划；文献检索、数据源编排、真实数据采集、Canonical Schema 标准化、实体对齐、医学规则、错误修复和质量门由确定性模块执行。该设计将概率模型限制在语义规划层，将事实、约束和发布判断交给可测试、可追溯的工程管线。

评价体系由四部分构成：冻结 Gold Set 与 SDTI、外部 Benchmark、任务适配度以及 Quality Gate。当前任务级诊断显示，系统在可追溯性和可复用性方面较强，但研究相关性与分析充分性仍有提升空间；Quality Gate 为 `REVIEW`。由于正式 Gold Set 尚未建立，且最近一次任务未实际调用 Qwen-plus，现有结果只能支持“Full Agent 架构适合该任务”，不能支持“Qwen-plus 优于 DeepSeek、GLM 或其他基座模型”的结论。

## 1. 问题定义

### 1.1 研究目标

给定一个宽泛科研主题 (q)，系统需要生成三类相互一致的输出：

1. 可执行研究问题与 Research Contract；
2. 具有真实来源、统一语义和审计记录的可分析数据集 (D^ast)；
3. 包含质量状态、证据边界和复现信息的研究报告 (R)。

因此，系统目标可以表示为：

[
q longrightarrow left(C, D^ast, Right),
]

其中，(C) 为研究契约，规定研究人群、暴露或比较因素、结局、分析单位、字段需求和数据源边界。

### 1.2 核心矛盾

科研问题通常以自然语言提出，具有开放性、歧义性和上下文依赖；科研数据交付则要求来源真实、字段明确、实体关系可靠、医学语义一致。若仅依赖规则系统，难以理解复杂科研意图；若仅依赖大语言模型，又无法稳定满足事实与安全约束。

这意味着本任务不是一个单纯的分类、回归或生成问题，而是一个受证据和医学规则约束的多阶段决策问题：

[
max left(
mathrm{Relevance},
mathrm{Adequacy},
mathrm{Traceability},
mathrm{Reusability}
ight)
]

[
	ext{s.t.}quad
mathcal{C}_{source},
mathcal{C}_{schema},
mathcal{C}_{identity},
mathcal{C}_{medical},
mathcal{C}_{release}.
]

这里不将四个目标强行压缩为未经验证的单一加权函数；正式发布仍由独立 Quality Gate 决定。

### 1.3 系统必须解决的五个问题

| 问题 | 直接方法的不足 | 系统要求 |
|---|---|---|
| 研究问题形式化 | 宽泛题目缺少人群、暴露、结局和分析单位 | 生成可验证的 PICO/Research Contract |
| 真实数据发现 | 模型可能生成不存在的数据集或字段 | 返回可核验 accession、URL 和来源状态 |
| 异构数据统一 | 不同数据库字段、粒度和编码不一致 | 映射到冻结 Schema，同时保留原始值 |
| 实体与医学安全 | 错误 Join 或概念替代可制造虚假患者记录 | 执行身份置信度和医学硬规则 |
| 科研可用性判断 | “有数据”不等于“足以回答问题” | 评估证据覆盖、完整性、冲突与发布风险 |

## 2. 系统架构

### 2.1 总体结构

系统遵循“语义规划—确定性执行—规则约束—证据审计”的分层架构：

```text
Research Topic
      │
      ▼
Intent & Question Formulation
      │
      ▼
Literature / RAG ──────► Evidence
      │
      ▼
Research Contract
      │
      ▼
Source Broker ─────────► Coverage / Fallback / Access State
      │
      ▼
Official Data Adapters
      │
      ▼
Canonical Schema & Raw-value Preservation
      │
      ▼
Entity Alignment & Join Policy
      │
      ▼
Medical Rules & Repair
      │
      ▼
Quality Gate
      │
      ├────────► PASS: Dataset + Report
      ├────────► REVIEW: Human Adjudication
      └────────► REJECT: Blocked with Reasons
```

该架构不是多个模块的简单串联。每一层都接收上一层的结构化状态，并解决由上一层产生的新问题：问题形式化产生字段需求，字段需求推动数据源选择，多源数据又产生语义统一和实体对齐问题，最终由医学规则与质量门控制发布。

### 2.2 模块与瓶颈的对应关系

| 模块 | 输入 | 解决的瓶颈 | 输出 |
|---|---|---|---|
| Intent & Formulation | 宽泛研究主题 | 意图歧义、研究边界不清 | 候选问题、PICO、研究类型 |
| Literature / RAG | 问题与检索式 | 问题缺少论文和数据证据 | Evidence、PMID/DOI、accession |
| Research Contract | 问题与证据 | 研究目标无法直接执行 | 字段契约、指标、纳排标准 |
| Source Broker | 字段需求 | 单库覆盖不足、访问状态不明 | 最小来源组合、覆盖率、fallback |
| Data Adapters | 数据源计划 | 模型无法保证 API 事实 | 真实响应、来源标识、采集状态 |
| Canonical Schema | 原始异构记录 | 字段含义和编码不一致 | 标准字段与 `raw_field/raw_value` |
| Entity Alignment | 患者、样本和检测记录 | 错误患者级横向 Join | 匹配置信度、unresolved/review |
| Medical Rules | 标准化记录 | 医学概念替代和危险推断 | 规则结果、冲突和阻断原因 |
| Repair & Quality Gate | 数据与错误清单 | 低风险错误和高风险错误混合 | Repair 审计、PASS/REVIEW/REJECT |

### 2.3 语义模型与确定性模块的边界

设大语言模型为 (M_	heta)，确定性执行系统为 (G)。系统输出不是由 (M_	heta) 直接生成，而是：

[
left(C,D^ast,Right)
=
G!left(
M_	heta(q,E),
S,
A,
J,
H,
Q
ight),
]

其中：

- (E)：文献与数据证据；
- (S)：冻结 Canonical Schema；
- (A)：真实数据源 Adapter；
- (J)：实体对齐与 Join Policy；
- (H)：医学安全规则；
- (Q)：质量门与发布规则。

这一分解的关键作用是：即使 (M_	heta) 输出不稳定，事实数据、身份关系、医学边界和发布状态仍不能被模型自由改写。

### 2.4 医学安全约束

系统至少执行以下冻结约束：

1. HER2 IHC 2+ 不得自动判为 HER2 Positive；
2. ERBB2 CNA amplification 不等同 HER2 IHC positive；
3. 低置信度患者/样本关联进入 `unresolved/review`；
4. 高权威来源之间的不可解释冲突不得自动选边；
5. 细胞系 `AUC/IC50` 与患者 `pCR/response` 必须由 `response_domain` 区分。

这些约束决定了模型架构：医学判断不能作为提示词建议存在，而必须成为数据管线中的可测试规则。

## 3. 评价指标

### 3.1 指标设计原则

指标从任务目标反推，而不是将所有可计算数值合并为一个总分：

- 检索指标回答“是否找到正确证据”；
- 忠实度与可追溯性回答“结论是否有来源支持”；
- 错误检测与修复指标回答“系统能否发现并纠正数据问题”；
- 任务适配度回答“数据是否足以支持当前科研问题”；
- Quality Gate 回答“结果是否允许发布”。

### 3.2 冻结 Gold Set 指标

设 (TP)、(FP)、(FN) 分别为真阳性、假阳性和假阴性，则：

[
mathrm{Precision}=rac{TP}{TP+FP},
qquad
mathrm{Recall}=rac{TP}{TP+FN},
]

[
mathrm{F1}
=
rac{2cdot mathrm{Precision}cdot mathrm{Recall}}
{mathrm{Precision}+mathrm{Recall}}.
]

正式核心指标包括：

| 指标 | 含义 | 建议目标 |
|---|---|---:|
| Retrieval F1 | 正确记录的检索完整性与准确性 | (ge 90%) |
| Faithfulness | 结论是否忠实于真实来源 | (ge 95%) |
| Traceability | 输出是否可追溯到来源 | (100%) |
| Error Detection F1 | 错误发现的准确性与完整性 | (ge 90%) |
| Repair Accuracy | 修复后结果是否正确 | (ge 90%) |

SDTI 按冻结公式计算：

[
mathrm{SDTI}
=
100	imes
left(
mathrm{Retrieval F1}
	imes mathrm{Faithfulness}
	imes mathrm{Traceability}
	imes mathrm{Error F1}
	imes mathrm{Repair Accuracy}
ight)^{1/5}.
]

建议目标为：

[
mathrm{SDTI}ge 90.
]

几何平均能够惩罚单项短板：任一环节明显失效，都不能被其他高分完全抵消。

### 3.3 外部 Benchmark

外部 Benchmark 用于与公开任务和已有方法比较：

| 能力 | 指标 | 作用 |
|---|---|---|
| 数据清洗 | Cleaning Precision/Recall/F1 | 衡量错误发现与清洗质量 |
| 信息检索 | nDCG@10、Recall@k、MRR | 衡量证据排序与召回 |
| Schema Matching | Schema Precision/Recall/F1 | 衡量字段语义映射 |
| Entity Resolution | Entity Precision/Recall/F1 | 衡量患者、样本和实体对齐 |

外部成绩必须使用公开数据集、固定版本和官方评价脚本。任务内部候选集上的指标不得冒充外部 Benchmark。

### 3.4 任务适配度

任务适配度用于诊断当前交付是否适合当前研究问题，包括：

| 维度 | 回答的问题 |
|---|---|
| Relevance | 数据对象、变量和结局是否与研究问题相关 |
| Adequacy | 样本量、字段覆盖和证据是否足以支持分析 |
| Traceability | 数据、字段和结论是否能够追溯 |
| Reusability | 数据格式、字典和处理记录是否支持复现 |

该指标属于任务级工程诊断，不等同于正式 SDTI。

### 3.5 发布质量门

Quality Gate 独立于综合得分：

| 状态 | 含义 | 发布策略 |
|---|---|---|
| PASS | 关键证据、规则和质量要求满足 | 允许发布 |
| REVIEW | 存在不确定性或待人工裁决事项 | 禁止自动发布 |
| REJECT | 存在关键缺失、冲突或安全违规 | 阻断输出 |

若虚假来源超过 1 条、Faithfulness 低于 90%，或 Traceability 低于 95%，系统不得自动发布。

## 4. 实验设计

### 4.1 评价对象

需要区分两个实验问题：

1. **架构问题：**Full Agent 是否优于更简单的系统变体？
2. **基座模型问题：**在相同 Agent 架构中，Qwen-plus、DeepSeek、GLM 等规划器谁更合适？

若将二者混在一次实验中，无法判断性能差异来自模型本身，还是来自工具、规则和数据源能力。

### 4.2 架构消融

在相同任务、字段契约、数据快照和评价脚本下比较：

| 变体 | 保留能力 | 用于检验的假设 |
|---|---|---|
| `rule_keyword` | 规则与关键词 | 语义规划是否必要 |
| `qwen_only` | 仅语言模型 | 确定性工具与约束是否必要 |
| `single_source_agent` | Agent + 单一数据源 | 多源编排是否提升覆盖 |
| `multi_source_no_gate` | 多源 Agent，无质量门 | Quality Gate 是否阻止危险结果 |
| `full_agent` | 完整系统 | 各模块联合后的总体效果 |

这一实验对应架构归因：只有当 Full Agent 相比消融变体稳定改善正式指标，才能说明收益来自系统机制，而不是单纯增加复杂度。

### 4.3 基座模型对照

基座模型对照应固定：

- 冻结任务集与 Gold Set；
- 数据源版本与访问权限；
- Research Contract 和工具集合；
- 最大调用次数、温度、超时和重试策略；
- 评价脚本与发布阈值。

每个模型至少重复 3 次，建议重复 5 次，并报告均值、标准差、95% bootstrap 置信区间、Win Rate、Gate Pass Rate、延迟和成本。

### 4.4 分层分析

Macro-F1 可能掩盖局部失败，因此结果还应按以下维度分层：

- 乳腺癌亚型；
- 数据源；
- 字段类型；
- 临床、组学和知识证据模态；
- `response_domain`；
- 患者/样本关联置信度；
- 医学风险等级。

## 5. 当前结果与分析

### 5.1 正式评价尚未完成

截至 2026-08-27，冻结 Gold Set 三张表均为 0 行，正式核心指标为空，系统状态为 `NOT_EVALUATED`：

| 指标 | 当前正式结果 |
|---|---|
| Retrieval Precision / Recall / F1 | 未评测 |
| Faithfulness | 未评测 |
| Traceability | 未评测 |
| Error Detection Precision / Recall / F1 | 未评测 |
| Repair Accuracy | 未评测 |
| SDTI | 未评测 |

因此，当前不能发布正式系统成绩，也不能据此宣称某一基座模型最优。

### 5.2 任务级诊断暴露的主要短板是证据充分性

最近一次任务生成 50 行、21 列数据，综合 Task-Adaptive Fitness 为 88.41%，Quality Gate 为 `REVIEW`。

| 维度 | 得分 |
|---|---:|
| 研究相关性 | 78.82% |
| 分析充分性 | 80.61% |
| 可追溯性与可靠性 | 98.00% |
| 可复用性 | 98.11% |

可追溯性和可复用性接近 98%，说明来源记录、字段字典和处理链条已经形成；相关性和充分性明显较低，说明当前瓶颈不再只是“能否找到数据”，而是“找到的数据是否包含回答研究问题所需的关键字段和样本结构”。这一结果将下一阶段的优化重点指向 Evidence Coverage、字段可用性核验和数据集筛选，而不是继续增加界面信息或自由文本生成。

### 5.3 内部工具指标不能替代外部 Benchmark

当前工具包得到：

- 清洗残留清除率：100%；
- 任务内 nDCG@10：98.96%；
- 内部 Integration Macro-F1：83.33%。

这些数值来自当前任务和内部候选集合，只能用于开发诊断。它们没有使用对应公开 Benchmark 的固定样本与官方评价脚本，因此不能标记为 Hospital、BEIR、Valentine 或正式 Gold Set 成绩。

### 5.4 AI Judge 探针说明“找到来源”仍不等于“证据充分”

在 3 个检索案例中：

| 指标 | 结果 |
|---|---:|
| Recall@1 | 33.33% |
| Recall@3 | 100.00% |
| nDCG@3 | 75.40% |
| 平均 Faithfulness | 4.67 / 5 |
| 平均 Completeness | 2.33 / 5 |
| Claim Support Rate | 46.67% |

结果表明，系统能够在前三个候选中召回相关来源，并保持较高的语言忠实度；然而，只有不足一半的关键主张获得充分证据支持，完整性评分也偏低。其主要问题不是来源完全虚假，而是来源所含字段不足以支撑完整研究结论。

该实验仅包含 3 个案例，并由 DeepSeek 作为 AI Judge，属于探索性探针，不构成统计显著性证据。

### 5.5 当前结果没有验证 Qwen-plus 的真实增益

最近一次任务记录为 `used_qwen=false`，实际运行的是确定性回退链路。由此可以区分两类结论：

- 已获得支持：确定性规划、数据编排、溯源和质量门能够独立完成任务流程；
- 尚未获得支持：Qwen-plus 相比规则回退或其他大模型带来了多少增益。

因此，当前结果支持 Full Agent 的工程可用性，不支持 Qwen-plus 的模型优越性。

## 6. 模型选择分析

### 6.1 选择 Full Agent 的依据

Full Agent 被选为主架构，是因为它同时满足本任务的五类目标：

1. 大语言模型处理开放式科研意图；
2. 真实 Adapter 保证数据来自实际接口；
3. 冻结 Schema 与原始值保留保证语义和审计；
4. 实体对齐与医学规则控制高风险错误；
5. Repair 和 Quality Gate 将不确定性显式转化为复核或阻断状态。

其优势不是“文本回答更自然”，而是将语义能力与事实约束分离，使系统能够在模型不稳定或不可用时保持安全边界。

### 6.2 选择 Qwen-plus 作为当前规划器的依据

当前选择基于工程适配，而非正式排名：

- 中文科研语义和中英文医学术语混合理解符合主要交互场景；
- 结构化输出与函数调用适合 Research Contract 和工具编排；
- 已完成 API、超时、临时会话和确定性 fallback 接入；
- 模型位于可替换 provider 接口后，不构成数据事实来源。

Qwen-plus 的定位是“语义规划器”，而不是 Ground Truth、医学裁决器或数据生成器。

### 6.3 替代方案的局限

| 方案 | 优点 | 根本局限 | 合理定位 |
|---|---|---|---|
| 规则/关键词 | 稳定、便宜、可复现 | 难以理解复杂意图和论文语境 | 安全规则与 fallback |
| 纯 LLM | 语言理解和生成灵活 | 无法可靠保证来源、字段、实体和医学安全 | 问题改写与规划原型 |
| 单数据源 Agent | 链路简单、身份边界清楚 | 临床、组学、治疗和结局覆盖不足 | 窄域基线 |
| 多数据源无质量门 | 表面覆盖较高 | 错误 Join 和语义混合会传播到结论 | 风险消融基线 |
| Full Agent | 规划、数据、规则和审计闭环 | 复杂度、延迟和成本较高 | 当前推荐架构 |

DeepSeek、GLM 或其他大模型并非已经被证明“不适用”。它们尚未在完全相同的任务、工具权限、数据范围和重复次数下作为 Subject Agent 完成公平对照。现阶段只能讨论工程差异，不能给出优劣排名。

## 7. 误差、局限与稳健性

### 7.1 误差传播路径

| 误差来源 | 进入环节 | 直接影响 | 最终风险 | 主要监测指标 |
|---|---|---|---|---|
| 研究问题歧义 | Intent/Formulation | 字段和结局定义错误 | 检索方向偏离 | Relevance、人工改写率 |
| 文献或数据源覆盖不足 | Literature/Source Broker | 关键字段缺失 | 分析结论不充分 | Adequacy、Claim Support |
| Schema 映射错误 | Normalization | 变量语义改变 | 统计分析失真 | Schema F1 |
| 实体错误关联 | Entity Alignment | 不同患者或样本被合并 | 制造虚假病例 | Entity F1、review rate |
| 医学概念替代 | Medical Rules | HER2/CNA/response 混淆 | 高风险医学误判 | Safety violation count |
| 模型输出不稳定 | Planning | 工具和字段计划波动 | 结果复现性下降 | 方差、Win Rate、fallback rate |

误差分析必须沿该链路定位，不能只用一个总分掩盖具体失效环节。

### 7.2 当前局限

1. 正式 Gold Set 尚未冻结，无法计算官方 SDTI；
2. 当前 AI Judge 样本量小，且存在模型裁判偏差；
3. 最新任务未实际调用 Qwen-plus，无法估计其边际贡献；
4. 缺少同条件架构消融与基座模型横向实验；
5. 当前结果尚未覆盖足够多的疾病亚型、数据源和 response domain；
6. 外部数据源的访问状态和字段可用性会随时间变化，需要运行时核验。

### 7.3 稳健性检验计划

正式实验应至少包含：

- 不同随机种子和模型温度下的重复运行；
- 数据源不可用、超时或字段缺失情景；
- 关键字段和证据片段扰动；
- 患者/样本匹配置信度阈值变化；
- 不同乳腺癌亚型和研究范式的跨任务验证；
- 去除单个模块后的反事实消融。

只有当模型排序和 Quality Gate 结论在上述扰动下保持稳定，才能将模型选择视为稳健结论。

## 8. 结论

本项目的关键问题不是选择一个能够生成医学文本的单一模型，而是建立一套能够把开放式科研意图转化为可靠科研数据的受约束系统。单纯规则方法缺少语义理解，纯大模型缺少事实和安全保证；因此，最自然的模型结构是由大语言模型承担语义规划，由确定性模块承担数据事实、实体关系、医学规则和发布控制。

当前结果表明，Full Agent 已形成较强的可追溯和可复用能力，但证据相关性与分析充分性仍是主要瓶颈。系统下一阶段应优先提升字段级 Evidence Coverage、数据集可用性核验和同条件消融实验，而不是根据小样本 AI 评审提前宣布基座模型优胜。

因此，现阶段可得出的正式结论是：

> **Full Agent 是当前推荐的系统架构；Qwen-plus 是当前工程适配的默认语义规划器。前者已有任务级工程证据支持，后者的相对优越性仍需冻结 Gold Set 和公平横向实验验证。**

## 复现与评价依据

- [冻结评测指标与 SDTI](06_评测指标与SDTI.md)
- [统一评价体系 V2](UNIFIED_EVALUATION_SYSTEM_V2.md)
- [评价配置](../configs/evaluation_system_v2.yaml)
- [DeepSeek AI Judge 探针](../evaluation/results_deepseek/comparison.json)
- [三模型候选评审](../evaluation/ai_evaluation_result.json)
