# 从这里开始

你正在查看「肿瘤精准治疗科研数据智能整合系统」：乳腺癌是当前专项验证癌种，系统同时支持 17 个其他常见癌种，并为未配置癌种保留通用发现入口。系统把自然语言科研问题转成可分析、可追溯的公开科研数据，不生成诊疗建议。

赛道能力主链：**千问问题解析与检索规划 + 真实 Adapter 取数 + 字段治理与错误诊断 + 冻结规则安全裁决 + 两轮闭环**。

## 推荐阅读顺序

1. `AGENTS.md`
2. `docs/FINAL_DELIVERY_INDEX_20260830.md`
3. `docs/乳腺癌精准治疗科研数据智能体_专业叙事与规范图示终稿_20260831.md`
4. `deliverables/乳腺癌精准治疗科研数据智能体_最新评委阅读包_20260902/README_START_HERE.md`
5. 需要修改 Schema 或医学规则时，再阅读 `docs/04_Canonical_Schema.md`、`docs/05_医学安全规则.md`

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

## 核心对照结果

| 能力 | 本项目 | 对照方法 | 差值 |
|---|---:|---:|---:|
| 问题解析 | **0.5522** | 项目词典 0.4662 | **+0.0860** |
| 科学检索 | **0.3920** | BGE 单路 0.3880 | **+0.0040** |
| 字段匹配 | **0.9018** | 项目原方法 0.7994 | **+0.1024** |
| 实体匹配 | **0.7449** | RecordLinkage 0.7440 | **+0.0009** |
| 数据清洗 | **0.9169**（六项） | Raha 0.8159（共同五项） | **+0.0870** |
| 完整乳腺癌链路 | **SDTI 98.1118** | 确定性链路 99.45 | 独立口径 |

公开结果分别对应不同能力和公开数据集，不相加为一个总准确率。检索的多方法、多指标统一表见 `evaluation/PUBLIC_RETRIEVAL_MATRIX_20260903.md`，新增 TREC-COVID 医学文献测试的真实结果也已纳入。当前最佳运行产物位于 `goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-current-deterministic-baseline-20260902/`。

## 医学安全边界

- HER2 IHC 2+ 不得直接判为 Positive；ERBB2 CNA ≠ HER2 IHC positive。
- 不得把细胞系 AUC/IC50 解释为患者 pCR。
- 低置信度患者/样本匹配不得自动合并。
- 高权威来源冲突时保留独立证据并进入复核。
- 关键字段缺少 Evidence 时不自动发布。
