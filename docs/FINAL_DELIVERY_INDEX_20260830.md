# 最终交付索引（2026-08-30）

本页是本仓库的统一验收入口。交付物以 Markdown、PNG/SVG 和机器可读 JSON 为准；Word 报告及其渲染缓存不在本次 GitHub 交付范围内。

## 当前结论

系统主链已经可运行，后端全量测试通过，前端首页和核心截图可正常展示。模型效果仍处于“可用于科研数据整理与审计、不可自动发布科研结论”的阶段：正式 `official_candidate` 观察分 SDTI 为 **63.36**，目标为 90，安全门 **FAIL**，`publish_allowed=false`。

| 交付项 | 文件 | 状态 |
|---|---|---|
| 框架说明报告 | [FINAL_FRAMEWORK_REPORT_20260830.md](FINAL_FRAMEWORK_REPORT_20260830.md) | 完成 |
| 系统设计报告 | [FINAL_SYSTEM_DESIGN_REPORT_20260830.md](FINAL_SYSTEM_DESIGN_REPORT_20260830.md) | 完成 |
| 结果报告 | [FINAL_RESULTS_REPORT_20260830.md](FINAL_RESULTS_REPORT_20260830.md) | 完成 |
| 指标检测报告 | [FINAL_METRICS_VALIDATION_REPORT_20260830.md](FINAL_METRICS_VALIDATION_REPORT_20260830.md) | 完成 |
| 系统框图、流程图与截图索引 | [FINAL_VISUAL_ASSETS_20260830.md](FINAL_VISUAL_ASSETS_20260830.md) | 完成 |
| 项目 README | [../README.md](../README.md) | 完成 |
| 机器可读正式指标 | [official metrics.json](../goldset/breast_cancer/official_candidate/evaluation_runs/official-candidate-20260829T132222Z/metrics.json) | 完成 |
| 公开同类项目对比证据 | [results.json](../evaluation/github_competitor_benchmark_20260830/results.json) | 完成 |
| 公开对照题号与解释 | [PUBLIC_COMPARISON_GUIDE_20260902.md](PUBLIC_COMPARISON_GUIDE_20260902.md) | 完成 |

## 验收结果

| 检查 | 结果 |
|---|---|
| 后端测试 | `482 collected`，全量执行通过；8 项因真实外部服务条件跳过 |
| 前端语法 | `node --check frontend/app.js` 通过 |
| 本地服务 | FastAPI 启动成功，`/health` 与首页可访问 |
| 浏览器验收 | 首页 DOM、五阶段导航、输入区、详情区正常；控制台无 error/warning |
| 图像验收 | 架构图、流程图、数据表、质量看板及当前首页截图可正常打开 |
| 敏感信息 | `.env`、缓存、运行日志、Word 工作目录不进入 Git |

## 推荐阅读顺序

1. 先读根目录 [README](../README.md)，了解项目价值、启动和真实成绩。
2. 读框架说明与系统设计，理解模型、工具、规则、Evidence 和质量门的责任边界。
3. 读结果报告与指标检测报告，区分正式 SDTI、development 观察和公开模块基准。
4. 通过视觉资产索引查看系统框图、端到端流程图和界面截图。
5. 需要看公开对照时，先读 [PUBLIC_COMPARISON_GUIDE_20260902.md](PUBLIC_COMPARISON_GUIDE_20260902.md)，再看逐题图和机器可读结果。

## 不能误读的边界

- 正式 SDTI 是 **63.36**，不是 development 的 66.94，也不是候选运行中的更高内部观察值。
- `official_candidate` 尚未 sealed frozen test，因此只能作为当前正式口径观察，不能宣称最终竞赛成绩。
- 任务内 `target match=1.00`、`Traceability=1.00` 或 Quality Gate PASS 不等于正式 SDTI 达标。
- HER2 IHC 2+、ERBB2 CNA、患者响应和细胞系药敏保持独立语义，不为提高分数而强行映射。
- 公开模块基准用于定位能力强弱，四项异构指标不能相加成项目总分。
