# 前端与内核截图索引

更新时间：2026-09-06
用途：统一定位科研助手首页、内核实验室、真实运行证据和 Agent 流程图。图片按 `S`（UI）、`K`（内核壳层）、`R`（运行证据）、`D`（流程/架构）编号；链接均指向仓库中的原图，不把多张图拼成一张长图。

## 先看证据边界

- 用户附图对应旧版移动端红框标注。新版 `S02`/`S04` 保留红色框、箭头和中文说明，但把说明移到画布外，避免遮住原界面；它们是附图的替代版本，不是新的运行结果。
- `S01`—`S07` 和 `K01`—`K07` 展示页面布局或空闲内核，不证明后端已经完成一次任务。尤其是 `K04` 的 Runtime 是“待运行”状态。
- `R01`—`R06` 是 2026-09-06 真实闭环任务 `loop-91ef39cffd32:r3` 的页面证据：156 行 × 19 列、69 名患者、156 个样本、24 个来源、Agent Runtime 7/7、四层质量门 `PASS`。这是可复核运行快照，不是新的统一 benchmark 成绩。
- `R18`/`R19` 是同一当前任务按用户参考样式重画的两张讲解图：质量门 + 结构化数据，以及原始样本特征弹窗。红框、箭头和文字只用于定位证据；弹窗仍保留可滚动的完整原始记录。
- `R07`—`R11` 是另一条 2026-09-06 确定性 `REVIEW` 运行；`R12`—`R17` 是 2026-08-31 的历史代表任务截图。不同任务的数值不能混用。
- 截图不构成临床诊断或治疗建议；医学安全边界和来源追溯以 `configs/`、后端质量门及相关文档为准。

## S · 科研助手首页（Planner UI）

| 编号 | 原图 | 路径 / 视口 | 内容与边界 |
|---|---|---|---|
| S01 | [桌面干净首页](images/frontend-home-clean-20260906.png) | `/` · 1440×1000 | 当前“新研究/提出方向”入口，无文字标注。 |
| S02 | [桌面首页红色讲解标注](images/frontend-home-annotated-20260906.png) | `/` · 1870×1000 | 五阶段规划、示例问题、问题输入、审查标签和科研兔入口；红框/箭头/文字移到外侧，不遮挡正文。 |
| S03 | [移动端干净首页](images/frontend-home-mobile-clean-20260906.png) | `/` · 390×1246 | 窄屏原始布局。 |
| S04 | [移动端首页红色讲解标注](images/frontend-home-mobile-annotated-20260906.png) | `/` · 810×1246 | 替代用户附图的非重叠标注；右侧红色文字说明和箭头，科研助手（科研兔）单独标出。 |
| S05 | [科研助手打开状态](images/research-companion-open-20260906.png) | `/` · 1440×1000 | 展示右下角科研解析助手打开后的页面关系。 |
| S06 | [科研助手面板裁剪](images/research-companion-panel-20260906.png) | `/` · 500×597 | 独立面板特写，明确标注“科研兔/科研解析助手”。 |
| S07 | [科研助手面板红色讲解标注](images/research-companion-panel-annotated-20260906.png) | `/` · 850×597 | 用红框、箭头和文字说明“只读解析入口”，与研究问题输入区区分。 |

## K · 内核实验室壳层（Kernel UI）

访问路径为 `/?surface=kernel`。这些图用于说明后端内核的前端入口、角色分工和任务输入位置；未提交任务时不应解读为运行成绩。

