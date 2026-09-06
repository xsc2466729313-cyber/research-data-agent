# V3.1 Phase 0 正式基线报告

本文件是 V3.1 升级前的正式基线。它只记录当前系统真相，不增加产品能力，不授权进入业务开发。

配套文件：

- `API_SNAPSHOT.md`
- `OUTPUT_CONTRACT.md`
- `REGRESSION.md`

---

# 1. 基本信息

| 项 | 值 |
|---|---|
| 项目名称 | 科研数据智能体（research-data-agent） |
| 当前 git commit | `8e023e1ee2b37abf0f9b114ddf53661444d97f7c` |
| 提交说明 | `release: prepare v2.0.0 package` |
| 当前分支 | `main` |
| 当前版本号 | `2.2.0-qwen-agent`（`backend/app/main.py` FastAPI version） |
| 生成日期 | 2026-09-05 |

说明：HEAD 提交信息仍写 v2.0.0 发布包；当前工作区运行时版本字段为 `2.2.0-qwen-agent`。本基线以工作区可读代码的版本字段为准，不改写历史 Gold Set 或公开基准成绩。

---

# 2. 当前系统状态

当前系统是：

**科研数据智能体。**

它把自然语言科研问题转成可分析、可追溯、可审计、可下载的公开科研数据包。乳腺癌是专项验证场景；系统已配置多个常见癌种入口，但不提供诊疗建议。

## 当前核心能力

- 科研问题规划与 Research Contract
- 官方数据源 Adapter 取数
- Schema 对齐与 Canonical 字段映射
- 患者/样本身份隔离
- Evidence 绑定（`source_id` / `raw_field` / `raw_value`）
- Quality Gate 与医学安全规则
- 两轮闭环补搜
- CSV / Excel / Parquet 导出

## 当前主要工作流

```text
用户输入
    ↓
Research Planning
    ↓
ResearchAgentService
    ↓
Adapter
    ↓
Schema
    ↓
Evidence
    ↓
Quality Gate
    ↓
Export
```

升级前系统已经具备：

- 数据源 Adapter（GDC、GEO、cBioPortal、AACT、CIViC、DepMap、Discovery）
- Schema 对齐（冻结 Canonical Schema + Matcher）
- Evidence
- Quality Gate
- 医学规则（`medical_rules.yaml`）
- 导出能力（csv / parquet / xlsx 等）

本阶段没有改动上述能力。

---

# 3. 冻结资产检查

对本报告生成时再次核对：

```text
git diff --name-only -- configs/canonical_schema.yaml configs/medical_rules.yaml ../../06_评测指标与SDTI.md
```

结果：无输出。上述三个冻结文件相对 HEAD **没有修改**。

| 文件 | 相对 HEAD | SHA-256（工作区） |
|---|---|---|
| `configs/canonical_schema.yaml` | 无 diff | `3014ED3CDFE710A9F77E73C1780B31A72ECA6FFAD42A6EAD7AF7760FCC6F4B70` |
| `configs/medical_rules.yaml` | 无 diff | `C607C503AFAA2C694A689F9B91F57308D028E5E30BB19D6FFB88A17FEDB6BCD3` |
| `../../06_评测指标与SDTI.md` | 无 diff | `D285926B0D80384F6145B9EBA54FD5D9C6609C8A69F2302440671D5B685D592D` |

`canonical_schema.yaml` 仍为 `version: "0.1"` 且 `frozen: true`。  
`medical_rules.yaml` 仍包含 HER2 IHC 2+、ERBB2 CNA、低置信度身份关联、缺 Evidence、跨域 response 等硬规则。

以下核心模块在 Phase 0 **保持不变**（未改实现、未重构）：

- Adapter（`backend/app/sources/**` 无本阶段 diff）
- SchemaMatcher（核心算法文件无本阶段 diff）
- Quality Gate（`quality_gate.py` / `quality_v2` 无本阶段 diff）
- ResearchAgentService（`backend/app/agent/service.py` 无本阶段 diff）

工作区存在先于 Phase 0 的其他未提交改动（前端、文献规划等）。那些文件不是本报告新增的业务模块，也不构成本阶段对冻结内核的修改。

`backend/app/v30/` 不存在。未创建 Router、Research Copilot、Memory、Planner。

---

# 4. API 基线

完整清单见 `API_SNAPSHOT.md`。

