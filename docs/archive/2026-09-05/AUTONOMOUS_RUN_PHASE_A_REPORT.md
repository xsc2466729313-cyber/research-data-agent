# Autonomous Research Run Phase A 实施报告

> 实施范围：Autonomous Research Run Orchestrator
>
> 状态：Phase A 完成
>
> 本阶段没有实现 Astronomy Adapter、VizieR、资产中心或新 Workspace 前端。

## 1. 新增文件

### 后端运行时

- `backend/app/v31/__init__.py`
- `backend/app/v31/models.py`
- `backend/app/v31/store.py`
- `backend/app/v31/risk.py`
- `backend/app/v31/stages.py`
- `backend/app/v31/service.py`
- `backend/app/v31/api.py`

### 测试

- `backend/tests/autonomous_run/__init__.py`
- `backend/tests/autonomous_run/test_phase_a.py`

## 2. 修改文件

- `backend/app/main.py`

本次修改只增加 v31 route mount 和 `AutonomousResearchRunService` 的应用初始化。现有 v30 路由、医疗服务、冻结配置和既有适配器没有重构。

工作区中 `backend/app/main.py` 还存在本次任务之前已有的其他未提交修改，本阶段保留这些修改，没有回滚或覆盖。

## 3. Run 状态机

已实现的自动阶段为：

```text
intake
  → planning
  → discovering
  → structuring
  → linking
  → quality_review
  → completed_preview
```

Run 状态支持：

- `queued`
- `running`
- `paused`
- `waiting_for_confirmation`
- `completed`
- `failed`
- `cancelled`

正常科研问题不再因为普通 clarification 缺失而停在前端等待点击。Planner readiness 不满足时，系统生成带有 `planner_gate=needs_review` 的 working plan，并继续向 preview 推进。

`completed_preview` 的语义严格限定为：规划、来源候选、字段 schema、映射和 evidence preview 已完成。它不表示真实数据已获取，也不表示 `dataset.csv` 已生成。

## 4. Research Run 与 Event 模型

### ResearchRun

已实现字段：

- `run_id`
- `research_id`（Phase A 可为空）
- `session_id`
- `question`
- `interpreted_goal`
- `status`
- `current_stage`
- `internal_stage`
- `constraints`
- `risk_flags`
- `started_at`
- `updated_at`
- `completed_at`
- `failure`
- `stage_results`
- `asset_refs`

### ResearchRunEvent

已实现字段：

- `event_id`
- `run_id`
- `sequence`
- `event_type`
- `stage`
- `message`
- `data_ref`
- `evidence_refs`
- `risk_level`
- `created_at`

已实现事件类型包括：

- `run_created`
- `stage_started`
- `stage_completed`
- `source_selected`
- `risk_raised`
- `confirmation_required`
- `asset_created`（模型预留，Phase A 不产生正式 Asset）
- `run_paused`
- `run_cancelled`
- `run_failed`
- `run_completed`

同一 Run 的事件 sequence 由 Event Store 在锁内分配，保证单调递增。

## 5. API

新增最小 API：

### 创建 Run

`POST /api/v31/research-runs`

输入：

```json
{
  "question": "我想研究Ia型超新星光变曲线",
  "research_id": null,
  "constraints": []
}
```

返回 HTTP 202，包含 Run snapshot，至少包括：

- `run_id`
- `session_id`
- `status`
- `current_stage`

创建后由后端 `ThreadPoolExecutor` 自动提交运行，不依赖浏览器继续发起下一阶段请求。

### 获取 Run

`GET /api/v31/research-runs/{run_id}`

### 获取事件

`GET /api/v31/research-runs/{run_id}/events`

返回按 `sequence` 排序的事件列表。

### 暂停

`POST /api/v31/research-runs/{run_id}/pause`

Phase A 支持暂停，但暂不实现 resume API。

### 取消

`POST /api/v31/research-runs/{run_id}/cancel`

暂停或取消后，worker 在下一个控制点停止，不会执行下游阶段。

旧 `/api/v30/*` 未删除、未改写，仍保持原有行为。

