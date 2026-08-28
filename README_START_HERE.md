# Codex 项目启动包：从这里开始

## 你是谁

你正在实现一个“乳腺癌精准治疗科研数据智能整合系统”。

## 第一次进入仓库必须按顺序阅读

1. `AGENTS.md`
2. `docs/00_项目总览.md`
3. `docs/01_总任务书.md`
4. `docs/02_系统架构.md`
5. `docs/03_数据源与测试数据集.md`
6. `docs/04_Canonical_Schema.md`
7. `docs/05_医学安全规则.md`
8. `docs/06_评测指标与SDTI.md`
9. `docs/07_GoldSet构建.md`
10. `docs/08_Demo与验收.md`

之后再开始执行 `prompts/` 中对应阶段的任务。

## 最核心的产品目标

系统要证明五件事：

- 找得准：Retrieval Precision
- 找得全：Retrieval Recall
- 整得真：Faithfulness
- 查得回：Traceability
- 改得对：Repair Accuracy

并以 `SDTI` 作为创新型综合可信指标。

## 禁止事项

- 不得伪造数据源、DOI、PMID、GSE、NCT、数据集或评测成绩。
- 不得自行修改冻结 Schema。
- 不得把 HER2 IHC、HER2 FISH、ERBB2 CNA 当成完全相同字段。
- 不得把细胞系药敏直接解释为患者临床疗效。
- 低置信度患者/样本匹配不得自动合并。
- 无 Evidence 的关键字段不得进入正式发布集。
- Gold Set 不能仅凭一个 AI 模型输出直接作为真值。

## 当前开发原则

先用 Mock 数据跑通端到端链路，再逐个接真实数据 Adapter。

## 当前阶段状态

主执行流程为 `prompts/00` 至 `prompts/10`，共 11 个阶段：

当前已完成 `11 / 11` 个阶段，剩余 `0` 个阶段。

- `00` 最小闭环：已完成
- `01` GDC Adapter：已完成，见 `docs/GDC_ADAPTER.md`
- `02` GEO Adapter：已完成，见 `docs/GEO_ADAPTER.md`
- `03` cBioPortal Adapter：已完成，见 `docs/CBIOPORTAL_ADAPTER.md`
- `04` AACT / ClinicalTrials.gov Adapter：已完成，见 `docs/AACT_ADAPTER.md`
- `05` CIViC Adapter：已完成，见 `docs/CIVIC_ADAPTER.md`
- `06` 标准化与融合：已完成，见 `docs/NORMALIZATION_INTEGRATION.md`
- `07` 评测与 SDTI：已完成，见 `docs/EVALUATION_SDTI.md`
- `08` AI 辅助 Gold Set：已完成，见 `docs/GOLDSET_AI_CURATION.md`
- `09` Repair 质量闭环：已完成，见 `docs/REPAIR_LOOP.md`
- `10` 前端完整化：已完成，见 `docs/FRONTEND_COMPLETE.md`

当前 `prompts/00` 至 `prompts/10` 已全部实现。后端保留阶段 00 Mock 链路，同时启用真实 GDC、NCBI GEO、cBioPortal、AACT/ClinicalTrials.gov 与 CIViC Adapter；真实数据 Adapter 的大型下载功能默认关闭或限量返回。阶段 06 提供可追溯标准化与安全融合；阶段 07 提供 Gold Set 门控评测；阶段 08 提供初标候选、独立模型复核、官方来源验证、确定性医学规则和人工 review queue；阶段 09 提供确定性错误自动修复、高风险 review、非破坏性重复隔离、修复前后审计和再次质量验证；阶段 10 提供科研任务入口、高级筛选、进度、候选与最终数据、指标、Evidence、Repair 记录和真实 CSV/Parquet 下载。当前 Gold Set 模板仍为空，所以系统不对外宣称任何真实评测成绩。

在阶段 00–10 骨架之上，当前主产品已经重构为 **v2 千问科研数据 Agent**：前端调用 `/api/agent/tasks`，由千问结构化解析科研问题并通过函数调用选择真实 Adapter；系统以临床样本锚定 cBioPortal 队列，防止分子孤立记录制造高缺失率，并可下载解析 GSE76360 Series Matrix，生成 50 名 HER2 阳性患者的基线治疗响应队列。页面提供中文数据值与字段字典、真实清洗记录、结局/变量匹配指标、点线式数据溯源以及 CSV/Parquet/Excel 导出。阶段 00 Mock 接口只作历史回归测试，不再是前端主链。详见 `docs/QWEN_RESEARCH_AGENT.md`。

评价体系已增设 **统一评价体系 v2**：在冻结 SDTI 外层新增外部 Benchmark、模型/系统变体横向对比、Quality Gate 消融、Task-Adaptive Fitness 和分层对比。详见 `docs/UNIFIED_EVALUATION_SYSTEM_V2.md`、`configs/evaluation_system_v2.yaml` 与 `data/evaluation_templates/unified_results_template.csv`。这些扩展不生成虚假成绩；所有数值必须来自真实运行产物和可追溯来源。

当前进一步升级已完成 **Research Planning Phase 1 / Literature Layer Phase 2**：允许输入宽泛研究方向，通过可替换 Literature Provider 形成带论文 Evidence 的候选科研问题与 Research Contract，并兼容现有 `ResearchBriefBuilder`。详见 `docs/RESEARCH_PLANNING_PHASE1.md`。

系统现已进入并完成总方案 **Phase 3 Planning RAG / Scientific KG MVP**：Europe PMC 开放全文结构化切片，可替换 ChromaDB + BGE 后端，默认可离线回归，支持语义/词法/章节/图谱混合检索、字段级 Evidence 查询、科研知识图谱和冻结 Gold Set RAG 评测。详见 `docs/PLANNING_RAG_PHASE3.md`。

