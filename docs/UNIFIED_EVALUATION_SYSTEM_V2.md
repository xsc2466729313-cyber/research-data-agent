# 统一评价体系 v2：模型对比、横向结果与分层评测

本文档把新增的“科研数据 Agent 统一评测方案工具包”融合进主项目。它是 `docs/06_评测指标与SDTI.md` 的扩展层，不修改其中任何冻结公式；正式 SDTI 仍只能由经验证、冻结的 Gold Set 计算。

## 1. 评价体系总结构

v2 评价体系分四层：

| 层级 | 回答的问题 | 主输出 | 是否可作为真实成绩 |
|---|---|---|---|
| 外部 Benchmark | 系统是否具备通用清洗、检索和异构整合能力 | Cleaning F1、nDCG@10、Schema/Entity F1 | 可以，前提是同环境真实运行并记录来源 |
| 冻结 Gold Set + SDTI | 本项目核心链路是否找得准、整得真、查得回、修得对 | 冻结 SDTI 十项指标 | 可以，前提是 Gold Set 验证通过 |
| Task-Adaptive Fitness | 结果是否适合当前科研问题 | Fitness Score、缺口反馈 | 任务级适用性，不冒充公共 benchmark |
| Quality Gate | 数据是否允许发布或进入科研分析 | PASS / REVIEW / REJECT | 发布准入结论，不是漂亮总分 |

配置入口为 `configs/evaluation_system_v2.yaml`，统一结果表模板为 `data/evaluation_templates/unified_results_template.csv`。

## 2. 指标设计

### 2.1 冻结核心指标

以下指标继续以 `docs/06_评测指标与SDTI.md` 为唯一公式来源：

- Retrieval Precision / Recall / F1
- Faithfulness
- Traceability
- Error Precision / Recall / F1
- Repair Accuracy
- SDTI

这些指标服务项目核心可信整合能力。未运行真实 Gold Set 时必须保持 `NOT_EVALUATED/null`。

### 2.2 外部 Benchmark 指标

外部 Benchmark 用于横向对比，不替代 SDTI。

| 能力 | 数据/任务 | 主指标 | 辅助指标 | 建议 Baseline |
|---|---|---|---|---|
| 数据清洗 | Hospital、Flights、Beers | Cell-level F1 | Precision、Recall、Repair Accuracy、Latency | HoloClean、Raha+Baran、Cocoon |
| 科学检索 | BEIR SciFact、NFCorpus | nDCG@10 | Recall@100、MRR@10、Latency | BM25、Contriever、BGE-M3 |
| Schema Matching | Valentine | Schema F1 | Precision、Recall、Runtime | Jaccard、COMA、Cupid |
| Entity Matching | DBLP-ACM、Walmart-Amazon | Entity F1 | Precision、Recall、Runtime | Fuzzy Rule、DeepMatcher、Ditto |

Integration Macro-F1 只能作为项目内部总览：

```text
Integration Macro-F1 = (Schema F1 + Entity F1) / 2
```

报告中必须同时展示 Schema F1 和 Entity F1，不能只展示汇总值。

### 2.3 Task-Adaptive Fitness

真实科研任务不能用固定字段列表一刀切。流程必须是：

```text
Research Question
→ Evaluation Contract
→ Freeze
→ Agent Run
→ Fitness Evaluation
→ Gap Feedback / Quality Gate
```

固定一级维度：

| 维度 | 评价重点 |
|---|---|
| Research Relevance | 人群、暴露/变量、结局、时间和分析单位是否匹配研究问题 |
| Analytical Adequacy | 样本量、缺失、结局变异、时间逻辑、泄漏风险是否支持目标分析 |
| Traceability & Reliability | source_id、真实来源、Evidence、版本、冲突处理是否完整 |
| Reusability | 字段字典、raw value 保留、机器可读导出、复现信息是否完备 |

每个二级项采用 0-4 分，四个一级维度归一化到 0-1 后计算：

```text
Fitness = 100 * geometric_mean(relevance, adequacy, traceability, reusability)
```

若 Quality Gate 为 `REVIEW` 或 `REJECT`，Fitness 不得作为可发布成绩，只能作为诊断反馈。

## 3. 模型对比设计

模型对比要同时回答两个问题：

1. 基座模型能力差异带来了什么变化？
2. 多源整合、Quality Gate、Adaptive Fitness 等系统设计带来了什么变化？

因此结果表必须保留 `method_id` 和 `base_model_id` 两列。

| method_id | 对比目的 | 千问 | 多源 | Quality Gate | Adaptive Fitness |
|---|---|---:|---:|---:|---:|
| `rule_keyword` | 最弱规则/关键词基线 | 否 | 否 | 否 | 否 |
| `qwen_only` | 看单模型理解与生成能力 | 是 | 否 | 否 | 否 |
| `single_source_agent` | 看 Agent 编排但不依赖多源互证 | 是 | 否 | 是 | 是 |
| `multi_source_no_gate` | 看多源带来的覆盖提升与风险 | 是 | 是 | 否 | 是 |
| `full_agent` | 完整系统主结果 | 是 | 是 | 是 | 是 |

所有模型对比必须满足：

- 同一科研任务；
- 同一冻结 Evaluation Contract；
- 同一候选数据范围、数据版本和时间窗口；
- 同一评价脚本版本；
- 能固定随机种子时固定随机种子；
- LLM 随机性实验至少重复 3 次，建议 5 次；
- 报告均值、标准差、95% bootstrap CI 和 Win Rate。

不得通过换任务、换数据上限或换 Gold Set 来制造优势。

## 4. 横向对比结果

横向结果指“同一指标、同一数据或任务下，不同方法并排比较”。正文推荐使用横向条形图或点图，表格用于精确值。