## 6. 各阶段调用的旧能力

### intake

直接调用：

- `V30Runtime.route`
- `V30Runtime.turn`
- v30 `RouterAgent`
- v30 `ResearchCopilot`
- v30 `MemoryService`

输出：

- 原始问题保留在 `ResearchRun.question`。
- `interpreted_goal`。
- `domain`。
- working assumptions。

对于 Ia 型超新星，现有 Copilot 没有抽出完整对象和目标，因此 Phase A 生成明确标记为工作理解的 `Ia型超新星 / 光变曲线研究`，不把它写成用户确认事实。

### planning

优先调用：

- `PlannerFacade`
- `RequirementAgentService`
- `ResearchPlanningV2Service`

当 v30 Planner readiness 不满足时，不返回 422 终止 Run，而是记录：

```text
planner_gate = needs_review
```

并生成 working plan。此 working plan 不取数、不生成数据行、不冻结医疗合同。

### discovering

调用：

- `SourceRegistryService`
- `DiscoveryFacade`
- `SourceSelectionService`
- 现有 `SourceBroker` matcher/selector

本阶段只产生来源候选、来源选择和假设覆盖率。保留 `fetched=false`、`integrated=false`、`coverage_claimed=false`。

### structuring

调用：

- `SchemaPackGenerator`
- `SchemaMatcherBridge`

本阶段只生成字段契约和字段映射，不生成数据行。

医疗任务仍绑定 `configs/canonical_schema.yaml`，没有修改冻结 schema。

### linking

调用：

- `GraphService.project`

输出：

- Evidence Graph projection。
- Source Lineage draft。

Graph 继续遵守现有禁止患者跨研究 Join、禁止复制事实值的约束。

### quality_review

本阶段只执行真实存在的 preview 检查：

- schema pack 是否存在。
- mapping 是否存在。
- graph 是否存在。
- 是否发生取数或整合。
- 是否生成数据行。

不会把 Phase A 的对象检查冒充为真实 Quality Gate 通过。

### completed_preview

写入：

- `preview_only=true`
- `dataset_generated=false`
- `asset_refs=[]`

不会产生真实 CSV、真实下载血缘或观测记录。

## 7. 风险确认规则

新增 `RiskPolicy`，默认只在高风险情形暂停：

- HER2 IHC 2+ 语义。
- ERBB2 CNA / amplification 与 HER2 IHC 维度混淆。
- 跨研究患者或样本 Join。
- 低置信度患者/样本关联。
- 高权威来源冲突。
- 不可逆执行、直接发布或直接写入主表。

上述情况会产生：

- `risk_raised`
- `confirmation_required`
- Run 状态 `waiting_for_confirmation`

以下情况不会单独阻塞 Run：

- 目标字段暂时缺少。
- 普通科研问题未回答 Copilot clarification。
- Ia 型超新星问题没有指定所有分析细节。

这些情况使用 working hypothesis 和 `needs_review` 记录，而不是要求用户逐步骤点击继续。

## 8. Ia 测试实际结果

测试问题：

```text
我想研究 Ia 型超新星光变曲线
```

实际结果：

- Run 状态：`completed`。
- 当前阶段：`completed_preview`。
- 阶段完成：`intake → planning → discovering → structuring → linking → quality_review → completed_preview`。
- Planner gate：`needs_review`。
- Discovery：正常调用现有 astronomy registry/discovery。
- `fetched=false`。
- `integrated=false`。
- `coverage_claimed=false`。
- Schema Pack：存在，`generates_data=false`。
- Graph：成功生成 Evidence Graph projection。
- Source Lineage：生成 draft，不声称已下载。
- `dataset_generated=false`。
- `asset_refs=[]`。

本阶段没有调用 astronomy adapter，没有接入 VizieR，也没有生成或伪造光变观测数据。

## 9. HER2 测试实际结果

测试问题：

```text
我想研究 HER2 阳性乳腺癌耐药机制
```

实际结果：

