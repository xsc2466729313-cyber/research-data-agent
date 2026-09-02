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

## 核心运行结果

| 评测 | 结果 |
|---|---:|
| 当前最佳综合结果（2026-09-02） | **SDTI 100.00** |
| 真实 Qwen 字段匹配（Valentine） | **Macro F1 0.9018** |

当前最佳运行产物位于 `goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-current-deterministic-baseline-20260902/`。

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
| [最终交付索引](docs/FINAL_DELIVERY_INDEX_20260830.md) | 最新交付物与最终正文入口 |
| [最终正文报告](docs/乳腺癌精准治疗科研数据智能体_专业叙事与规范图示终稿_20260831.md) | 项目设计、数据整合流程与最终展示 |
| [最新评委阅读包](deliverables/乳腺癌精准治疗科研数据智能体_最新评委阅读包_20260902/README_START_HERE.md) | 当前最完整的独立阅读包 |

## 复现评测与图表

外部依赖准备完成后，可重跑 GitHub 同类项目评测：

```powershell
python scripts\run_github_competitor_benchmark.py --external-package-dir <外部评测依赖目录>
python scripts\build_github_report_charts.py
```

图表直接读取 `results.json`，不在绘图代码中填写成绩。完整逐方法指标、数据哈希和运行环境均保留在评测产物中。

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

验收时运行后端测试和前端语法检查；最终交付内容以 [最终交付索引](docs/FINAL_DELIVERY_INDEX_20260830.md) 和 [最终正文报告](docs/乳腺癌精准治疗科研数据智能体_专业叙事与规范图示终稿_20260831.md) 为准。

项目入口与硬约束见 [README_START_HERE.md](README_START_HERE.md) 和 [AGENTS.md](AGENTS.md)。
