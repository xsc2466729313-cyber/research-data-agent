# Phase 0 基线报告

- 阶段：V3.1 Phase 0 — 工程保护与基线建立
- 日期：2026-09-05
- 结论：本阶段只新增基线文档，未开发 V3.1 业务能力，未进入 Phase 1

---

## 1. 当前 git commit

| 项 | 值 |
|---|---|
| HEAD | `8e023e1ee2b37abf0f9b114ddf53661444d97f7c` |
| 提交说明 | `release: prepare v2.0.0 package` |
| 作者 | xsc2466729313-cyber |
| 提交时间 | 2026-09-04T14:10:16+08:00 |
| 分支 | `main` |

工作区在该提交之上已有**先于本阶段存在**的未提交改动（前端、文献规划、README、部分测试等）。这些文件不是 Phase 0 产生的。Phase 0 没有改它们。

本阶段新增（未跟踪文档）：

- `../v31_baseline/API_SNAPSHOT.md`
- `../v31_baseline/REGRESSION.md`
- `../v31_baseline/OUTPUT_CONTRACT.md`
- `PHASE0_REPORT.md`

---

## 2. 当前项目版本

| 来源 | 版本 |
|---|---|
| FastAPI `app.version`（`backend/app/main.py`） | `2.2.0-qwen-agent` |
| FastAPI title | 科研数据智能体 (Research Data Agent) |
| `/health` 声明 mode | `qwen-agent+function-calling+live-adapters+research-dataset+traceability+quality-gate+v3-mainline` |
| HEAD 提交信息 | v2.0.0 发布包准备 |
| `RELEASE_NOTES.md` 顶部 | v2.2.0（2026-09-05） |

基线以**当前工作区可读代码**为准：运行时版本字段是 `2.2.0-qwen-agent`。历史阅读包与 Gold Set 观察成绩仍按原口径，不在本阶段改写。

---

## 3. 当前目录结构摘要

```text
仓库根
  backend/app/          运行时后端
  backend/tests/        现有自动测试（约 92 个文件）
  frontend/             规划工作台 + 高级工作台
  configs/              冻结 schema / 医学规则 / 质量与来源配置
  docs/                 架构与交付文档
  ../v31_baseline/    本阶段新增的升级基线
  goldset/              乳腺癌 Gold Set 与模板
  evaluation/           公开基准产物
  scripts/              评测与打包脚本
  schemas/              JSON schema
  prompts/              历史提示词
```

`backend/app` 主要子目录：`agent`、`sources`、`research_planning`、`research_planning_v2`、`requirement_agent`、`integration`、`normalization`、`quality_v2`、`critic`、`evidence`、`parsers`、`literature`、`retrieval`、`rag`、`source_broker`、`evaluation`、`goldset`、`repair`、`rules`、`governance`、`contracts`。

`backend/app/sources`：`gdc`、`geo`、`cbioportal`、`aact`、`civic`、`depmap`、`discovery`。

本阶段**没有**创建 `backend/app/v30/`。

---

## 4. 当前核心模块列表

### 可信数据内核（只读保护）

- `ResearchAgentService`：肿瘤科研任务执行
- 官方 Adapter：GDC / GEO / cBioPortal / AACT / CIViC / DepMap / Discovery
- `ParserRegistry`：CSV / Excel / HTML / JATS / PDF 文本层
- `canonical_schema.yaml` + `CanonicalRecord`
- SchemaMatcher / EntityMatcher / `PatientSampleLinker`
- `EvidenceBuilder`
- `medical_rules.yaml` + Quality Gate / Quality V2 / Critic
- `ClosedLoopService`
- Gold Set 加载与 SDTI 公式文档

### 现有规划层（保留直连）

- `ResearchPlanningService` / `ResearchPlanningV2Service`
- `RequirementAgentService`
- `SourceBroker`

### 前端

- 规划工作台：主题 → 文献 → 问题 → 合同 → 来源
- 高级工作台：运行协议、质量门、分析矩阵、溯源、导出

---

## 5. 当前医学主流程

```text
用户输入科研问题
        ↓
Research Planning
  Topic → 文献扫描 → 候选问题 → Research Contract → Source Plan
  兼容入口：/api/research/* 与 /api/v3/research/*
        ↓
ResearchAgentService
  解析 ResearchSpec → 选工具 → 受控执行
  入口：/api/agent/tasks
        ↓
Adapter
  官方 API / 文件下载，登记 source_id
        ↓
Schema / 数据集构造
  DatasetBuilder + Matcher + 冻结 Canonical 字段
        ↓
Evidence
  raw_field / raw_value / source_id 绑定到标准值
        ↓
Quality Gate
  来源 / 字段 / 身份 / 适用性
  PASS / REVIEW / REJECT（或 FAIL）
  publish_allowed 仅在 PASS 且有主表行时为真
        ↓
Export
  CSV / Parquet / Excel（含来源、字段字典、可科研性等 sheet）
```

