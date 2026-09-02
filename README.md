# 乳腺癌精准治疗科研数据智能体

面向乳腺癌科研的数据整合 Agent：把自然语言研究问题转成可执行的研究方案，从公开数据库取数，完成字段标准化、患者/样本关联、医学安全检查和缺口驱动的两轮迭代，最终导出可分析、可追溯的数据与质量报告。乳腺癌是当前专项验证癌种，系统同时配置了 17 个其他常见癌种，并为未配置癌种保留通用发现入口。

> 模型负责理解、规划与反思；公开数据库提供事实；确定性规则负责医学安全和发布边界。本项目服务科研数据整理，不提供临床诊疗建议。

![科研规划工作台](docs/images/01-user-workflow.png)

## 当前能力

| 环节 | 已实现能力 | 交付结果 |
|---|---|---|
| 问题理解 | 从研究方向生成候选问题与 Research Contract | 人群、暴露、结局、字段和来源约束 |
| 真实取数 | GDC、GEO、cBioPortal、AACT、CIViC、DepMap 与论文表格/图注 | 带真实 `source_id` 的原始记录 |
| 数据整合 | Schema 匹配、实体关联、医学字段归一化 | 保留 `raw_field`、`raw_value` 的标准表 |
| 质量控制 | 来源、字段、实体、研究适用性四层质量门 | PASS / REVIEW / FAIL 与问题清单 |
| 自主闭环 | 根据缺字段、结局域错配和来源不足规划下一轮补搜 | 两轮指标快照、动作与输入/输出哈希 |
| 多癌种扩展 | 乳腺癌专项流程与 17 个其他常见癌种配置 | 按癌种加载研究上下文与安全边界 |
| 导出审计 | CSV、Excel、Evidence 与运行报告 | 可追溯科研数据包 |

## GitHub 同类项目实测

本项目与 GitHub 同类方法使用相同公开数据、相同划分和相同指标运行。下列数字是模块级能力对比，不能相加，也不是乳腺癌正式 SDTI。

![GitHub 同类项目四模块对比](docs/images/github-benchmark-summary.png)

| 功能 | 公共评测集 | **本项目** | GitHub 对照 | 结论 |
|---|---|---:|---:|---|
| 科学检索 | BEIR 5 个数据集 | **0.3818** | BGE 0.3880 | 接近，低 0.0062 |
| 字段匹配 | Valentine 10 个任务 | **0.7994** | COMA 0.7670 | 高 0.0324 |
| 实体匹配 | DeepMatcher 5 个任务 | **0.7449** | RecordLinkage 0.7440 | 高 0.0009 |
| 数据清洗 | 5 个共同实测任务 | **0.5726** | Raha 子集 0.8159 | 低 0.2433 |

实体匹配采用验证集选择的 V2/V3/AND 自适应策略；数据清洗融合格式归一化与高频 `x` 占位符一致性修复。完整逐数据集结果、未运行项目原因、方法差异与复现信息见 [GitHub 同类项目公开数据集实测报告](evaluation/github_competitor_benchmark_20260830/report.md)。机器可读证据在 [results.json](evaluation/github_competitor_benchmark_20260830/results.json)。

![BEIR 五个公开检索数据集分层结果](docs/images/github-retrieval-breakdown.png)

## 正式评测与运行观察

| 评测 | 当前结果 | 状态 | 正确读法 |
|---|---:|---|---|
| 历史正式卷基线观察 | **SDTI 63.36** | `publish_allowed=false` | 仍是历史基线，不是 sealed frozen test |
| 最终 Qwen hybrid 候选观察（2026-09-02） | **SDTI 98.11** | `publish_allowed=false` | 真实 Qwen + LIVE Adapter，卷面未 sealed |
| 当前确定性消融（2026-09-02） | **SDTI 100.00** | 诊断用 | 说明候选卷已被专门化规则饱和，不能证明通用能力 |
| development 练习册 | 66.94 | 非正式 | 已用于迭代，不能当正式成绩 |

最终 Qwen hybrid 运行的机器可读证据见 `goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-qwen-hybrid-final-20260902/`；检索 11 次、字段治理 26 次、错误诊断 18 次真实调用均成功，运行时来源校验 249/249 通过，但 9 个任务质量门为 REVIEW，且卷面未 sealed，因此仍不允许自动发布。正式公式和阈值见 [评测指标与 SDTI](docs/06_评测指标与SDTI.md)；公开模块对照与 Qwen 边界见 [公开对照题号与结果说明](docs/PUBLIC_COMPARISON_GUIDE_20260902.md)。

## 工作流程

