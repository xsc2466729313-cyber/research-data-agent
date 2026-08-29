# 乳腺癌精准治疗科研数据智能体

面向「从科学问题到可用数据」的中文科研数据 Agent。输入研究方向或具体问题后，系统检索真实论文与开放数据，形成研究方案，调用公开数据库，做字段标准化、患者/样本关联、医学安全检查和缺口补搜，再导出可分析、可追溯的结果。

本项目对应赛道能力：**自主检索、任务内迭代闭环、千问规划 + 真实工具取数**。模型负责理解与规划，公开数据库提供事实，确定性规则负责医学安全和发布边界。**不提供临床诊疗建议。**

> 当前生产规划模型为 **Qwen3.8-Max**。未连接模型时可走确定性兜底，页面会标明。

## 快速入口

| 目标 | 入口 |
|---|---|
| GitHub 仓库 | https://github.com/xsc2466729313-cyber/breast-cancer-research-agent |
| 从这里开始 | [README_START_HERE.md](README_START_HERE.md) |
| 生产主链 | [docs/CURRENT_MAINLINE.md](docs/CURRENT_MAINLINE.md) |
| 数据报告（含正式分与缺口） | [docs/DATA_REPORT_20260829.md](docs/DATA_REPORT_20260829.md) |
| 正式 Gold Set | [goldset/templates/](goldset/templates/) |
| 冻结 SDTI 公式 | [docs/06_评测指标与SDTI.md](docs/06_评测指标与SDTI.md) |

## 系统交付什么

输入例如：

```text
研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系，
并整理患者级科研数据集。
```

系统会尝试输出：有论文 Evidence 的候选问题、Research Contract、公开库检索记录、保留 `source_id` / `raw_field` / `raw_value` 的分析矩阵、四层质量门、两轮闭环对照，以及 Excel / CSV / 质量报告。

**当前研究任务上，这些输出经常仍不完整。** 缺 pCR / HER2、结局与问题不同域、质量门 `REVIEW` 都是真实状态，不是已经修好。详见下方「已知缺口」和数据报告。

## 怎么启动

### 方式一：直接运行（推荐本地开发）

前置：Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 <http://127.0.0.1:8000/>。FastAPI 同时托管前端，不必再配前端端口。

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

### 方式二：Docker

前置：Git、Docker Desktop。

```powershell
git clone https://github.com/xsc2466729313-cyber/breast-cancer-research-agent.git
cd breast-cancer-research-agent
powershell -ExecutionPolicy Bypass -File .\scripts\docker_up.ps1
```

- 用户端：<http://localhost:8888>
- API：<http://localhost:8000/docs>

停止：`docker compose down`

### 连接千问

用户端右上角「连接千问 API」。凭据只保存在后端进程内存，最长约 2 小时；**不要把密钥写入仓库或 README**。未连接时可用确定性兜底。

## 正式考卷 vs development 练习册

| | 正式入口 | development 练习册 |
|---|---|---|
| 路径 | `goldset/templates/`（来自 `official_candidate/`） | `goldset/breast_cancer/development/` |
| ID | `breast-cancer-official-candidate-20260829` | `breast-cancer-development-20260829` |
| 行数 | retrieval 50 / field 26 / error 18 | retrieval 53 / field 35 / error 22 |
| 审核人 | xsc（2026-08-29） | xsc（2026-08-29） |
| `frozen_test` | **否**（`frozen=false`） | **否**（development 分册） |
| 本次实测 SDTI | **63.36**（评测 ID `official-candidate-20260829T132222Z`） | **66.94**（千问 LIVE，非正式） |
| 能否当正式成绩 | 可报「对本正式卷的实测」，**不是** sealed 赛题终考 | **禁止**填入正式栏 |

重跑正式评测：

```powershell
python goldset\breast_cancer\official_candidate\collect_official_sdti.py --retrieval planner
```

或工作台「开始正式评测」（`POST /api/evaluation/official-run`）。数字必须以 `metrics.json` 为准，禁止把 66.94 写成正式分。

## 已知缺口（还没提升的部分）

闭环第二轮**已经接上改搜路径**：缺 pCR / 治疗响应、或当前是生存队列时，会改搜 `GSE25066`、`GSE76360`、`GSE50948`，禁止用 METABRIC 生存表空转。缺 HER2 时继续拉临床/GEO 特征；IHC 2+ 不得写成 Positive。

但：

1. **工作台上已经跑完的旧任务不会自动过门。** 必须重新跑协议，新检索才会进当前结果。
2. 代表研究任务上仍常见：宽表有行（例如 METABRIC 848×46），治疗响应分析集为 0，结局不匹配，缺 HER2 / pCR，四层质量门总体 **REVIEW**，`publish_allowed=false`。
3. 正式卷实测 Retrieval F1 0.45、Faithfulness 0.65、Repair Accuracy 0.50，安全门 **FAIL**（Faithfulness < 90%，另有 5 个高风险问题未解决）。目标 SDTI 90 未达到。

不要把「代码里接了补搜」理解成「当前这张表已经补上」。缺的还是缺。

## 工作流

```mermaid
flowchart LR
  A[研究方向或科研问题] --> B[论文检索与问题细化]
  B --> C[Research Contract]
  C --> D[Source Broker]
  D --> E[GDC / GEO / cBioPortal / AACT / CIViC / DepMap]
  E --> F[标准化并保留原始值]
  F --> G[患者/样本关联]
  G --> H[医学安全与质量门]
  H --> I[分析矩阵与 Evidence]
  H --> J[缺口诊断]
  J -->|第二轮改搜 pCR 队列等| D
  I --> K[Excel / CSV / 质量报告]
```

第一轮保存完整输入、工具调用和结果。第二轮按字段/结局/Evidence 缺口生成补充请求。质量门通过、输入重复、没有可验证改进或达到轮次限制时停止。**执行了第二轮 ≠ 缺口已经补齐。**

## 医学安全边界

- HER2 IHC 2+ 不得直接自动判为 HER2 Positive
- ERBB2 CNA amplification 不等同 HER2 IHC positive
- 低置信度患者/样本关联进入 `unresolved/review`
- 高权威来源不可解释冲突不得自动选边
- 细胞系 `AUC/IC50` 与患者 `pCR/response` 必须用 `response_domain` 区分
- 无 Evidence 的关键字段不得进入正式发布集

冻结接口：`configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml`、`docs/06_评测指标与SDTI.md`（公式不得自行改）。

## 测试

```powershell
python -m pytest -q
node --check frontend\app.js
```

## 数据与 GitHub 边界

| 内容 | 是否提交 |
|---|---|
| 代码、配置、测试、文档、Gold Set CSV | 提交 |
| 脱敏评测报告与 `metrics.json` | 提交 |
| API Key、`.env`、凭据 CSV | **不提交** |
| `data/cache/`、大型 GEO/GDC/BEIR 下载 | **不提交** |
| `__pycache__` / `.pytest_cache` | **不提交** |

项目原则：有真实来源才写入；有 Gold Set 观察才报分；缺字段就写缺，不把未完成写成已完成。
