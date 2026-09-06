# V3.1 Phase 0 API 快照

- 盘点日期：2026-09-05
- 对照提交：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 运行时代码版本字段：`2.2.0-qwen-agent`（见 `backend/app/main.py` 的 FastAPI `version`）
- 来源：只读核对 `backend/app/main.py` 与 `backend/app/v3_api.py`
- 用途：后续 `/api/v30/*` 只能新增，不得改变下表标记为冻结的行为

冻结含义：路径、方法、response 模型名与现有业务语义保持不变。Phase 1 及之后只允许在新前缀增加接口。

健康检查不冻结产品语义，但路径应保留。

| 方法 | 路径 | response 模型 / 返回 | 是否冻结 |
|---|---|---|---|
| GET | `/health` | `dict`：status / mode / version | 是（保留） |
| GET | `/api/agent/architecture` | `dict`：架构角色说明 | 是 |
| GET | `/api/agent/configuration` | `AgentConfigurationStatus` | 是 |
| POST | `/api/agent/qwen-sessions` | `QwenSessionStatus` | 是 |
| DELETE | `/api/agent/qwen-sessions/{session_id}` | 204 | 是 |
| GET | `/api/agent/giiisp-configuration` | `GiiispConfigurationStatus` | 是 |
| POST | `/api/agent/giiisp-configuration` | `GiiispConfigurationStatus` | 是 |
| POST | `/api/agent/api-check` | `ApiCheckResult` | 是 |
| POST | `/api/agent/tasks` | `AgentTaskResult` | 是 |
| GET | `/api/agent/tasks/latest` | `AgentTaskResult` | 是 |
| GET | `/api/agent/tasks/{task_id}` | `AgentTaskResult` | 是 |
| GET | `/api/agent/tasks/{task_id}/export/{file_format}` | 文件流（csv/parquet/xlsx/json/metadata/quality_report） | 是 |
| POST | `/api/research/task` | `ResearchTaskCreated` | 是 |
| GET | `/api/task/status/{task_id}` | `ResearchTaskStatus` | 是 |
| GET | `/api/task/spec/{task_id}` | `ResearchTaskSpec` | 是 |
| GET | `/api/task/report/{task_id}` | `QualityGateReport` | 是 |
| POST | `/api/v2/agent/closed-loop` | `ClosedLoopResponse` | 是 |
| GET | `/api/v2/agent/closed-loop/{loop_id}` | `ClosedLoopResponse` | 是 |
| GET | `/api/v2/agent/memory` | `dict`（闭环记忆） | 是 |

## `/api/research/*`

| 方法 | 路径 | response 模型 | 是否冻结 |
|---|---|---|---|
| POST | `/api/research/topics` | `ResearchTopic` | 是 |
| POST | `/api/research/topics/{topic_id}/literature-scan` | `LiteratureScanResponse` | 是 |
| GET | `/api/research/topics/{topic_id}/question-candidates` | `QuestionCandidateList` | 是 |
| POST | `/api/research/questions/{candidate_id}/select` | `ResearchContract` | 是 |
| GET | `/api/research/contracts/{contract_id}` | `ResearchContract` | 是 |
| POST | `/api/research/contracts/{contract_id}/freeze` | `ResearchContract` | 是 |
| POST | `/api/research/contracts/{contract_id}/source-plan` | `SourcePlanningResult` | 是 |
| GET | `/api/research/source-plans/{source_plan_id}` | `SourcePlanningResult` | 是 |
| POST | `/api/research/topics/{topic_id}/rag-index` | `RAGIndexReport` | 是 |
| POST | `/api/research/topics/{topic_id}/evidence-query` | `EvidenceQueryResponse` | 是 |
| GET | `/api/research/topics/{topic_id}/knowledge-graph` | `ScientificGraphSnapshot` | 是 |
| POST | `/api/research/topics/{topic_id}/rag-evaluate` | `RAGEvaluationResult` | 是 |

## `/api/v3/research/*` 与 v3 配套

| 方法 | 路径 | response 模型 / 返回 | 是否冻结 |
|---|---|---|---|
| POST | `/api/v3/research/clarify` | `ClarifyResponse` | 是 |
| POST | `/api/v3/research/contracts` | `FrozenResearchContract` | 是 |
| POST | `/api/v3/research/contracts/{contract_id}/freeze` | `FrozenResearchContract` | 是 |
| GET | `/api/v3/research/contracts/{contract_id}` | `FrozenResearchContract` | 是 |
| GET | `/api/v3/research/contracts/{contract_id}/queries` | `dict`（扩展检索式） | 是 |
| POST | `/api/v3/discovery/sources` | `dict`（集合覆盖选择） | 是 |
| POST | `/api/v3/parsing/run` | `ParseResult` | 是 |
| POST | `/api/v3/retrieval/search` | `RetrievalResponse` | 是 |
| POST | `/api/v3/critic/diagnose` | `CriticReport` | 是 |
| GET | `/api/v3/review` | `dict` | 是 |
| POST | `/api/v3/review` | `ReviewItem` | 是 |
| POST | `/api/v3/review/{review_id}/decision` | `ReviewItem` | 是 |
| GET | `/api/v3/evidence/field/{record_id}/{field}` | `FieldEvidenceResponse` | 是 |
| GET | `/api/v3/rules/publication-gates` | `dict` | 是 |