```mermaid
flowchart LR
  A[科研问题] --> B[候选问题与研究契约]
  B --> C[来源规划]
  C --> D[GDC / GEO / cBioPortal / AACT / CIViC / DepMap]
  D --> E[标准化并保留原始值]
  E --> F[患者与样本关联]
  F --> G[四层质量门]
  G --> H[分析矩阵与 Evidence]
  G --> I[缺口诊断]
  I -->|补搜或换同域队列| C
  H --> J[CSV / Excel / 质量报告]
```

闭环不会为了“通过”而猜测缺失医学事实。需要患者 pCR 时，生存结局或细胞系 AUC/IC50 不能替代；第二轮只能寻找更匹配的数据源，仍缺失则保持 REVIEW。

## 快速启动

需要 Python 3.11+。首次启动：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 <http://127.0.0.1:8000/>。Docker 用户可运行 `./scripts/docker_up.ps1`，然后访问 <http://localhost:8888>。

千问凭据只在会话或本机环境变量中配置，不要提交 `.env` 或任何密钥。

## 报告导航

| 报告 | 用途 |
|---|---|
| [最终交付索引](docs/FINAL_DELIVERY_INDEX_20260830.md) | 四份最终报告、图表、截图与验收结果的统一入口 |
| [框架说明报告](docs/FINAL_FRAMEWORK_REPORT_20260830.md) | 五层框架、主链、模型/程序责任与数据治理边界 |
| [系统设计报告](docs/FINAL_SYSTEM_DESIGN_REPORT_20260830.md) | 模块设计、质量门、闭环、API、安全与复现设计 |
| [结果报告](docs/FINAL_RESULTS_REPORT_20260830.md) | 正式指标、真实任务、公开对比、已完成与短板 |
| [指标检测报告](docs/FINAL_METRICS_VALIDATION_REPORT_20260830.md) | 指标重算、口径隔离、安全门、测试与敏感信息检查 |
| [系统图与截图索引](docs/FINAL_VISUAL_ASSETS_20260830.md) | 架构图、流程图、当前页面和核心功能截图 |
| [GitHub 同类项目实测报告](evaluation/github_competitor_benchmark_20260830/report.md) | 同数据、同切分、同指标的外部方法对比 |
| [指标提升与两轮融合说明](docs/METRIC_IMPROVEMENT_REPORT_20260830.md) | 提升前后差值、融合策略与闭环取优规则 |
| [分层评测与消融报告](evaluation/agent_stratified_ablation_20260829/report.md) | development 分层、候选卷迭代、检索与规划消融 |
| [迭代交付说明](docs/ITERATION_REPORT_20260829.md) | 本轮自主闭环、持久化与质量能力变更 |
| [当前生产主链](docs/CURRENT_MAINLINE.md) | 生产默认、评测方法与 legacy 能力边界 |
| [数据与指标口径](docs/DATA_REPORT_20260829.md) | 正式/非正式指标及公开检索分层 |
| [多癌种范围](docs/MULTI_CANCER_SCOPE.md) | 乳腺癌专项、17 个已配置癌种与通用发现入口 |
| [公开对照题号与结果说明](docs/PUBLIC_COMPARISON_GUIDE_20260902.md) | 公开模块题、Qwen hybrid 和正式乳腺癌评价的边界 |
| [完整设计与评测](docs/FINAL_INTEGRATED_REPORT_20260829.md) | 架构、功能、接口与阶段评测总览 |

## 复现评测与图表

外部依赖准备完成后，可重跑 GitHub 同类项目评测：

```powershell
python scripts\run_github_competitor_benchmark.py --external-package-dir <外部评测依赖目录>
python scripts\build_github_report_charts.py
```

图表直接读取 `results.json`，不在绘图代码中填写成绩。完整逐方法指标、数据哈希和运行环境均保留在评测产物中。DeepMatcher、Ditto、HoloClean 未在当前环境完成公平复现的模型不填论文数字，统一标记 `NOT_EVALUATED`。

## 医学安全边界

- HER2 IHC 2+ 不得直接自动判为 HER2 Positive。
- ERBB2 CNA amplification 不等同 HER2 IHC positive。
- 低置信度患者/样本关联进入 `unresolved/review`。
- 高权威来源存在不可解释冲突时不得自动选边。
- 细胞系 `AUC/IC50` 与患者 `pCR/response` 必须用 `response_domain` 区分。
- 关键字段缺少 Evidence 时禁止自动发布。

## 验证

```powershell
python -m pytest -q
node --check frontend\app.js
```

验收时运行后端测试和前端语法检查；正式评测、来源审计和安全门结果以 [指标检测报告](docs/FINAL_METRICS_VALIDATION_REPORT_20260830.md) 及对应运行产物为准。

项目入口与硬约束见 [README_START_HERE.md](README_START_HERE.md) 和 [AGENTS.md](AGENTS.md)。
