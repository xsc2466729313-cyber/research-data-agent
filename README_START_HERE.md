# 从这里开始

你正在查看「肿瘤精准治疗科研数据智能整合系统」：系统面向多癌种精准治疗科研数据的查找、解析、整合与核验，乳腺癌是当前专项验证场景，同时配置了 17 个其他常见癌种，并为未配置癌种保留通用发现入口。系统把自然语言科研问题转成可分析、可追溯的公开科研数据，不生成诊疗建议。

赛道能力主链：**千问问题解析与检索规划 + 真实 Adapter 取数 + 字段治理与错误诊断 + 冻结规则安全裁决 + 两轮闭环**。

在线演示：[https://cancer-precision-data-agent.onrender.com/](https://cancer-precision-data-agent.onrender.com/)

Agent 架构说明见 [`docs/AGENT_ARCHITECTURE.md`](docs/AGENT_ARCHITECTURE.md)，系统属于有边界的混合式多 Agent 编排：有主 Agent 和职责隔离的规划、采集、批评、质量与闭环角色，同时保留确定性事实处理和医学规则门。

## 推荐阅读顺序

1. `AGENTS.md`
2. `docs/FINAL_DELIVERY_INDEX.md`
3. `docs/PROJECT_REPORT.md`
4. `docs/REVIEWER_STORY.md`（汇报讲稿：问题—设计—指标—能力—价值）
5. `deliverables/cancer-precision-data-agent-v2.0.0-reading-pack.zip`
6. 需要修改 Schema 或医学规则时，再阅读 `docs/04_Canonical_Schema.md`、`docs/05_医学安全规则.md`

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

## 首次使用千问

首次点击“开始完整规划”前，网页会要求先连接千问 API。点击提示框中的“去配置 API”，填写百炼 API Key 并测试连接后即可运行；默认使用 `Qwen3.8-Max`（`qwen3.8-max`）。网页填写的凭据仅在当前后端进程的临时内存中保存，最长两小时，不会写入项目文件。

## 核心对照结果

| 能力 | 本项目 | 对照方法 | 差值 |
|---|---:|---:|---:|
| 问题解析 | **0.5522** | 项目词典 0.4662 | **+0.0860** |
| 科学检索 | **0.3915** | BGE 单路 0.3880 | **+0.0035** |
| 字段匹配 | **0.9018** | 项目原方法 0.7994 | **+0.1024** |
| 实体匹配 | **0.7449** | RecordLinkage 0.7440 | **+0.0009** |
| 数据清洗 | **0.9169**（六项） | Raha 0.8159（共同五项） | **+0.0870** |
| 乳腺癌专项完整链路（候选卷观察） | **SDTI 98.1118** | 确定性消融 100.00 | 均 `publish_allowed=false`，不是封存正式成绩 |

公开结果分别对应不同能力和公开数据集，不相加为一个总准确率。检索的多方法、多指标统一表见 `evaluation/PUBLIC_RETRIEVAL_MATRIX_20260903.md`，新增 TREC-COVID 医学文献测试的真实结果也已纳入。当前最佳运行产物位于 `goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-current-deterministic-baseline-20260902/`。

## 医学安全边界

- HER2 IHC 2+ 不得直接判为 Positive；ERBB2 CNA ≠ HER2 IHC positive。
- 不得把细胞系 AUC/IC50 解释为患者 pCR。
- 低置信度患者/样本匹配不得自动合并。
- 高权威来源冲突时保留独立证据并进入复核。
- 关键字段缺少 Evidence 时不自动发布。
