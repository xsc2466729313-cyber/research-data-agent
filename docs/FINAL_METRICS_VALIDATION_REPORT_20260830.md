# 指标检测报告（2026-08-30）

## 1. 检测目的

本报告验证仓库所展示的模型/系统指标是否有机器可读来源、公式是否与冻结文档一致、正式与非正式口径是否分离，以及代码和页面是否具备可复现基础。检测不生成新成绩，不使用前端写死值替代评测产物。

## 2. 正式指标来源与重算

历史基线数据源：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/metrics.json`。严格 Qwen LIVE 候选数据源：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-qwen-live-audited-final-20260830/metrics.json`。

严格 Qwen LIVE 候选记录：SDTI **91.7451**，Retrieval F1 **0.6500**，Faithfulness **1.0000**，Traceability **1.0000**，Error F1 **1.0000**，Repair Accuracy **1.0000**；`qwen3.8-max` 实际调用 11/11，兜底 0，来源校验 186/186 通过。该卷 `frozen=false`，且 5 个任务质量门 REVIEW，因此 `gate=REVIEW`、`publish_allowed=false`。

| 组成项（严格 Qwen LIVE） | JSON 值 | 计数证据 |
|---|---:|---|
| Retrieval Precision | 0.590909090909 | 13 / 22 |
| Retrieval Recall | 0.722222222222 | 13 / 18 |
| Retrieval F1 | 0.650000000000 | Precision/Recall 调和平均 |
| Faithfulness | 1.000000000000 | 26 / 26 |
| Traceability | 1.000000000000 | 26 / 26 |
| Error Precision | 1.000000000000 | 15 / 15 |
| Error Recall | 1.000000000000 | 15 / 15 |
| Error F1 | 1.000000000000 | Precision/Recall 调和平均 |
| Repair Accuracy | 1.000000000000 | 3 / 3 |

冻结公式：

```text
SDTI = 100 *
  (Retrieval F1 * Faithfulness * Traceability * Error F1 * Repair Accuracy) ** (1/5)
```

代入严格 Qwen 机器可读值，得到 `91.74505626105`，四舍五入为 **91.75**。历史未调用 Qwen 基线仍为 63.36。公式来源为 `docs/06_评测指标与SDTI.md`，本次未修改。

## 3. 安全门检测

| 检查 | 当前值 | 阈值 | 结果 |
|---|---:|---:|---|
| Fake source rate | 0.0000 | <= 0.01 | 通过 |
| Faithfulness | 1.0000 | >= 0.90 安全门 | 通过 |
| Traceability | 1.0000 | >= 0.95 | 通过 |
| 实时任务质量门 REVIEW | 5 | 0 | 阻断 |
| sealed frozen test | 否 | 是 | 阻断 |

综合结论：严格 Qwen LIVE 为 `gate=REVIEW`，`publish_allowed=false`；阻断项是 5 个实时任务质量门 REVIEW 与候选卷尚未 sealed frozen。

## 4. 口径隔离检测

| 指标集合 | 数值 | 合法用途 | 禁止用途 |
|---|---:|---|---|
| 历史 official_candidate 基线 | SDTI 63.36 | 未调用 Qwen 的历史对照 | 宣称当前模型成绩 |
| 严格 Qwen LIVE candidate | SDTI 91.75 | 当前代码/API 回归观察 | 宣称 sealed 最终成绩 |
| development Qwen LIVE | SDTI 66.94 | 迭代与回归诊断 | 写入正式成绩栏 |
| 任务内 closed-loop | progress 0.915 -> 0.960 | 比较同任务两轮 | 替代 SDTI/Repair Accuracy |
| BEIR/Valentine/DeepMatcher/Raha | 模块级分数 | 定位模块能力 | 合成临床或项目总分 |

检测结果：README 与本次四份最终报告均明确分栏，没有把 66.94 写成正式分，也没有把公开模块指标相加。

## 5. 公开对比证据检测

机器可读来源：`evaluation/github_competitor_benchmark_20260830/results.json`；报告来源：`evaluation/github_competitor_benchmark_20260830/report.md`。

- 检索：项目融合 0.3791，对照 BGE 0.3880。
- 字段匹配：项目 V3 0.7994，对照 COMA 0.7670。
- 实体匹配：项目自适应融合 0.7449，对照 RecordLinkage 0.7440。
- 清洗检测：项目 0.5726，对照 Raha PVD+RVD 子集 0.8159。
- DeepMatcher、Ditto、HoloClean 未公平复现的项目保持 `NOT_EVALUATED`，没有抄论文数字。

## 6. 工程检测

执行日期：2026-08-30，Windows，Python 3.14。

| 命令/检查 | 结果 |
|---|---|
| `python -m pytest -q` | 通过；进度 100%，8 项外部服务条件跳过 |
| `pytest --collect-only` | 482 tests collected |
| `node --check frontend/app.js` | 通过 |
| FastAPI 本地启动 | `127.0.0.1:8010` 启动成功 |
| 浏览器首页 | 标题、导航、输入、详情区正常 |
| 浏览器控制台 | 0 条 error/warning |

测试仅出现两条依赖弃用警告：Starlette TestClient/httpx 与 Python 3.15 前的 `load_module()`；不影响本次通过结论，后续依赖升级时处理。

## 7. 完整性与敏感信息检测

- `.env`、本地环境、缓存、日志、公开基准大文件和状态库均被忽略。
- Word 报告与渲染工作目录 `evidence_delivery/` 不纳入本次 GitHub 交付。
- 报告中的来源、指标和图表均指向仓库内 JSON/Markdown 证据。
- 当前结果包含公开科研数据与合成/公开基准，不提交 API Key 或未授权患者数据。

## 8. 最终判定

工程整理状态：**通过交付检查**。严格 Qwen LIVE 模型观察为 **SDTI 91.75**，检索 F1 仍低于 90% 目标；安全门 **REVIEW**，不得自动发布，直到 5 个任务 REVIEW 解除且 Gold Set sealed frozen。