| 编号 | 原图 | 路径 / 视口 | 内容与边界 |
|---|---|---|---|
| K01 | [内核实验室桌面全页](images/kernel-lab-desktop-clean-20260906.png) | `/?surface=kernel` · 1440×2415 | Hero、配置、Agent 架构、Runtime、任务入口及结果容器的空闲壳层。 |
| K02 | [内核实验室移动端全页](images/kernel-lab-mobile-clean-20260906.png) | `/?surface=kernel` · 390×3281 | 移动端响应式壳层；页面较长，适合按章节查看。 |
| K03 | [Agent 架构区域](images/kernel-lab-agent-architecture-20260906.png) | `#agent-architecture` · 1326×1270 | 证据驱动的混合式多 Agent 编排及职责说明；不是一次运行日志。 |
| K04 | [Agent Runtime 空闲卡片](images/kernel-lab-agent-runtime-20260906.png) | `#agent-runtime` · 1287×223 | 未提交问题时七个角色均为“待运行”；不能代替 `R03` 真实运行证据。 |
| K05 | [任务输入区域](images/kernel-lab-task-entry-20260906.png) | `#task-entry` · 1326×497 | “输入一句话，内核实验室自动推进”入口和运行边界设置。 |
| K06 | [内核实验室红色讲解全页](images/kernel-lab-desktop-annotated-20260906.png) | `/?surface=kernel` · 1870×2415 | 用红框、箭头和文字说明内核总览、运行配置、Agent 架构、Runtime、任务入口。 |
| K07 | [Agent 架构红色讲解标注](images/kernel-lab-agent-architecture-annotated-20260906.png) | `#agent-architecture` · 1686×1270 | 单独标出“任务规划 → 证据与规则 → 独立校验 → 可追溯交付”流程图。 |

## R · 真实运行与结果审查证据

### R1 · 2026-09-06 HER2 真实闭环运行（主证据）

以下截图来自同一后端任务 `loop-91ef39cffd32:r3`，不是 mock 或静态填充：156 行 × 19 列、69 名患者、156 个样本、24 个来源，Agent Runtime 7/7，四层质量门 `PASS`。页面同时保留“探索性准入不等于正式发表或临床结论”的边界说明；这是可复核运行快照，不是新的统一 benchmark 成绩。

| 编号 | 原图 | 建议截取区域 | 证据边界 |
|---|---|---|---|
| R01 | [HER2 真实运行全页](images/kernel-lab-live-loop91-her2-20260906.png) | `/?surface=kernel` · 1440×7608 | task `loop-91ef39cffd32:r3`；状态完成；156×19；质量门 PASS。 |
| R02 | [HER2 任务摘要与 PICO](images/kernel-lab-live-loop91-her2-20260906-briefing.png) | `#protocol-brief` · 1326×1133 | 69 名患者、156 个样本、19 个字段；保留研究队列边界和来源说明。 |
| R03 | [HER2 Agent Runtime](images/kernel-lab-live-loop91-her2-20260906-runtime.png) | `#agent-runtime` · 1287×223 | 7/7 已审查；角色状态来自本次任务返回，不外推为模型排行。 |
| R04 | [HER2 四层质量门](images/kernel-lab-live-loop91-her2-20260906-quality-gate.png) | `#quality-gates` · 1326×252 | 四层均 PASS；探索性准入不等于临床结论。 |
| R05 | [HER2 科研数据集](images/kernel-lab-live-loop91-her2-20260906-research-data.png) | `#research-data` · 1326×869 | 页面显示 156 行患者/样本级结果；完整字段保留在导出入口。 |
| R06 | [HER2 来源血缘](images/kernel-lab-live-loop91-her2-20260906-provenance.png) | `#provenance` · 1326×1568 | 来源登记、状态和校验值示例；不把不同研究患者编号直接合并。 |

### R3 · 当前版本参考样式讲解图

这两张图使用当前前端（运行时显示 `2.2.0-qwen-agent`）和同一真实任务 `loop-91ef39cffd32:r3` 重新采集，视觉上对齐用户提供的红框/箭头/说明样式。第一张把四层质量门和结构化数据入口放在同一视口；第二张打开首个样本 `GSM1232992` 的原始特征审计弹窗。弹窗首屏显示 8 行，右侧滚动条表明其余原始项仍可继续查看。

