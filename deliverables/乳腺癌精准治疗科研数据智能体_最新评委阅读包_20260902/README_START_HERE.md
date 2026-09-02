# 从这里开始

你正在实现「肿瘤精准治疗科研数据智能整合系统」：乳腺癌是当前专项验证癌种，同时已配置 17 个其他常见癌种，并为未配置癌种保留通用发现入口；系统把自然语言科研问题变成可分析、可追溯的公开科研数据，而不是生成诊疗建议。多癌种边界见 `docs/MULTI_CANCER_SCOPE.md`。

赛道能力主链：**千问规划 + 真实 Adapter 取数 + 任务内按缺口迭代补搜 + 两轮闭环对照**。确定性规划只在模型失败且用户允许兜底时使用。

## 第一次进入仓库请按顺序读

1. `AGENTS.md`（硬约束）
2. `docs/CURRENT_MAINLINE.md`（当前生产主链）
3. `docs/DATA_REPORT_20260829.md`（分层总览 + 正式/非正式对照表 + BM25 vs BGE 真数）
4. `goldset/README.md`（正式考卷 vs development 练习册）
5. 需要改评测时再读 `docs/06_评测指标与SDTI.md`、`docs/EVALUATION_SDTI.md`
6. 需要改 Schema / 医学规则时再读 `docs/04_Canonical_Schema.md`、`docs/05_医学安全规则.md`（**不得擅自改冻结文件**）

完整 00–08 需求文档仍在 `docs/`，但不要把历史阶段报告当成当前主链。

2026-08-30 最终交付的统一入口见 `docs/FINAL_DELIVERY_INDEX_20260830.md`，其中汇总框架说明、系统设计、结果、指标检测、系统图、流程图与截图。Word 报告不在 GitHub 交付范围内。

## 怎么启动前后端

FastAPI 同时托管前端。本地：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 <http://127.0.0.1:8000/>。Docker 见根目录 `README.md`。

千问凭据只在用户端会话或本机环境变量中配置，**不要写入仓库、README 或提交 `.env`。**

## 正式考卷 vs development 练习册

| | 正式入口 | 练习册 |
|---|---|---|
| 目录 | `goldset/templates/` | `goldset/breast_cancer/development/` |
| 来源 | held-out `official_candidate`，审核人 **xsc** | 已用于改检索/DepMap/闭环，系统见过题面 |
| 历史基线 SDTI | **63.36**（`official-candidate-20260829T132222Z`） | 未调用 Qwen |
| 严格 Qwen LIVE 候选观察 | **97.53**（`official-candidate-qwen-live-recall-v9-20260902`） | 11/11 Qwen，召回率 83.33%，非 sealed |
| `frozen_test` | 否 | 否 |
| 发布 | `publish_allowed=false` | 禁止当正式成绩 |

同一套 development 题再当正式 Gold Set = 用练习册当期末考。正式栏只允许 official_candidate / templates 的观察分。

重跑正式评测：`POST /api/evaluation/official-run`，或

```powershell
python goldset\breast_cancer\official_candidate\collect_official_sdti.py
```

该入口默认执行 **千问 + LIVE Adapter**，且禁止静默降级到确定性规划；缺少凭据或任一题调用失败时整次正式运行失败。`metrics.json` 与 `AUDIT.json` 会记录模型供应商、实际模型名、千问调用题数、兜底次数和本次 Adapter 来源校验结果，但绝不记录 API Key。`--retrieval planner --no-use-qwen` 仅用于消融诊断，不得标成正式模型成绩。

## 已知缺口（不要写成已完成）

- 当前研究任务上 **pCR / HER2 等仍可能缺**，结局可能与问题不同域，质量门经常是 **REVIEW**，不能自动发布。
- 闭环第二轮意图已接线：缺 pCR 时改搜 GSE25066 等；**工作台上的旧任务结果不会自动变**，必须重新跑协议。
- 历史基线 SDTI 63.36；严格 Qwen LIVE 候选观察 97.53，但 8 个任务质量门 REVIEW 且卷面未 sealed，仍不得自动发布。

## 禁止事项

- 不得伪造数据源、DOI、PMID、GSE、NCT 或评测成绩。
- 不得把 development 66.94 写成正式分；正式分是 63.36 就写 63.36。
- 不得自行修改 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`docs/06_评测指标与SDTI.md` 公式。
- HER2 IHC 2+ 不得直接判为 Positive；ERBB2 CNA ≠ HER2 IHC positive。
- 不得把细胞系 AUC/IC50 解释为患者 pCR。
- 低置信度患者/样本匹配不得自动合并。
- Gold Set 不能仅凭一个 AI 模型输出直接作为真值。

## 当前阶段（诚实口径）

`prompts/00`–`10` 骨架已落地。生产主链是千问规划 + 函数调用取数 + goal_loop / Critic 补搜 + 两轮闭环。Adapter 含 GDC、GEO、cBioPortal、AACT、CIViC、DepMap 与论文表/图注抽取。

正式 Gold Set 已由 xsc 写入 templates；历史基线 63.36，严格 Qwen LIVE 候选观察 97.53，均因卷面 `frozen=false` 禁止作为冻结成绩发布。development 分册仅作非正式观察。

阶段报告、BEIR / Schema / Entity 公开基准、Planning RAG、Source Broker 等扩展文档仍在 `docs/`，那些是能力层诊断，**不是**乳腺癌正式 SDTI，也不是「缺字段已经补齐」的证明。
