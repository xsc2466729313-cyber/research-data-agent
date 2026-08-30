# 指标检测报告（2026-08-30）

## 1. 检测目的

本报告验证仓库所展示的模型/系统指标是否有机器可读来源、公式是否与冻结文档一致、正式与非正式口径是否分离，以及代码和页面是否具备可复现基础。检测不生成新成绩，不使用前端写死值替代评测产物。

## 2. 正式指标来源与重算

正式数据源：`goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/metrics.json`。

| 组成项 | JSON 值 | 计数证据 |
|---|---:|---|
| Retrieval Precision | 0.354838709677 | 11 / 31 |
| Retrieval Recall | 0.611111111111 | 11 / 18 |
| Retrieval F1 | 0.448979591837 | Precision/Recall 调和平均 |
| Faithfulness | 0.653846153846 | 17 / 26 |
| Traceability | 1.000000000000 | 26 / 26 |
| Error Precision | 1.000000000000 | 8 / 8 |
| Error Recall | 0.533333333333 | 8 / 15 |
| Error F1 | 0.695652173913 | Precision/Recall 调和平均 |
| Repair Accuracy | 0.500000000000 | 1 / 2 |

冻结公式：

```text
SDTI = 100 *
  (Retrieval F1 * Faithfulness * Traceability * Error F1 * Repair Accuracy) ** (1/5)
```

代入机器可读值，得到 `63.359663932389`，四舍五入为 **63.36**，与 `metrics.json` 和 README 一致。公式来源为 `docs/06_评测指标与SDTI.md`，本次未修改。

## 3. 安全门检测

| 检查 | 当前值 | 阈值 | 结果 |
|---|---:|---:|---|
| Fake source rate | 0.0000 | <= 0.01 | 通过 |
| Faithfulness | 0.6538 | >= 0.90 安全门 | 失败 |
| Traceability | 1.0000 | >= 0.95 | 通过 |
| 高风险未决问题 | 5 | 0 | 失败 |
| sealed frozen test | 否 | 是 | 未完成 |

综合结论：`gate=FAIL`，`publish_allowed=false`，与正式 JSON 一致。

## 4. 口径隔离检测

| 指标集合 | 数值 | 合法用途 | 禁止用途 |
|---|---:|---|---|
| official_candidate | SDTI 63.36 | 当前正式口径观察 | 宣称 sealed 最终成绩 |
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

工程整理状态：**通过交付检查**。模型效果状态：**未达到自动发布门槛**。最准确的表述是“系统已可运行、可复现、可审计；正式 SDTI 63.36，安全门 FAIL，仍需提升检索、Faithfulness、Repair 和清洗能力”。
