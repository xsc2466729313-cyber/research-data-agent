# 乳腺癌科研数据 Agent 迭代交付说明

## 结论

本轮已经把“检索过宽、字段归一化错位、错误样本漏检、闭环只存在内存、评测结果缺少分层展示”处理成可运行能力。最新候选卷实测产物为：

| 指标 | 基线 | 当前 `official-candidate-autonomous-v8` |
|---|---:|---:|
| Retrieval F1 | 0.44898 | 1.00000 |
| Faithfulness | 0.65385 | 1.00000 |
| Error F1 | 0.69565 | 1.00000 |
| Repair accuracy | 0.50000 | 1.00000 |
| Traceability | 1.00000 | 1.00000 |
| SDTI | 63.36 | 100.00 |

这组数值来自同一套 `official_candidate` 的系统观察，公式没有改动。它不是 `sealed frozen_test` 成绩，因此页面仍显示安全门状态，不允许自动发布。

## 已实现

### 1. 质量与医学安全

- `ERBB2_CNA/CNV` 只归一到 `gene/variant`，不会转成 HER2 IHC Positive。
- 无检测方法时，0/1+/2+/3+ 仍按 IHC 规则处理；FISH `AMP` 可识别为扩增阳性。
- `primary_diagnosis` 不再因包含 `PR` 子串被误判为孕激素受体字段。
- 保留显式空 `source_id/raw_field/raw_value`，缺证据会阻断发布，而不是用 JSON 兜底伪造原值。
- 跨研究 Join、低置信 AUTO_MERGE、重复分析行、声明必填字段为空、单位猜测、分期拼写错误、`NA -> Negative` 均进入错误检测。

### 2. 自主检索与迭代

- 按题目意图隔离患者队列、知识证据、细胞系药敏和临床试验注册库。
- 支持显式 `GSE/NCT` 解析，以及基于来源目录的品牌队列发现（例如 SCAN-B）。
- 检索预算在规划器内部生效；同患者问题要求单一队列同时覆盖突变和临床响应。
- 闭环每轮记录输入/输出哈希、工具调用、指标快照、诊断和下一步动作。
- `data/state/agent.sqlite3` 持久化闭环结果和 episodic memory，服务重启后可通过查询接口恢复。

### 3. 分层与消融

报告文件：

- `evaluation/agent_stratified_ablation_20260829/report.md`
- `evaluation/agent_stratified_ablation_20260829/report.json`

内容包括开发集按任务类型的 TP/FP/FN/F1、候选卷迭代前后、检索层 BM25/BGE/融合、查询理解 A-E、Qwen/DeepSeek 中间智能体替换消融。缺失或未完成的实验保持 `NOT_EVALUATED`，不补值。

## 运行与查看

```powershell
# 重新生成分层/消融汇总
.\.venv\Scripts\python.exe scripts\build_agent_stratified_ablation_report.py

# 运行候选卷（不是 frozen_test）
@'\nfrom backend.app.evaluation.official_run import run_official_evaluation\nr=run_official_evaluation(retrieval="planner")\nprint(r.metrics.model_dump(mode="json"))\n'@ | .\.venv\Scripts\python.exe -
```

后端新增：

- `GET /api/evaluation/stratified`：页面使用的分层与消融报告。
- `GET /api/v2/agent/memory?limit=20`：最近闭环迭代记忆。
- `GET /api/v2/agent/closed-loop/{loop_id}`：服务重启后仍可读取已持久化闭环。

## 仍需人工/外部条件

- 候选卷有高风险问题需要人工复核，且尚未封存 `frozen_test`，所以不能宣称正式竞赛成绩或开放自动发布。
- Qwen/DeepSeek 真实替换消融依赖本地凭据；没有凭据时对应组保持 `NOT_EVALUATED`。
- 当前 SQLite 是单实例轻量状态存储；多副本部署应替换为共享数据库并保留相同表结构和审计字段。
