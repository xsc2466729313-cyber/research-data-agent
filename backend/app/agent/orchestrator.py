from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestrationDecision:
    next_stage: str
    reason: str
    required_tools: tuple[str, ...]
    stop_condition: str


class ResearchOrchestrator:
    """Deterministic task router. It plans work but never mutates data or bypasses gates."""

    VERSION = "orchestrator-v1"

    def decide(self, *, question: str = "", contract_status: str | None = None, completed_stages: set[str] | None = None, missing_required_fields: list[str] | None = None, quality_gate: str | None = None) -> OrchestrationDecision:
        completed = completed_stages or set()
        missing = missing_required_fields or []
        if quality_gate in {"FAIL", "REJECT"}:
            return OrchestrationDecision("quality_review", "质量门未通过，先处理阻断项。", ("quality_agent",), "quality_gate == PASS")
        if not question.strip():
            return OrchestrationDecision("research_planning", "缺少科研问题，需要先形成 Research Contract。", ("research_agent",), "contract 已生成")
        if "literature_search" not in completed:
            return OrchestrationDecision("literature_search", "先用真实文献建立 Evidence Pack。", ("literature_engine",), "Evidence Pack 非空或明确记录缺失")
        if contract_status != "READY_FOR_SOURCE_PLANNING":
            return OrchestrationDecision("research_planning", "Research Contract 尚未通过 Evidence 门控。", ("research_agent",), "contract_status == READY_FOR_SOURCE_PLANNING")
        if "data_acquisition" not in completed:
            return OrchestrationDecision("data_acquisition", "按 Required 字段覆盖搜索并验证数据源。", ("data_agent",), "候选数据源已验证")
        if "integration" not in completed or missing:
            return OrchestrationDecision("integration", "仍有字段或实体需要语义整合。", ("integration_agent",), "无未决必需字段且身份冲突为零")
        return OrchestrationDecision("quality_review", "数据已获取并整合，进入最终科研质量审核。", ("quality_agent",), "quality_gate == PASS")