| 编号 | 参考样式截图 | 视口 / 内容 | 证据边界 |
|---|---|---|---|
| R18 | [质量门与结构化数据红框讲解图](images/kernel-lab-current-quality-data-callout-20260906.png) | 1440×1100 · 四层质量门 + 患者/样本计数 + 主表开头 | 当前任务显示 69 名患者、156 个样本、四层质量门 PASS；不是 benchmark 成绩。 |
| R19 | [原始样本特征弹窗红框讲解图](images/kernel-lab-current-raw-characteristics-callout-20260906.png) | 1440×1000 · 标准化值 / 原始值 / 原始记录说明 | 标准化只改变展示层；原始值和导出记录保留，可滚动复核。 |

### R2 · 2026-09-06 确定性 REVIEW 运行（边界对照）

这组截图来自另一条任务 `agent-bed29b9fe8c9`：13 行 × 31 列、9 个 `source_items`、2 个候选来源，质量门 `REVIEW`。它用于展示“有结果但仍需补核”的安全路径，不应与 R1 的 PASS 运行混用。

| 编号 | 原图 | 建议截取区域 |
|---|---|---|
| R07 | [确定性 REVIEW 结果总览](images/kernel-lab-deterministic-pik3ca-20260906.png) | 结果总览 |
| R08 | [确定性 REVIEW Agent Runtime](images/kernel-lab-deterministic-pik3ca-runtime-20260906.png) | `#agent-runtime` |
| R09 | [确定性 REVIEW 质量门](images/kernel-lab-deterministic-pik3ca-quality-gates-20260906.png) | `#quality-gates` |
| R10 | [确定性 REVIEW 科研数据集](images/kernel-lab-deterministic-pik3ca-research-data-20260906.png) | `#research-data` |
| R11 | [确定性 REVIEW 数据血缘](images/kernel-lab-deterministic-pik3ca-provenance-20260906.png) | `#provenance` |

### R2 · 2026-08-31 历史代表任务

| 编号 | 原图 | 用途 |
|---|---|---|
| R12 | [历史任务摘要](images/annotated-positive-04-task-summary-20260831.png) | 代表任务的摘要、任务状态和主数据交付概览。 |
| R13 | [历史质量门](images/annotated-positive-05-quality-gate-20260831.png) | 质量门判定与待复核项示例。 |
| R14 | [GSE76360 数据表](images/annotated-positive-06-gse76360-table-20260831.png) | 历史患者/样本级表格展示。 |
| R15 | [原始审计字段](images/annotated-positive-07-raw-audit-20260831.png) | `raw_field`、`raw_value` 和来源审计示例。 |
| R16 | [来源血缘](images/annotated-positive-08-lineage-20260831.png) | 来源选择与数据路径示例。 |
| R17 | [科研适用性](images/annotated-positive-09-readiness-20260831.png) | 可科研性、风险和后续建议示例。 |

## D · Agent 流程图与架构图

