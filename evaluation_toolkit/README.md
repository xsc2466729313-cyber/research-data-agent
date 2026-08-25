# 科研数据 Agent 统一评测方案工具包

适用项目：赛道二·数据场景·方向 1A「科学数据查找、解析与整合」

本工具包的核心思想不是“只在自己的乳腺癌案例上给自己打分”，而是采用两级验证：

1. **外部标准 Benchmark**：用别人已经标好 Ground Truth 的数据，验证数据清洗、检索、字段对齐/实体匹配三项通用能力，便于和已有方法做横向比较。
2. **真实科研任务验证**：在自己的科研场景中，用 Quality Gate、反馈闭环和 Task-Adaptive Fitness-for-Purpose 评价，证明这些能力被正确地用于真实科研数据生产。

推荐最终论文/PPT主结构：

> 外部 Benchmark 证明“能力强” → 真实任务证明“落地对” → Quality Gate 证明“风险受控” → Adaptive Fitness 证明“适合当前科研目的”

## 建议优先跑的最小实验集

### 1. 数据清洗
- 数据集：Hospital、Flights、Beers（优先3个，时间够再加 Rayyan、Movies）
- 主指标：Cell-level Precision / Recall / F1
- Baseline：Raha+Baran、HoloClean、Cocoon（可选 LAED）
- 自己：Qwen-only Cleaning、Full Agent Cleaning

### 2. 科学数据检索
- 数据集：BEIR SciFact（主）、NFCorpus（生医补充）
- 主指标：nDCG@10
- 辅助：Recall@100、MRR@10、Latency
- Baseline：BM25、Contriever-MS MARCO、BGE-M3
- 自己：Qwen-only Retrieval、Full Agent Retrieval

### 3. 多源异构整合
分成两个可外部对比的子任务：
- Schema Matching F1：Valentine Benchmark；Baseline = Jaccard、COMA、Cupid
- Entity Matching F1：DeepMatcher ER-Magellan；Baseline = DeepMatcher、Ditto
- 内部展示可报告 Integration Macro-F1 = (Schema F1 + Entity F1)/2，但必须注明这是项目内部汇总值，不是行业标准指标。

### 4. 科研适用性
- 不使用固定公共分数硬套所有科研问题。
- 采用 Task-Adaptive Fitness-for-Purpose：
  Research Question → Evaluation Contract → Freeze → Data Search/Integration → Fitness Evaluation
- 一级维度固定：Research Relevance、Analytical Adequacy、Traceability/Reliability、Reusability
- 二级条件由 Agent 根据科研任务自动匹配。
- 横向对比：Rule Baseline、Qwen-only、Single-source Agent、Multi-source No-Gate、Full Agent。
- 所有系统在同一任务上使用同一份冻结 Evaluation Contract。

### 5. Quality Gate
输出不是一个虚构总分，而是 PASS / REVIEW / REJECT。
建议硬门：
- 来源真实性可验证
- 关键字段来源可追溯
- 无未解决关键冲突
- Schema/实体关联符合规则
- 关键科学事实有证据
- 任务级必要分析条件满足，否则 REVIEW/REJECT

通过消融实验证明 Quality Gate 的价值，而不是口头说“提高质量”。

## 多 AI 评价机制的正确定位

多 AI 只用于**需要人工语义判断、程序无法确定的评价项**，例如：
- 一个自然语言结局字段是否真正等价于目标 outcome
- 某个来源是否满足任务中的语义相关等级
- 某条 Evidence 是否足以支持结构化科学事实
- Task-Adaptive rubric 中无法由统计规则直接判断的条目

流程：
Judge A 独立评分 → Judge B 独立评分 → 差距过大触发 Judge C 仲裁 → 仍不确定则人工。
必须准备少量人工校准集（建议 30–50 条），报告 Weighted Cohen's κ / agreement / human-review rate。

## 目录
- `docs/01_完整评价方案.md`：可直接融合进技术报告
- `docs/02_Benchmark与Baseline链接.md`：模型、数据集、论文/代码链接
- `docs/03_对比实验与消融设计.md`
- `docs/04_可视化设计.md`
- `docs/05_多AI评价与人工校准协议.md`
- `configs/evaluation.yaml`：统一实验配置模板
- `scripts/download_all.ps1`：Windows 下载/克隆入口
- `scripts/metrics_template.py`：指标计算模板
- `scripts/plot_templates.py`：结果可视化模板
- `templates/results_template.csv`：统一结果表