## `/api/adapters/*`

| 方法 | 路径 | response 模型 | 是否冻结 |
|---|---|---|---|
| POST | `/api/adapters/gdc` | `GDCAdapterResult` | 是 |
| POST | `/api/adapters/geo` | `GEOAdapterResult` | 是 |
| POST | `/api/adapters/cbioportal` | `CBioPortalAdapterResult` | 是 |
| POST | `/api/adapters/aact` | `AACTAdapterResult` | 是 |
| POST | `/api/adapters/civic` | `CIViCAdapterResult` | 是 |

DepMap 当前作为执行引擎工具存在，根路由未单独暴露 `/api/adapters/depmap`。后续不得为了 v30 删除上表五条官方 Adapter 入口。

## `/api/v2/schema` `/api/v2/entity` `/api/v2/quality`

| 方法 | 路径 | response 模型 | 是否冻结 |
|---|---|---|---|
| POST | `/api/v2/schema/match` | `SchemaMatcherV3Response` | 是 |
| POST | `/api/v2/schema/match-v2plus` | `SchemaMatcherV3Response` | 是 |
| POST | `/api/v2/entity/match` | `EntityMatcherV3Response` | 是 |
| POST | `/api/v2/entity/match-v2plus` | `EntityMatcherV3Response` | 是 |
| POST | `/api/v2/quality/review` | `QualityReviewResponse` | 是 |
| POST | `/api/v2/quality/detect` | `ErrorDetectionResult` | 是 |
| POST | `/api/v2/quality/candidates` | `RepairCandidateResult` | 是 |
| POST | `/api/v2/quality/apply` | `SafeApplyResult` | 是 |
| POST | `/api/v2/governance/decide` | `SafetyDecisionResult` | 是 |
| POST | `/api/v2/retrieval/search` | `RetrievalResponse` | 是 |
| POST | `/api/v2/research/plan` | `ResearchPlanningV2Response` | 是 |

## `/api/evaluation/*`

| 方法 | 路径 | response 模型 / 返回 | 是否冻结 |
|---|---|---|---|
| GET | `/api/evaluation/overview` | `EvaluationOverview` | 是 |
| GET | `/api/evaluation/goldset/templates` | `GoldSetTemplateInspection` | 是 |
| POST | `/api/evaluation/run` | `EvaluationResult` | 是 |
| POST | `/api/evaluation/official-run` | `EvaluationResult` | 是 |
| GET | `/api/evaluation/artifacts/{evaluation_id}/{artifact_name}` | 文件 | 是 |

## 其他核心入口（同样冻结行为）

| 方法 | 路径 | response 模型 | 是否冻结 |
|---|---|---|---|
| POST | `/api/integration/normalize` | `NormalizationIntegrationResult` | 是 |
| POST | `/api/tasks/mock` | `MockPipelineResult` | 是（legacy） |
| POST | `/api/tasks/mock/export/{file_format}` | 文件流 | 是（legacy） |
| POST | `/api/goldset/sources/verify` | `SourceVerificationResult` | 是 |
| POST | `/api/goldset/retrieval/initial-label` | `RetrievalInitialLabelResult` | 是 |
| POST | `/api/goldset/fields/initial-label` | `FieldInitialLabelResult` | 是 |
| POST | `/api/goldset/errors/construct` | `ErrorConstructionResult` | 是 |
| POST | `/api/goldset/reviews/retrieval` | `RetrievalReviewedDraft` | 是 |
| POST | `/api/goldset/reviews/field` | `FieldReviewedDraft` | 是 |
| POST | `/api/goldset/reviews/error` | `ErrorReviewedDraft` | 是 |
| POST | `/api/goldset/validate` | `GoldSetRuleValidationResult` | 是 |
| POST | `/api/repair/classify` | `ErrorClassificationResult` | 是 |
| POST | `/api/repair/run` | `RepairLoopResult` | 是 |

## 明确不存在（Phase 0 时点）

以下路径在当前代码中不存在。后续若实现，必须走新前缀，不能改写上表冻结路径：

- `/api/v30/*`
- `/api/v30/route`
- `/api/v30/copilot/turn`
- `/api/v30/sessions`
- `/api/v30/plan`

## 快照纪律

后续阶段对照本表时：

1. 冻结行不得改方法、路径或收窄现有字段。
2. 新增只能出现在 `/api/v30/*`。
3. 不得删除 Adapter / evaluation / quality 入口来“简化”升级。
