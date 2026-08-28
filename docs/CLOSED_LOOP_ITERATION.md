# 闭环迭代协议

## 目的

闭环迭代把一次科研任务拆成有限、可审计的反馈轮次：

```text
初始问题
→ 第一轮检索/整合/质量输出
→ 缺口诊断
→ 安全修正检索输入
→ 第二轮重新执行
→ 指标前后对比
→ 达标或无改进时停止
```

入口为 `POST /api/v2/agent/closed-loop`。请求体的 `initial_request` 与普通
`/api/agent/tasks` 使用相同的 `AgentTaskRequest`，并额外设置 `max_iterations`
（2--4）、`require_two_rounds`（默认 `true`）和 `min_improvement`。默认产品行为是
固定完成两轮：第一轮即使质量门通过，也会生成补充验证请求；第二轮才允许按质量门
或无改进规则停止。将 `require_two_rounds=false` 可兼容旧的提前停止策略。

也可以运行 `scripts/run_closed_loop_benchmark.py` 生成单次真实运行的 JSON 产物；该脚本明确标记为 operational run，不输出正式 benchmark 分数。

## 跨轮契约

每个 `ClosedLoopIteration` 同时保留：

- 本轮完整 `AgentTaskResult`；
- `ClosedLoopDiagnosis`：缺失字段、目标匹配和证据链问题；
- `ClosedLoopAction`：下一轮将改变的检索字段；
- `ClosedLoopMetricSnapshot`：required field coverage、target match、traceability、review burden 和 progress score；
- `ClosedLoopAudit`：输入/输出哈希、调用 ID、策略 ID、时间和安全约束。

`progress_score` 是任务内反馈信号，不是正式 benchmark、Repair Accuracy 或 SDTI，避免把单次闭环改善冒充正式成绩。

## 安全停止规则

闭环最多运行 4 轮。完成最低要求的两轮后，质量门通过、输入重复、没有新的安全修正动作、达到最大轮次，或上一轮没有达到最小改进时停止。第一轮通过时的动作类型为 `supplemental_verification`；存在诊断缺口时为 `refocus_retrieval`。修正器只会：

- 把诊断出的缺口字段追加到下一轮问题；
- 把第一轮 coverage、target match、traceability 和已尝试策略摘要写入下一轮反馈上下文；
- 优先未尝试的来源；
- 打开已有的受限搜集迭代。

它不会放宽患者/样本关联、修改 HER2 或 response 事实、删除 provenance，也不会把 fallback 结果写成模型成绩。

## 运行记录

2026-08-28 的历史真实数据模式 smoke 运行保存在 `evaluation/closed_loop/live_smoke.json`；它生成于两轮默认策略接入前，仅用于保留当时的运行记录。当前默认策略的真实两轮 smoke 保存在 `evaluation/closed_loop/live_two_round_smoke_20260828.json`：两轮各 8 次工具调用、输入哈希不同，首轮和二轮 progress score 均为 `0.96`，说明即使首轮已达标也确实完成了第二轮复核；`plan_only` 对照保存在 `evaluation/closed_loop/two_round_smoke_20260828.json`。这些数值只反映任务运行状态，不代表乳腺癌 Gold Set、正式 benchmark 或 SDTI。

同日的 `plan_only` smoke 保存在 `evaluation/closed_loop/smoke.json`，由于没有访问患者级数据，指标保持 `0.00 -> 0.00`；这说明闭环不会用规划文本伪造数据改善。
