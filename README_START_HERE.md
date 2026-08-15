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
