from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from backend.app.evaluation.models import RiskLevel
from backend.app.models import ApiModel, SafetyGate
from backend.app.normalization.models import SourceAuthority


class QualityRecord(ApiModel):
    record_id: str = Field(min_length=1, max_length=512)
    record: dict[str, Any] = Field(min_length=1, max_length=200)
    source_authority: SourceAuthority = SourceAuthority.STANDARD


class DetectionRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendedAction(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class DetectedError(ApiModel):
    finding_id: str = Field(min_length=1)
    record_ids: list[str] = Field(min_length=1)
    field: str | None = None
    error_type: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    detection_confidence: float = Field(ge=0, le=1)
    risk_level: DetectionRisk
    severity: str = Field(min_length=1)
    deterministic: bool
    observed_value: Any = None
    candidate_repair: dict[str, Any] | None = None
    evidence: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
    message: str = Field(min_length=1)


class ErrorDetectionResult(ApiModel):
    task_id: str = Field(min_length=1)
    detector_version: str = Field(min_length=1)
    findings: list[DetectedError]
    checked_record_count: int = Field(ge=0)
    summary: dict[str, int | float | str | bool]
    detected_at: datetime


class RepairCandidate(ApiModel):
    candidate_id: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    error_type: str = Field(default="unknown", min_length=1)
    record_id: str = Field(min_length=1)
    field: str | None = None
    operation: str = Field(pattern=r"^(replace|quarantine)$")
    proposed_value: Any = None
    expected_value: Any = None
    confidence: float = Field(ge=0, le=1)
    risk_level: DetectionRisk
    safe_to_apply: bool
    requires_review: bool
    basis: list[str] = Field(min_length=1)
    preserves_provenance: bool
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def validate_safety(self) -> "RepairCandidate":
        if self.safe_to_apply and self.requires_review:
            raise ValueError("a safe candidate cannot simultaneously require review")
        if not self.safe_to_apply and not self.requires_review and not self.blocked_reason:
            raise ValueError("unsafe candidates need review or a blocked reason")
        if self.operation == "replace" and self.field is None:
            raise ValueError("replace candidates require a field")
        return self


class RepairCandidateResult(ApiModel):
    task_id: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    candidates: list[RepairCandidate]
    summary: dict[str, int | float | str | bool]
    generated_at: datetime


class AppliedChange(ApiModel):
    candidate_id: str
    record_id: str
    field: str | None = None
    operation: str
    before: Any = None
    after: Any = None
    status: str = Field(pattern=r"^(APPLIED|SKIPPED|BLOCKED)$")
    reason: str | None = None


class SafeApplyResult(ApiModel):
    task_id: str = Field(min_length=1)
    applier_version: str = Field(min_length=1)
    records: list[QualityRecord]
    changes: list[AppliedChange]
    applied_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    quarantined_record_ids: list[str] = Field(default_factory=list)
    post_detection: ErrorDetectionResult
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_at: datetime


class GateStatus(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class HardGate(ApiModel):
    gate_id: str
    status: GateStatus
    passed: bool
    evidence: str
    affected_record_ids: list[str] = Field(default_factory=list)


class SoftIndicators(ApiModel):
    sample_size: int = Field(ge=0)
    missingness_rate: float = Field(ge=0, le=1)
    recommended_field_coverage: float = Field(ge=0, le=1)
    source_authority_score: float = Field(ge=0, le=1)
    traceability_rate: float = Field(ge=0, le=1)
    review_burden: float = Field(ge=0, le=1)


class ReadinessReport(ApiModel):
    task_id: str
    status: str = Field(pattern=r"^(READY|READY_WITH_REVIEW|NOT_READY)$")
    publish_allowed: bool
    hard_gates: list[HardGate] = Field(min_length=6)
    soft_indicators: SoftIndicators
    reviewed_record_count: int = Field(ge=0)
    blocking_finding_count: int = Field(ge=0)
    review_finding_count: int = Field(ge=0)
    rationale: list[str] = Field(min_length=1)
    readiness_version: str
    evaluated_at: datetime


class ReviewQueueItem(ApiModel):
    review_id: str
    record_ids: list[str] = Field(min_length=1)
    finding_id: str | None = None
    candidate_id: str | None = None
    priority: str = Field(pattern=r"^(HIGH|MEDIUM|LOW)$")
    reason: str = Field(min_length=1)
    required_action: str = Field(min_length=1)
    status: str = Field(default="PENDING", pattern=r"^(PENDING|APPROVED|REJECTED)$")


class QualityReviewRequest(ApiModel):
    task_id: str = Field(min_length=1, max_length=512)
    records: list[QualityRecord] = Field(min_length=1, max_length=500)
    required_fields: list[str] = Field(default_factory=list)
    recommended_fields: list[str] = Field(default_factory=list)
    granularity: str | None = None


class QualityApplyRequest(ApiModel):
    task_id: str = Field(min_length=1, max_length=512)
    records: list[QualityRecord] = Field(min_length=1, max_length=500)
    candidates: RepairCandidateResult | list[RepairCandidate]


class QualityReviewResponse(ApiModel):
    task_id: str
    detection: ErrorDetectionResult
    candidates: RepairCandidateResult
    applied: SafeApplyResult
    readiness: ReadinessReport
    review_queue: list[ReviewQueueItem]
    safety_gate: SafetyGate
    notice: str
