from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field, model_validator

from backend.app.models import ApiModel, SafetyGate


class EvaluationMode(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    GOLD_SET = "gold_set"


class EvaluationStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PARTIALLY_EVALUATED = "PARTIALLY_EVALUATED"
    EVALUATED = "EVALUATED"


class MetricStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    EVALUATED = "EVALUATED"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RetrievalLabel(str, Enum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GoldSetManifest(ApiModel):
    gold_set_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    frozen: bool
    frozen_at: datetime
    initial_labeler: str = Field(min_length=1, max_length=200)
    independent_reviewer: str = Field(min_length=1, max_length=200)
    deterministic_rules_verified: bool
    source_references_verified: bool
    high_risk_review_complete: bool
    human_reviewer: str | None = Field(default=None, min_length=1, max_length=200)
    gold_set_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_independent_review(self) -> GoldSetManifest:
        if self.initial_labeler.casefold() == self.independent_reviewer.casefold():
            raise ValueError("initial_labeler and independent_reviewer must differ")
        return self


class RetrievalGoldCase(ApiModel):
    question_id: str = Field(min_length=1, max_length=128)
    research_question: str = Field(min_length=1, max_length=2000)
    dataset_id: str = Field(min_length=1, max_length=256)
    label: RetrievalLabel
    label_source: str = Field(min_length=1, max_length=500)
    review_status: ReviewStatus
    notes: str = Field(default="", max_length=2000)


class FieldGoldCase(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    source_dataset: str = Field(min_length=1, max_length=256)
    raw_field: str = Field(min_length=1, max_length=256)
    raw_value: str = Field(max_length=5000)
    canonical_field: str = Field(min_length=1, max_length=256)
    canonical_value: str = Field(min_length=1, max_length=5000)
    allowed_auto_transform: bool
    label_source: str = Field(min_length=1, max_length=500)
    review_status: ReviewStatus
    notes: str = Field(default="", max_length=2000)


class ErrorGoldCase(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    error_type: str = Field(min_length=1, max_length=256)
    original_record: str = Field(min_length=1, max_length=20_000)
    expected_detection: bool
    expected_repair: str | None = Field(default=None, max_length=20_000)
    auto_repair_allowed: bool
    risk_level: RiskLevel
    review_status: ReviewStatus
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_repair_expectation(self) -> ErrorGoldCase:
        if self.auto_repair_allowed and not self.expected_detection:
            raise ValueError("a clean control cannot allow automatic repair")
        if self.auto_repair_allowed and self.expected_repair is None:
            raise ValueError("allowed automatic repair requires expected_repair")
        if self.risk_level == RiskLevel.HIGH and self.auto_repair_allowed:
            raise ValueError("high-risk cases cannot allow automatic repair")
        return self


class GoldSetBundle(ApiModel):
    manifest: GoldSetManifest
    retrieval_gold: list[RetrievalGoldCase] = Field(default_factory=list, max_length=20_000)
    field_gold: list[FieldGoldCase] = Field(default_factory=list, max_length=20_000)
    error_gold: list[ErrorGoldCase] = Field(default_factory=list, max_length=20_000)


class RetrievalObservation(ApiModel):
    question_id: str = Field(min_length=1, max_length=128)
    dataset_id: str = Field(min_length=1, max_length=256)
    retrieved: bool


class FieldObservation(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    canonical_field: str = Field(min_length=1, max_length=256)
    canonical_value: str = Field(min_length=1, max_length=5000)
    evidence_complete_valid: bool


class ErrorObservation(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    detected: bool
    auto_repair_executed: bool = False
    repaired_value: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def require_repaired_value(self) -> ErrorObservation:
        if self.auto_repair_executed and self.repaired_value is None:
            raise ValueError("executed automatic repair requires repaired_value")
        if not self.auto_repair_executed and self.repaired_value is not None:
            raise ValueError("repaired_value requires auto_repair_executed=true")
        return self


class BenchmarkObservations(ApiModel):
    retrieval: list[RetrievalObservation] = Field(default_factory=list, max_length=20_000)
    fields: list[FieldObservation] = Field(default_factory=list, max_length=20_000)
    errors: list[ErrorObservation] = Field(default_factory=list, max_length=20_000)


class SourceValidationSummary(ApiModel):
    checked_source_count: int = Field(ge=0)
    fake_source_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> SourceValidationSummary:
        if self.fake_source_count > self.checked_source_count:
            raise ValueError("fake_source_count cannot exceed checked_source_count")
        return self


class EvaluationRequest(ApiModel):
    evaluation_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    mode: EvaluationMode = EvaluationMode.NOT_EVALUATED
    gold_set: GoldSetBundle | None = None
    observations: BenchmarkObservations | None = None
    source_validation: SourceValidationSummary | None = None
    unresolved_high_risk_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_mode_inputs(self) -> EvaluationRequest:
        if self.mode == EvaluationMode.NOT_EVALUATED:
            if self.gold_set is not None or self.observations is not None:
                raise ValueError(
                    "not_evaluated mode cannot accept Gold Set data or observations"
                )
            if self.source_validation is not None or self.unresolved_high_risk_count:
                raise ValueError(
                    "not_evaluated mode cannot accept benchmark safety results"
                )
        elif self.gold_set is None or self.observations is None:
            raise ValueError("gold_set mode requires gold_set and observations")
        return self


class ConfusionCounts(ApiModel):
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)


class EvaluationCounts(ApiModel):
    retrieval: ConfusionCounts
    faithful_fields: int = Field(ge=0)
    sampled_critical_fields: int = Field(ge=0)
    traceable_fields: int = Field(ge=0)
    key_nonempty_fields: int = Field(ge=0)
    errors: ConfusionCounts
    correct_repairs: int = Field(ge=0)
    automatic_repairs: int = Field(ge=0)


class MetricResult(ApiModel):
    value: float | None = Field(default=None, ge=0, le=100)
    status: MetricStatus
    formula: str = Field(min_length=1)
    numerator: float | None = Field(default=None, ge=0)
    denominator: float | None = Field(default=None, ge=0)
    target: float | None = Field(default=None, ge=0, le=100)
    target_met: bool | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def keep_status_consistent(self) -> MetricResult:
        if self.status == MetricStatus.NOT_EVALUATED and self.value is not None:
            raise ValueError("NOT_EVALUATED metric cannot contain a value")
        if self.status == MetricStatus.EVALUATED and self.value is None:
            raise ValueError("EVALUATED metric must contain a value")
        return self


class EvaluationMetrics(ApiModel):
    retrieval_precision: MetricResult
    retrieval_recall: MetricResult
    retrieval_f1: MetricResult
    faithfulness: MetricResult
    traceability: MetricResult
    error_precision: MetricResult
    error_recall: MetricResult
    error_f1: MetricResult
    repair_accuracy: MetricResult
    sdti: MetricResult


class EvaluationSafety(ApiModel):
    gate: SafetyGate
    publish_allowed: bool
    fake_source_rate: MetricResult
    redlines: list[str] = Field(default_factory=list)
    publication_blockers: list[str] = Field(default_factory=list)


class ArtifactReference(ApiModel):
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    url: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GoldSetSummary(ApiModel):
    gold_set_id: str
    version: str
    checksum: str
    retrieval_case_count: int = Field(ge=0)
    field_case_count: int = Field(ge=0)
    error_case_count: int = Field(ge=0)


class EvaluationResult(ApiModel):
    evaluation_id: str
    evaluation_status: EvaluationStatus
    gold_set: GoldSetSummary | None = None
    counts: EvaluationCounts | None = None
    metrics: EvaluationMetrics
    safety: EvaluationSafety
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    notice: str


class GoldSetTemplateInspection(ApiModel):
    status: EvaluationStatus
    directory: str
    required_headers: dict[str, list[str]]
    row_counts: dict[str, int]
    notice: str