- Run 状态：`completed`。
- 当前阶段：`completed_preview`。
- 普通的“机制探索/疗效预测” clarification 没有阻塞整个 Run。
- Planner gate 被记录为 `needs_review`。
- 现有 oncology Registry、Discovery、Source Selection、冻结 schema、Matcher 和 Graph projection 正常复用。
- 没有执行患者级数据整合。
- 没有触碰 `canonical_schema.yaml`、`medical_rules.yaml`、`quality_rules.yaml`。

高风险对照测试：

```text
研究乳腺癌 HER2 IHC 2+ 的耐药机制
```

该问题在 intake 后进入 `waiting_for_confirmation`，没有继续执行 planning 及下游阶段，符合医学安全边界。

## 10. 并发隔离结果

并发启动：

- Run A：HER2 阳性乳腺癌耐药机制。
- Run B：Ia 型超新星光变曲线。

实际验证：

- 两个 Run 的 `run_id` 不同。
- 两个 Run 的 `session_id` 不同。
- A 的事件全部绑定 A 的 `run_id`。
- B 的事件全部绑定 B 的 `run_id`。
- A 的 question 不包含超新星上下文。
- B 的 question 不包含 HER2 上下文。
- 每个 stage handler 显式接收 `run_id` 和 `session_id`。
- 没有全局 current session。

## 11. 测试汇总

### Phase A 专项

`backend/tests/autonomous_run/test_phase_a.py`：13 项，全部通过。

覆盖：

1. 创建 Run。
2. 原始 question 保留。
3. 自动阶段推进。
4. 普通模糊问题不被普通 clarification 永久阻塞。
5. 高风险条件进入 waiting_for_confirmation。
6. 阶段失败停止下游伪执行。
7. 事件 sequence 正确。
8. 两个 Run 并发隔离。
9. pause。
10. cancel。
11. 不调用不存在的 astronomy adapter。
12. 不生成假 dataset。
13. 冻结配置保持存在且未被本阶段修改。

### v30 回归

现有 v30 测试：80 项，全部通过。

### 全量后端回归

`pytest -q backend/tests`：共收集 674 项测试，运行到 100%，没有失败。

完整回归覆盖既有适配器、API、检索、规划、Schema、Graph、Quality、医学安全和评测相关测试。

## 12. 已知限制

- Run Store 和 Event Store 当前是进程内内存实现，服务重启后 Run 不恢复。
- Phase A 没有 Research Project 持久化，因此 `research_id` 仍可为空。
- 没有 resume API。
- 没有生产级队列、重试策略、跨进程锁和任务恢复机制。
- Discovery 仍然遵守现有“候选/目录能力”边界，不等于真实来源下载。
- Astronomy registry 仍是 `catalog_only/planned`，没有真实 astronomy adapter。
- 没有生成 CSV、Metadata Asset、Quality Report Asset 或正式 Source Lineage Asset。
- Graph 是现有 projection，不替代 EvidenceBuilder，也不包含事实数据行。
- 当前 API 没有 SSE/WebSocket，前端未来可先通过轮询读取 snapshot/events。
- Phase A 未实现用户追问、修改方向和 Run 分支。

## 13. 是否满足进入 Phase B

满足进入 Phase B 的前置条件，但本次没有实现 Phase B。

已满足：

- 后端自主 Run 编排边界已经建立。
- 前端不再负责推进阶段的后端契约已经建立。
- Run/Event Store 已抽象。
- 风险驱动暂停已建立。
- v30 能力以 Python service/runtime 方式复用，没有 HTTP 调用自身 API。
- Ia 问题可以自动运行到诚实的 preview。
- HER2 医疗安全规则和冻结配置保持不变。
- 并发 Run 隔离和失败短路已验证。

Phase B 仍需单独完成并单独验收：

- 先验证真实 Ia 来源可访问性、字段和下载方式。
- 再实现最小 astronomy adapter。
- 生成真实观测级表和 provenance。
- 不得假设 VizieR 或其他来源一定可用。
- 不得把 Phase A 的 preview 结果升级为真实数据资产。

本阶段到此停止，不继续实现 Phase B。
