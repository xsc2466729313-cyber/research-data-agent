# Production Mainline

更新时间：2026-08-29  
依据：赛道二方向 1A。本文只标明当前默认主链，不把未完成写成已完成，不把 development 分册分数写成正式 SDTI。

## 一句话

Qwen 负责推理与规划，工具负责取数，算法负责匹配与来源组合，规则负责守门，Evidence 负责证明，Gold Set 负责评测。

## 生产主链

```text
Requirement Agent（多视角 + 文献 Evidence）
        ↓
用户选择候选 → Frozen Research Contract
        ↓
Discovery（Source Registry + Coverage + Weighted Set Cover）
        ↓
Parsing Layer（API / CSV / Excel / HTML / PDF）
        ↓
Schema Matcher V2 + Entity Matcher V2 + SafetyLayer
        ↓
Quality V2
        ↓
Critic → Reflexion / 任务内 goal_loop + 两轮闭环
        ↓
导出 CSV / Excel / Parquet
```

| 能力 | 生产默认 | 仅评测 / 消融 | Legacy（保留可运行） |
|---|---|---|---|
| 规划 API | `/api/v3/research/*` + 现有 `/api/research/*` | `/api/v2/research/plan` | 固定三题模板仅作 `GENERIC_FALLBACK` |
| 检索 | BM25 + BGE + RRF + Reranker（`hybrid_rerank`）；BGE 不可用时显式 hashing fallback | 单路 BM25 / semantic | hashing 不得标成语义检索 |
| Schema | Matcher V2 | Matcher V3 | — |
| Entity | Matcher V2 + Safety Gate | Matcher V3 | — |
| Quality | Quality V2 | — | 阶段 09 Repair 闭环 |
| 闭环 | Critic + 任务内多轮 goal_loop 补搜 + 两轮 closed-loop | — | 固定 GSE/METABRIC 策略仅 fallback |
| 数据 Adapter | GDC / GEO / cBioPortal / AACT / CIViC / DepMap / 论文表图注 | — | `/api/tasks/mock` |
| 正式指标观察 | 历史基线 **63.36**；严格 Qwen LIVE 候选 **91.75**，两者均 `publish_allowed=false` 且不是 `frozen_test` | BEIR / Valentine / DeepMatcher；development 千问 LIVE **66.94（非正式）** | — |

## 正式评测路径

- 考卷入口：`goldset/templates/`（来自 `goldset/breast_cancer/official_candidate/`，审核人 xsc，2026-08-29）
- 行数：retrieval 50 / field 26 / error 18；`gold_set_id=breast-cancer-official-candidate-20260829`
- 采集与评分：`POST /api/evaluation/official-run`，或 `python goldset/breast_cancer/official_candidate/collect_official_sdti.py`；默认千问 + LIVE Adapter 且禁止静默兜底，模型名与本次真实来源校验写入评测审计
- 最新产物：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/`（`metrics.json` / `report.md` / `AUDIT.json`）
- 允许 `allow_reviewed_unfrozen=True` 是因为 manifest 仍 `frozen=false`；这是正式卷实测，不是 sealed `frozen_test`
- **禁止**把 `goldset/breast_cancer/development/` 的 66.94 填进正式栏

**分层指标与对照表（真实数字）见 [DATA_REPORT_20260829.md](DATA_REPORT_20260829.md)**：质量门 / 能力层 / 评测层分开；正式 vs 非正式一张总表；BM25 vs BGE 五数据集 nDCG；任务观察 848 行 REVIEW。不要只读本节口径。

短版对照：

| 层 | 大数字 | 口径 |
|---|---|---|
| 检索能力 | BGE nDCG@10 0.3880 vs BM25 0.3147（3,677 查询） | BEIR，不是正式 Retrieval F1 |
| 历史基线 SDTI | **63.36**，publish_allowed=false | 未调用 Qwen |
| 严格 Qwen LIVE 候选 | **91.75**，publish_allowed=false | 11/11 Qwen；5 个任务 REVIEW；不是 frozen_test |
| 非正式 SDTI | 66.94 | development 千问 LIVE，禁止进正式栏 |
| 质量门 | 任务上常见 REVIEW；正式安全门 FAIL | 缺 pCR/HER2 仍缺 |

## 闭环第二轮意图 vs 工作台旧结果

第二轮在诊断到「要 pCR/治疗响应、当前却是生存表」时，改搜 `GSE25066`、`GSE76360`、`GSE50948`，禁止用 OS/RFS 或细胞系 AUC/IC50 冒充患者 pCR。缺 HER2 临床状态时继续拉 GEO 特征或 cBioPortal HER2 字段；IHC 2+ 保持 Equivocal，不得写成 Positive。

**工作台上已经跑完的旧任务不会自动过门。** 补搜路径只作用于新的一轮执行；要过质量门必须重新跑协议，让新队列（例如 GSE25066）进入当前结果。缺字段、结局不匹配、质量门 REVIEW 在旧结果上仍然成立。

## 冻结接口（不得擅自改公式）

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `docs/06_评测指标与SDTI.md`

## 前端主路径

规划工作台先选候选、冻结 Research Contract，再生成 Source Plan 与数据集。高级工作台默认开启千问规划、任务内迭代补搜与两轮闭环：解析问题 → 选工具取数 → 诊断缺口 → 换队列/补 DepMap/NCT/论文抽取 → 再评 readiness。单元格可打开 Evidence Drawer；质量门 REVIEW 进入人工审核队列。

正式 SDTI 入口是 `goldset/templates/`。严格 Qwen LIVE 观察产物为 `official-candidate-qwen-live-audited-final-20260830`（91.75）；运行时来源校验 186/186 通过，但 5 个任务质量门 REVIEW 且卷面未 sealed，不得自动发布。`goldset/breast_cancer/development/` 的 66.94 仅作非正式对照。