必须准备 6 张核心横向表：

| 表 | 行 | 列 |
|---|---|---|
| Cleaning Benchmark | HoloClean / Raha+Baran / Cocoon / Qwen-only / Full Agent | Hospital F1、Flights F1、Beers F1、Macro-F1、Latency |
| Retrieval Benchmark | BM25 / Contriever / BGE-M3 / Qwen-only / Full Agent | SciFact nDCG@10、SciFact Recall@100、NFCorpus nDCG@10、Latency |
| Integration Benchmark | Jaccard/COMA/Cupid 或 DeepMatcher/Ditto 等 | Schema F1、Entity F1、Runtime |
| SDTI Gold Set | Rule / Qwen-only / Single-source / Multi-source No-Gate / Full Agent | 十项冻结指标、SDTI、Safety Gate |
| Quality Gate Ablation | No Gate / Source Gate / +Integration Gate / Full Gate | Critical Error、False Acceptance、Traceability、Coverage、Latency |
| Fitness Domain Tasks | Rule / Qwen-only / Single-source / Multi-source No-Gate / Full Agent | Mean Fitness、Median、Win Rate、Gate Pass Rate、CI |

`data/evaluation_templates/unified_results_template.csv` 是这些表的统一长表格式。正式填数前，`value/mean/std/ci95_*` 必须为空，不得用推测值占位。

## 5. 分层对比

分层对比用于暴露平均分掩盖的问题。每个结果行都必须允许按 `stratum_name/stratum_value` 聚合。

必报分层：

| stratum_name | 例子 | 目的 |
|---|---|---|
| `benchmark_dataset` | Hospital、SciFact、Valentine、DBLP-ACM | 防止只挑最容易的数据集 |
| `research_task_type` | response_analysis、survival_analysis、molecular_association | 看不同科研设计的适配能力 |
| `disease_subtype` | HER2_positive、TNBC、HR_positive_HER2_negative | 看乳腺癌亚型差异 |
| `source_type` | GDC、GEO、cBioPortal、ClinicalTrialsGov、CIViC | 看不同来源解析稳定性 |
| `response_domain` | clinical、preclinical_cell_line、clinical_trial、knowledge_evidence | 防止细胞系药敏和患者疗效混淆 |
| `evidence_level` | official_accession、PMID_or_DOI、curated_database、secondary | 看证据强度 |
| `patient_sample_link_confidence` | high、medium、low、unresolved | 看实体关联风险 |
| `error_type` | missing、typo、unit、duplicate、semantic_ambiguity | 看修复短板 |
| `missingness_band` | 0-10%、10-30%、30-50%、>50% | 看缺失压力 |
| `risk_level` | low、medium、high | 看医学安全边界 |

分层报告规则：

- 同时报告 macro average 和 weighted average；
- 小样本层不删除，标注 `small_n`；
- 每张总表必须列出 worst stratum 和主要失败原因；
- 高风险层即使样本少，也必须单独展示；
- 分层结果不得自动覆盖医学安全规则。

## 6. Quality Gate 与反馈闭环

Quality Gate 输出三态：

- `PASS`：可进入最终科研数据集；
- `REVIEW`：需要模型仲裁或人工复核；
- `REJECT`：禁止发布，并触发重新检索、解析、标准化或整合。

建议消融：

| Variant | Gate 组成 | 观察重点 |
|---|---|---|
| No Gate | 无 | Critical Error 和 False Acceptance 上限 |
| Source Gate | 来源真实性 | 虚假来源率下降 |
| Source + Integration Gate | 来源 + Schema/Entity/Conflict | 错误对象关联下降 |
| Full Gate | 来源 + 整合 + Traceability + Task-critical + 医学规则 | 可发布质量与覆盖率权衡 |

主图使用 Quality-Coverage Trade-off：

```text
x = Auto-Publish / Coverage
y = 1 - Critical Error Rate
```

## 7. 多 AI Judge 定位

多 AI Judge 只能用于程序无法确定的语义评价项，例如 outcome 语义等价、Evidence 是否足以支持结构化事实、ResearchSpec 相关等级等。

禁止交给 AI Judge 的项目：

- 样本量、缺失率、重复数；
- URL/accession 是否存在；
- Schema 类型合法性；
- 原始 API exact value；
- HER2 IHC 2+、ERBB2 CNA、response_domain 等确定性医学硬规则。

必须报告：

- Weighted Cohen's kappa；
- Agreement with Human；
- Coverage；
- Abstention Rate；
- Human Review Rate；
- Cost per item。

多 AI Judge 是降低人工复核负担的机制，不是制造 Ground Truth 的机制。

## 8. 交付物与使用方式

新增交付物：

- `configs/evaluation_system_v2.yaml`：统一评价体系配置；
- `data/evaluation_templates/unified_results_template.csv`：模型对比、横向对比、分层对比统一结果长表；
- `docs/UNIFIED_EVALUATION_SYSTEM_V2.md`：本设计文档。

推荐落地顺序：

1. 先补齐 20-30 个 paper-grounded 科研任务和冻结 Evaluation Contract；
2. 跑外部 Benchmark，建立 Cleaning / Retrieval / Integration 横向基线；
3. 在同一任务集上跑 `rule_keyword`、`qwen_only`、`single_source_agent`、`multi_source_no_gate`、`full_agent`；
4. 生成横向表、分层表、Quality Gate 消融图；
5. 最后才发布有来源、有 run artifact、有 Gold Set 或 Evaluation Contract 支撑的结果。

任何没有真实运行、没有 `source_id`、没有冻结 Contract 或 Gold Set 支撑的数字，都只能保留为空，不能写成系统成绩。