| 编号 | 原图 | 用途 |
|---|---|---|
| D01 | [证据驱动 Agent 架构 SVG](../frontend/agent-architecture-evidence-driven.svg) | 内核页直接使用的主 Agent、规划/采集/核验/质量角色和规则/RAG 支撑图。 |
| D02 | [中文 Agent 完整工作流 SVG](../frontend/agent-workflow-cn.svg) | 从科研问题、来源发现到质量门和交付的完整闭环；适合放入报告或演示。 |
| D03 | [中文 Agent 工作流 PNG](images/agent-workflow-cn-20260904.png) | D02 的高分辨率渲染版，便于阅读包离线预览。 |
| D04 | [标准闭环流程](images/closed-loop-workflow-standard-v2-20260831.png) | 缺口诊断、换方法补查、质量判断和停止条件。 |
| D05 | [在线评测工作流 PNG](images/online-evaluation-workflow-cn-20260901.png) / [SVG](images/online-evaluation-workflow-cn-20260901.svg) | 评测任务、运行、审计和报告产物链。 |
| D06 | [用户工作流](images/01-user-workflow.png) | 用户从问题输入到结果查看的简化路径。 |
| D07 | [来源角色图](images/source-roles-cn-20260831.png) | 公开来源在规划、采集和核验中的职责分层。 |
| D08 | [系统架构图](images/system-architecture-v3.png) | v3 系统层级与模块边界。 |
| D09 | [系统工作流图](images/system-workflow-v3.png) | 系统级处理链，和 D01/D02 的 Agent 角色图互补。 |
| D10 | [系统架构期刊版](images/system-architecture-journal-small-arrows-20260901.png) / [大图](images/system-architecture-journal-20260831.png) | 报告排版用架构图两个尺寸。 |
| D11 | [四个质量问题](images/four-quality-questions-cn-20260831.png) | 真实性、字段、身份和科研适用性四层检查。 |

## 报告中的其他图表

以下图像是评测或方法对照图，不是前端截图；完整正文引用关系见 [`PROJECT_REPORT.md`](PROJECT_REPORT.md)。

| 图表 | 原图 |
|---|---|
| GitHub 基准摘要 / 检索拆分 | [summary](images/github-benchmark-summary.png) · [breakdown](images/github-retrieval-breakdown.png) |
| 规划模型对照 | [planner-model-comparison-20260831.png](images/planner-model-comparison-20260831.png) · [中文标注](images/planner-model-comparison-cn-20260831.png) |
| 检索方法 / 查询策略 | [retrieval-method](images/retrieval-method-comparison-cn-20260831.png) · [query-strategy](images/query-strategy-comparison-cn-20260831.png) |
| 公开数据集地图 | [cleaning](images/public-cleaning-datasets-20260902.png) · [entity](images/public-entity-datasets-20260902.png) · [retrieval](images/public-retrieval-datasets-20260902.png) · [schema](images/public-schema-datasets-20260902.png) |
| 公开对照结果 | [question map](images/public-comparison-question-map-20260902.png) · [scorecard](images/public-comparison-scorecard-20260902.png) · [failure map](images/public-comparison-failure-map-20260902.png) |
| SDTI 组成 | [sdti-component-comparison-20260830.png](images/sdti-component-comparison-20260830.png) |
| 评测与质量补充 | [system-metrics-comparison-cn-20260831.png](images/system-metrics-comparison-cn-20260831.png) |

## 复采与校验命令

```powershell
# 本地启动（FastAPI 同时托管前端）
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

# 重新采集 S/K 干净截图（需要仓库提供的临时 Playwright runtime）
$env:NODE_PATH = "tmp/pwcap/node_modules"
node scripts/capture_frontend_screenshots.js

# 如需固定一条已完成任务，另设任务 ID 和结果文件前缀
$env:RESEARCH_AGENT_TASK_ID = "loop-91ef39cffd32:r3"
$env:RESEARCH_AGENT_RESULT_PREFIX = "kernel-lab-live-loop91-her2"
$env:RESEARCH_AGENT_REFERENCE_TASK_ID = "loop-91ef39cffd32:r3"
node scripts/capture_frontend_screenshots.js

# 生成 S02/S04、S07、K06/K07 的红框/箭头讲解版本
python scripts/annotate_frontend_screenshots.py

# 生成当前版本参考样式的 R18/R19 两张图
python scripts/annotate_reference_style_screenshots.py

# 检查脚本语法
node --check scripts/capture_frontend_screenshots.js
python -m py_compile scripts/annotate_frontend_screenshots.py
python -m py_compile scripts/annotate_reference_style_screenshots.py
```

真实运行截图应在任务完成后从同一浏览器会话截取，并在图注中保留 task ID、运行模式、行列数、来源数和质量门状态；不要用空闲 `K04` 冒充运行证据。
