# Research Agent V2 Phase C

本阶段完成升级方案中的 Research Agent V2 编排层：

```text
ResearchPlanningV2Request
→ EvidenceExtractorV2
→ QuestionGeneratorV2
→ VariableDesignerV2
→ StudyDesignPlannerV2
→ ResearchPlanningV2Response
```

## 已实现

- `StructuredExtractionV2`：PICO/PECO 风格的人群、干预、暴露、对照、结局、协变量、亚组、粒度和研究范式。
- `EvidencePackItemV2`：每条证据保留 `source_id`、真实 URL、`paper_id`、章节、`raw_field`、`raw_value`、原文摘录和确定性哈希 ID。
- `QuestionGeneratorV2`：复用既有 evidence-aware formulation 作为 baseline；有可核验论文时标记 `EVIDENCE_AGENT`，无论文时标记 `GENERIC_FALLBACK`。
- `VariableDesignerV2`：复用字段证据门控，Required 字段缺证据仍进入 unresolved/review，不自动补事实。
- `StudyDesignPlannerV2`：为 prediction、survival、association 输出不同的分层/防泄漏约束，并强制 `response_domain=clinical` 作为患者结局规划的默认边界。
- `ResearchAgentV2`：统一编排、版本和审计字段，记录输入论文数、Evidence 数、Qwen 调用次数和 runtime verification 状态。

## API

`POST /api/v2/research/plan` 保持原请求兼容，新增 `structured_extraction`、`evidence_pack`、`fallback_template_only`、`agent_version` 和 `audit`。

旧 `plan_legacy()` 仍保留，供回滚和消融实验使用；它不作为默认 API 路径。

## 验收边界

当前组件是可审计的确定性 Evidence 编排，不宣称已经调用 Qwen，也不把本地回归 fixture 当作科研 benchmark。真实 Qwen Structured Extraction、Data Agent runtime verification 和领域 Gold Set 评测仍是后续工作。

最近一次集成 smoke 产物：[REPORT.md](../evaluation/research_planning_v2/runs/20260828T104101Z_phase_c/REPORT.md)。该产物只检查契约字段、Evidence 来源和 fallback 边界，不给出准确率或 SDTI。

## 回滚

将 `ResearchPlanningV2Service.plan()` 改回 `plan_legacy()` 即可回到上一版 facade；新模块不修改冻结 Schema、医学规则或 SDTI 公式。
