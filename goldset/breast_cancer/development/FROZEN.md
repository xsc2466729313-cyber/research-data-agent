# Development Gold Set 当前状态

独立审核人：**xsc**（2026-08-29）  
初标：`development-draft-builder`  
冻结文件：`MANIFEST.json`（checksum 见该文件）  
来源核验：`SOURCE_VERIFICATION.json`  
规则检查：`RULE_CHECKS.json`

这是 **development 分册**，不是 `frozen_test`，也没有拷进 `goldset/templates/`。

因此：

- 看板正式入口是 `goldset/templates/`（held-out official_candidate），正式实测 SDTI **63.36**，与本分册无关
- 不得把 development 分报成赛题正式成绩
- 已有两次真实系统观察：Source Broker seed 对照，以及千问 LIVE Agent 主链

Excel 保存后必须再存成 UTF-8，否则加载器会拒收。

## development 实测：千问 LIVE Agent（2026-08-29）

评测 ID：`development-xsc-qwen-live-20260829`  
方法：`ResearchAgentService.run`，`use_qwen=True`，`allow_deterministic_fallback=False`，`data_mode=LIVE`，模型 `qwen3.8-max`。12 道独立科研问题；千问解析问题并选工具，真实 Adapter 取数。字段/错误观察仍走 Biomarker/Gene/Drug 规则与 Quality V2（千问不得覆盖医学门）。迭代上限 4 轮（生产默认最高 8，本次为可完成的实跑边界）。

**SDTI = 66.94（development 分册，安全门 FAIL，禁止发布）**

- 12 题中 11 题 `used_qwen=true`。`q03` 两次均因千问返回的科研任务 JSON 未过 Schema 校验失败，**没有**改走确定性规划冒充千问，该题检索记为未取到。
- Retrieval P/R/F1：0.60 / 0.58 / 0.59（TP 15, FP 10, FN 11）
- Faithfulness 0.77（27/35）；Traceability 1.0
- Error P/R/F1：1.0 / 0.42 / 0.59；Repair Accuracy 0.50
- 产物：`evaluation_runs/development-xsc-qwen-live-20260829/`、`OBSERVATIONS_QWEN.json`、`OBSERVATION_AUDIT_QWEN.json`、`qwen_runs/`

短板（检索，升级前观察）：GEO 金标准 `GSE76360`/`GSE25066` 多数题未点名下载；知识证据题仍会顺手拉 METABRIC/TCGA（假阳性）；当时没有 DepMap 工具所以 q08 漏检；试验题取到 AACT 但未落到 `NCT01042379`。字段/错误分与规则层对照跑相同，不是千问映射分。

当前生产主链已补：题型匹配的 GEO/NCT 种子（阿培利司题不得误种 HER2 GEO）、DepMap 细胞系药敏（`response_domain=preclinical_cell_line`）、论文 HTML/JATS 表与图注（REVIEW，不读像素）、任务内按缺口换方法补搜。这不是看板正式分，也不是 Rule/Qwen/Full Agent 五变体矩阵分。`templates/` 已写入 held-out 正式考卷并已对本卷评分（正式 SDTI 63.36）。工作台评测区可展示本分册非正式 SDTI 66.94，禁止当正式成绩。代码接了补搜不等于工作台旧任务已经过质量门。

## development 对照：Source Broker seed（非生产主链）

评测 ID：`development-xsc-20260829`  
方法：Europe PMC 文献扫描 + Source Broker 入选/回退队列（不是千问 Agent）。  
**SDTI = 63.69**。仅作对照，不能当作生产结论。
