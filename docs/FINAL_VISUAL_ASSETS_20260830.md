# 系统框图、流程图与截图索引（2026-08-30）

本页汇总最终交付中的视觉证据。图像均为仓库本地文件，可直接在 GitHub 预览；SVG 版本便于后续编辑，PNG 版本用于报告和演示。

## 1. 系统技术架构

![乳腺癌精准治疗科研数据智能体系统技术架构](images/system-architecture-v3.png)

- PNG：[system-architecture-v3.png](images/system-architecture-v3.png)
- SVG：[system-architecture-v3.svg](images/system-architecture-v3.svg)
- 内容：交互接入、智能体编排、真实数据源、处理治理和科研输出五层架构。

## 2. 端到端流程与质量闭环

![端到端流程与质量闭环](images/system-workflow-v3.png)

- PNG：[system-workflow-v3.png](images/system-workflow-v3.png)
- SVG：[system-workflow-v3.svg](images/system-workflow-v3.svg)
- 内容：科研问题、ResearchSpec、工具选择、真实取数、标准化、实体融合、Evidence、四层质量门与 Gap 反馈。

## 3. 当前版本首页

![当前版本科研规划工作台](images/08-current-home-20260830.png)

该图在 2026-08-30 从本地 `127.0.0.1:8010` 实际运行页面截取。页面包含五阶段导航、研究方向示例、输入框、完整规划按钮和右侧详情区；截图时浏览器控制台无 error/warning。

## 4. 核心功能截图

| 截图 | 说明 |
|---|---|
| [01-planning-workspace.png](images/01-planning-workspace.png) | 科研规划工作台 |
| [02-qwen-connection.png](images/02-qwen-connection.png) | Qwen 临时会话与连接 |
| [03-api-console.png](images/03-api-console.png) | FastAPI/接口交互 |
| [04-research-dataset.png](images/04-research-dataset.png) | 患者/样本级科研数据表 |
| [05-quality-dashboard.png](images/05-quality-dashboard.png) | 质量看板与数据字典 |
| [06-raw-audit.png](images/06-raw-audit.png) | 原始字段审计 |
| [07-lineage.png](images/07-lineage.png) | 来源与 Evidence 追溯 |
| [02-user-workflow-mobile.png](images/02-user-workflow-mobile.png) | 移动端布局 |

## 5. 评测图表

![四模块公开基准对比](images/github-benchmark-summary.png)

![BEIR 五数据集检索分层](images/github-retrieval-breakdown.png)

图表由评测 `results.json` 生成，不在绘图脚本里手填成绩。四个模块使用不同数据与指标，只能逐行比较。

## 6. 公开对照增强图（2026-09-02）

本轮新增图只覆盖公开能力对照和解释，不修改已有系统架构图、端到端流程图或内容结构图。它们统一读取 `evaluation/github_competitor_benchmark_20260830/results.json`，并保留本项目领先、持平和落后的真实结果。

| 图像 | 作用 |
|---|---|
| [public-comparison-scorecard-20260902.png](images/public-comparison-scorecard-20260902.png) | 四个公开能力层宏平均总览 |
| [public-retrieval-datasets-20260902.png](images/public-retrieval-datasets-20260902.png) | `PB-01` 五个检索数据集逐项对照 |
| [public-schema-datasets-20260902.png](images/public-schema-datasets-20260902.png) | `PB-02` 十个字段匹配任务逐项对照 |
| [public-entity-datasets-20260902.png](images/public-entity-datasets-20260902.png) | `PB-03` 五个实体匹配任务逐项对照 |
| [public-cleaning-datasets-20260902.png](images/public-cleaning-datasets-20260902.png) | `PB-04` 六个错误检测任务逐项对照 |
| [public-comparison-failure-map-20260902.png](images/public-comparison-failure-map-20260902.png) | 解释当前不占优的原因和下一步验证方案 |
| [public-comparison-question-map-20260902.png](images/public-comparison-question-map-20260902.png) | 保留 `RQ-01`，说明它与 `PB-01`—`PB-04` 的关系 |

题号、对照方法、指标含义和失败原因见 [PUBLIC_COMPARISON_GUIDE_20260902.md](PUBLIC_COMPARISON_GUIDE_20260902.md)。

## 7. 图像验收

| 检查 | 结果 |
|---|---|
| 架构图 | 2400 x 1350，PNG/SVG 均存在，文字可读 |
| 流程图 | 2400 x 1350，PNG/SVG 均存在，闭环箭头完整 |
| 核心桌面截图 | 1265 x 712 或 1600 x 1050，页面内容完整 |
| 移动端截图 | 390 x 844，无关键内容重叠 |
| 当前首页截图 | 1280 x 720，与本次未提交前端版本一致 |
| 评测图表 | 数据标签与报告数字一致 |