当前冻结入口包括：

- `/api/agent/*`：任务执行、状态、导出、千问会话
- `/api/research/*`：主题、文献、合同、来源方案
- `/api/v3/*`：澄清、冻结合同、解析、Critic、审核
- `/api/adapters/*`：GDC / GEO / cBioPortal / AACT / CIViC
- `/api/v2/*`：Schema / Entity / Quality / 检索 / 规划 V2 / 闭环
- `/api/evaluation/*`：Gold Set 模板、评测运行、产物

当前代码中 **不存在** `/api/v30/*`。

后续 V3.1 只能新增：

```text
/api/v30/*
```

不得改写上列冻结入口的方法、路径或收窄现有行为。

---

# 5. 数据输出基线

完整契约见 `OUTPUT_CONTRACT.md`。

当前数据可信链：

```text
数据源
    ↓
Adapter / Parser
    ↓
Schema
    ↓
Evidence
    ↓
Quality
    ↓
Export
```

必须保留：

- `source_id`
- `raw_field`
- `raw_value`
- Evidence
- PASS / REVIEW / FAIL（及质量门并存的 REJECT / READY 枚举，见输出契约）

主表只能来自现有 Adapter / DatasetBuilder 可解析结果，不能由模型直接生成患者行。  
`publish_allowed` 不得被模型自评改写。  
导出入口 `GET /api/agent/tasks/{task_id}/export/{file_format}` 与 Excel 来源/可科研性 sheet 必须继续可用。

---

# 6. 测试基线

运行方式与文件清单见 `REGRESSION.md`。

| 项 | 记录 |
|---|---|
| Python 环境 | 仓库 `.venv`，Python 3.11.3 |
| pytest 环境 | pytest 8.3.5 |
| 工作目录 | 仓库根目录，`PYTHONPATH=.` |
| 固定测试集 | REGRESSION.md 中的 25 个文件（规划 / Agent / Adapter 单测 / Schema / Quality / Parser / Evaluation / 模型） |

## 实际运行结果

固定回归集 **已经执行**，填写真实结果：

| 项 | 结果 |
|---|---|
| 执行日期 | 2026-09-05 |
| 收集用例 | 234 |
| 通过 | 234 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 0 |
| 耗时 | 12.09 秒 |
| 退出码 | 0 |

未执行、因此不填写通过或失败：

- 全仓库约 92 个测试文件的一次总跑
- 需要外网的 integration 联通测试
- 需要千问密钥的 LIVE 评测
- `node --check frontend/app.js`

以上未跑项保持为：尚未执行，不伪造结果。  
234 不是全仓库总成绩，只是 Phase 0 固定医学回归集成绩。

---

# 7. Phase 0 验收结果

是否满足进入 Phase 1：**YES**

判断标准核对：

| 标准 | 状态 |
|---|---|
| 1. 基线文档完成 | 是（API_SNAPSHOT / OUTPUT_CONTRACT / REGRESSION / 本报告） |
| 2. 冻结文件无修改 | 是（三项冻结文件相对 HEAD 无 diff） |
| 3. API 快照完成 | 是 |
| 4. 输出契约完成 | 是 |
| 5. 回归测试状态明确 | 是（固定集 234 passed / 0 failed；其余未跑已标明） |

本阶段未开发 V3.1 功能，未进入 Phase 1 实现。

---

# 8. Phase 1 启动条件

Phase 0 已通过。下一阶段是：

**Phase 1：Research Copilot + Router + 最小 Session Memory**

按 `../2026-09-05/IMPLEMENTATION_PLAN_V31.md`，第一刀只做旁路对话闸门，不自动取数，不创建完整 Planner（Planner 门面可作为 Phase 1 第二刀）。

Phase 1 禁止修改：

- Adapter
- Schema（含 `configs/canonical_schema.yaml` 与 Matcher 核心算法）
- Quality（含 Quality Gate / Quality V2 / `medical_rules.yaml`）
- ResearchAgentService

Phase 1 只允许新增 `backend/app/v30/` 旁路与 `/api/v30/*`，并保持旧医学入口可直连。

工作区若仍有与升级无关的未提交改动，Phase 1 提交应与它们隔离，避免和 Copilot 混在一起。

---

Phase 0 正式基线到此结束。本文件只记录，不包含代码，不修改业务文件。