本阶段没有改变这条链上的任何代码。

---

## 6. 当前测试结果

执行时间：2026-09-05  
命令：见 `../v31_baseline/REGRESSION.md` 的 Phase 0 固定回归集  
环境：`.venv` Python 3.11.3，pytest 8.3.5，`PYTHONPATH=.`  
范围：25 个测试文件（规划 / Agent / Adapter 单测 / Schema / Quality / Parser / Evaluation / Canonical 模型）

| 项 | 结果 |
|---|---|
| 收集用例 | 234 |
| 通过 | **234** |
| 失败 | **0** |
| 错误 | **0** |
| 跳过 | **0** |
| 耗时 | 12.09 秒 |
| 退出码 | 0 |

未在本阶段运行：

- 全部约 92 个测试文件的一次总跑
- 标记为 integration 的真实外网 Adapter 联通测试
- 需要千问密钥的 LIVE 评测
- `node --check frontend/app.js`

以上未跑项**没有**被填写为通过或失败。不能把 234 当成全仓库总成绩。

---

## 7. 当前冻结文件检查结果

对本阶段开始时与结束后均执行：

```text
git diff --name-only -- configs/canonical_schema.yaml configs/medical_rules.yaml
  ../../06_评测指标与SDTI.md docs/EVALUATION_SDTI.md goldset
  backend/app/sources backend/app/agent/service.py
  backend/app/agent/quality_gate.py backend/app/quality_v2
  backend/app/integration/schema_matcher_v2.py
  backend/app/integration/schema_matcher_v3.py
```

结果：**无输出**。这些路径相对 HEAD 没有 diff。

SHA-256（当前工作区文件，供后续对照）：

| 文件 | SHA-256 |
|---|---|
| `configs/canonical_schema.yaml` | `3014ED3CDFE710A9F77E73C1780B31A72ECA6FFAD42A6EAD7AF7760FCC6F4B70` |
| `configs/medical_rules.yaml` | `C607C503AFAA2C694A689F9B91F57308D028E5E30BB19D6FFB88A17FEDB6BCD3` |
| `../../06_评测指标与SDTI.md` | `D285926B0D80384F6145B9EBA54FD5D9C6609C8A69F2302440671D5B685D592D` |
| `docs/EVALUATION_SDTI.md` | `0DBE526FB37261347DF713EBE1146CFBDB71A4AA70A7EFA0EF69A3C68FB5617B` |

`canonical_schema.yaml` 仍为 `version: "0.1"` 且 `frozen: true`。  
`medical_rules.yaml` 仍含 HER2 IHC 2+、ERBB2 CNA、低置信度身份、缺 Evidence、跨域 response 等硬规则。

---

## 8. Phase 0 自身约束核对

| 禁止项 | 本阶段是否触碰 |
|---|---|
| 开发 V3.1 新功能 | 否 |
| 进入 Phase 1 | 否 |
| 创建 Router / Copilot / Memory | 否 |
| 创建 `backend/app/v30/` | 否 |
| 修改冻结配置 / Adapter / Matcher / Quality / Agent 主流程 / Gold Set / SDTI | 否 |
| 修改现有 API 行为 | 否 |
| 修改或新写业务测试 | 否 |
| 伪造测试成绩 | 否 |

---

## 9. 是否满足进入 Phase 1 的条件

**工程保护条件：满足。**

已具备：

1. `../v31_baseline/` 三份基线文档
2. 医学固定回归 234 通过、0 失败
3. 冻结文件无 diff，哈希已记录
4. 输出契约已写明主表、追溯、质量门、导出
5. 无 v30 业务代码混入本阶段

进入 Phase 1 前建议（不是本阶段缺陷，但是工作区事实）：

- 工作区仍有与 Phase 0 无关的未提交改动。Phase 1 应只新增 `backend/app/v30/**` 与必要挂载，不要把那些改动和 Copilot 混在一个提交里。
- Phase 1 第一刀按 `IMPLEMENTATION_PLAN_V31.md` 第八部分：只做 Router + Copilot + 最小 Memory，不做 Planner，不改内核。

Phase 0 到此结束。不继续开发。
