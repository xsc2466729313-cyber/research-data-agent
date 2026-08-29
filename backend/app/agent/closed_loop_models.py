from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from backend.app.agent.models import AgentTaskRequest, AgentTaskResult
from backend.app.models import ApiModel


class ClosedLoopRequest(ApiModel):
    """Input contract for an auditable, bounded self-correction run."""

    initial_request: AgentTaskRequest
    max_iterations: int = Field(default=3, ge=2, le=4)
    require_two_rounds: bool = True
    min_improvement: float = Field(default=0.01, ge=0, le=1)
    stop_on_no_improvement: bool = True


class ClosedLoopMetricSnapshot(ApiModel):
    iteration: int = Field(ge=1)
    progress_score: float = Field(ge=0, le=1)
    required_field_coverage: float = Field(ge=0, le=1)
    target_match_rate: float = Field(ge=0, le=1)
    traceability: float = Field(ge=0, le=1)
    unresolved_gap_count: int = Field(ge=0)
    review_burden: float = Field(ge=0, le=1)
    quality_gate: str
    publish_allowed: bool


class ClosedLoopDiagnosis(ApiModel):
    diagnosis_id: str
    label: str
    severity: str
    evidence: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    repair_kind: str = ""


class ClosedLoopAction(ApiModel):
    action_id: str
    action_type: str
    status: str
    rationale: str
    changed_request_fields: list[str] = Field(default_factory=list)
    strategy_ids: list[str] = Field(default_factory=list)


class ClosedLoopImprovement(ApiModel):
    from_iteration: int = Field(ge=1)
    to_iteration: int = Field(ge=1)
    score_delta: float
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    improved: bool
    summary: list[str] = Field(default_factory=list)


class ClosedLoopAudit(ApiModel):
    iteration: int = Field(ge=1)
    input_hash: str
    output_hash: str
    attempted_call_count: int = Field(ge=0)
    attempted_call_ids: list[str] = Field(default_factory=list)
    strategy_ids: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    created_at: datetime


class ClosedLoopIteration(ApiModel):
    iteration: int = Field(ge=1)
    input_request: AgentTaskRequest
    result: AgentTaskResult
    metrics: ClosedLoopMetricSnapshot
    diagnoses: list[ClosedLoopDiagnosis] = Field(default_factory=list)
    actions: list[ClosedLoopAction] = Field(default_factory=list)
    improvement: ClosedLoopImprovement | None = None
    audit: ClosedLoopAudit


class ClosedLoopHighlightCard(ApiModel):
    label: str
    value: str
    hint: str = ""
    tone: str = "neutral"


class ClosedLoopResponse(ApiModel):
    loop_id: str
    status: str
    completed_iterations: int = Field(ge=0)
    stop_reason: str
    iterations: list[ClosedLoopIteration] = Field(default_factory=list)
    final_result: AgentTaskResult | None = None
    improvement_summary: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    audit_notice: str
    improved: bool = False
    presentation: str = "best_only"
    best_iteration: int = Field(default=1, ge=1)
    user_notice: str = ""
    highlight_cards: list[ClosedLoopHighlightCard] = Field(default_factory=list)
    display_iterations: list[int] = Field(default_factory=list)
    attempted_repairs: list[str] = Field(default_factory=list)