根据《Scientific Data Agent 终局完整设计包》，当前进一步完成 **Phase 4 Source Broker MVP**：将 Source、Dataset、Resource 分层，以 Research Contract 生成 DatasetCandidate、Field Coverage Matrix、最小来源组合、JoinPolicy 和 fallback。所有 seed capability 都标记为采集前待验证，多 cohort 无 crosswalk 时明确禁止患者级横向 Join。详见 `docs/SOURCE_BROKER_PHASE4.md`。

前端现已升级为 **Guided Research Planning Workspace**：默认首页从宽泛 Topic 出发，依次展示真实论文 Evidence、候选科研问题、Research Blueprint 和 Source Plan；原完整数据工作台保留为“高级数据工作台”。详见 `docs/FRONTEND_PLANNING_WORKSPACE.md`。

模型评价、架构选择和答辩说明见 `docs/MODEL_EVALUATION_AND_SELECTION_REPORT.md`。该报告明确区分任务级诊断、AI Judge 探针、冻结 Gold Set 正式指标和未完成的横向模型实验，不使用代理分数冒充正式 SDTI。

VNext 检索实测汇总见 `evaluation/vnext_retrieval_calibrated_macro_20260828.md`：BGE-small-en-v1.5 五组 nDCG@10 宏平均 `0.3880`，校准融合 `0.3791`，均高于 tuned BM25 `0.3147`；融合权重只用 train/dev 选择，以上仅为 BEIR 检索层指标，不是临床效果或 SDTI。
Phase C Research Planning V2 已完成：`POST /api/v2/research/plan` 返回结构化 PICO/PECO 抽取、Evidence Pack、候选问题、变量角色/理由/证据/可用性、研究设计与未决问题；无论文 Evidence 时明确标记 `GENERIC_FALLBACK`，不作为正式科研事实。Phase D Schema Matcher V3 已接入独立模块、`/api/v2/schema/match` 和 Valentine 评测入口，十任务宏平均 F1 `0.7994`，低于现有 V2 `0.8451`，因此保持 V2 为默认。Phase E Entity Matcher V3 已接入 `/api/v2/entity/match`，经 train/valid 阈值校准后五个 DeepMatcher 任务宏平均 F1 `0.5579`、Recall `0.6229`，虽较固定阈值提升但仍低于 V2 F1 `0.7408`，因此保持 V2 为默认。详见 `docs/RESEARCH_AGENT_V2_PHASE_C.md`、`docs/SCHEMA_MATCHER_V3_PHASE_D.md`、`docs/ENTITY_MATCHER_V3_PHASE_E.md`。

Phase F Quality V2 已接入：`/api/v2/quality/detect`、`/api/v2/quality/candidates`、`/api/v2/quality/review` 将错误检测、修复候选、安全应用和 Research Readiness 分离；只自动执行低风险确定性候选，高风险医学字段、身份、response 与关键 provenance 保留审核或阻断。就绪度采用六项 Hard Gates 与可解释 Soft Indicators，正式 Detection F1/Repair Accuracy 等待冻结乳腺癌 Error Gold Set，不报告虚假成绩。详见 `docs/QUALITY_V2_PHASE_F.md`。

端到端对照矩阵与乳腺癌 Gold Set 工作区已建立：`scripts/run_variant_matrix.py` 会冻结 Rule/Qwen/Single-source/Multi-source/Full Agent 的共同控制条件，但在真实模型、冻结 Evaluation Contract 和人工 Gold Set 就绪前保持 `NOT_EVALUATED`。Gold Set 工作区见 `goldset/breast_cancer/README.md`。

VNext 升级已完成 **Phase A 治理底座** 并建立 **Phase B 统一检索协议**：Agent/算法只生成 proposal，独立 Safety Layer 依据证据、医学语义、身份与来源规则输出 `AUTO/REVIEW/REJECT`；检索统一返回 BM25/dense/fusion/rerank 分数、延迟、调用率与审计哈希。当前默认主检索为 BM25，Hashing 仅显式 fallback；真实 embedding/reranker 和五组 BEIR 重跑仍属 Phase B 后续验收。详见 `docs/VNEXT_PHASE_A_B.md`。

当前已补充 **Closed-Loop Iteration V2**：`POST /api/v2/agent/closed-loop` 会保存第一轮完整结果，诊断字段/结局/证据链缺口，安全地生成第二轮检索输入，并返回前后轮 coverage、target match、traceability、review burden 与 progress score 对比；支持 `GET /api/v2/agent/closed-loop/{loop_id}` 查询审计结果。前端研究任务入口已同步提供“启用闭环自我修正”开关、轮次诊断与指标对比展示，并更新脚本缓存版本。闭环最多 4 轮，质量门通过、重复输入或无可验证改进时停止。该 progress score 仅用于任务内反馈，不冒充正式 benchmark 或 SDTI。详见 `docs/CLOSED_LOOP_ITERATION.md`。

闭环默认执行 **两轮研究**：第一轮通过质量门也会生成“补充验证/完整性复核”请求，第二轮严格基于第一轮输出、诊断和已尝试来源重新检索；两轮之后才允许按无改进或质量门规则停止。可通过 `require_two_rounds=false` 保留兼容的提前停止行为，前端默认显式发送 `require_two_rounds=true`。

查询理解层与 A-E 消融已接入公开 BEIR 评测：规则归一化、保护词/漂移校验、原始回退和 `k=60` RRF 均可审计；无外部 Qwen 结构化计划缓存时 C/D/E 明确为 `NOT_EVALUATED`。当前结果仅为检索层诊断，生产默认保持 `compat`。详见 `docs/QUERY_UNDERSTANDING_ABLATION.md`。
