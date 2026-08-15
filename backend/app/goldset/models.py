from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from backend.app.evaluation.models import (
    ErrorGoldCase,
    FieldGoldCase,
    RetrievalGoldCase,
    RetrievalLabel,
    RiskLevel,
)
from backend.app.models import ApiModel


class SourceDatabase(str, Enum):
    GDC = "gdc"
    GEO = "geo"
    CBIOPORTAL = "cbioportal"
    AACT = "aact"
    CIVIC = "civic"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"


class CurationKind(str, Enum):
    RETRIEVAL = "retrieval"
    FIELD = "field"
    ERROR = "error"


class CurationStatus(str, Enum):
    INITIAL_LABELED = "initial_labeled"
    SECOND_REVIEWED = "second_reviewed"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    RULE_VALIDATED = "rule_validated"


class ReviewPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewQueueStatus(str, Enum):
    OPEN = "open"


class FindingSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ErrorCaseType(str, Enum):
    DUPLICATE = "duplicate"
    MISSING = "missing"
    GENE_ALIAS = "gene_alias"
    DRUG_ALIAS = "drug_alias"
    SCHEMA_MAPPING_ERROR = "schema_mapping_error"
    HER2_ASSAY_ERROR = "her2_assay_error"
    PROVENANCE_MISSING = "provenance_missing"
    PATIENT_SAMPLE_CONFLICT = "patient_sample_conflict"


class SourceReference(ApiModel):
    source_id: str = Field(min_length=1, max_length=256)
    source_database: SourceDatabase
    accession: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2000)


class SourceVerificationResult(ApiModel):
    verification_id: str = Field(min_length=1)
    source: SourceReference
    status: VerificationStatus
    method: str = "live_official_http_v1"
    checked_at: datetime
    checked_url: str | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_truncated: bool = False
    reason: str


class ReviewQueueItem(ApiModel):
    queue_id: str = Field(min_length=1)
    kind: CurationKind
    case_id: str = Field(min_length=1)
    priority: ReviewPriority
    reasons: list[str] = Field(min_length=1)
    source_id: str = Field(min_length=1)
    required_action: str = "human_review"
    status: ReviewQueueStatus = ReviewQueueStatus.OPEN


class RetrievalLabelProposal(ApiModel):
    question_id: str = Field(min_length=1, max_length=128)
    research_question: str = Field(min_length=5, max_length=2000)
    source: SourceReference
    proposed_label: RetrievalLabel
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class RetrievalInitialLabelRequest(ApiModel):
    model_id: str = Field(min_length=1, max_length=200)
    proposals: list[RetrievalLabelProposal] = Field(min_length=1, max_length=500)


class RetrievalDraft(ApiModel):
    draft_id: str
    primary_model_id: str
    question_id: str
    research_question: str
    dataset_id: str
    proposed_label: RetrievalLabel
    confidence: float = Field(ge=0, le=1)
    rationale: str
    source_verification: SourceVerificationResult
    status: CurationStatus


class RetrievalInitialLabelResult(ApiModel):
    drafts: list[RetrievalDraft]
    review_queue: list[ReviewQueueItem]
    notice: str


class FieldLabelProposal(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    source: SourceReference
    raw_field: str = Field(min_length=1, max_length=256)
    raw_value: str = Field(max_length=5000)
    proposed_canonical_field: str = Field(min_length=1, max_length=256)
    proposed_canonical_value: str = Field(min_length=1, max_length=5000)
    allowed_auto_transform: bool
    companion_fields: dict[str, str] = Field(default_factory=dict, max_length=50)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class FieldInitialLabelRequest(ApiModel):
    model_id: str = Field(min_length=1, max_length=200)
    proposals: list[FieldLabelProposal] = Field(min_length=1, max_length=500)


class FieldDraft(ApiModel):
    draft_id: str
    primary_model_id: str
    case_id: str
    source_dataset: str
    raw_field: str
    raw_value: str
    proposed_canonical_field: str
    proposed_canonical_value: str
    allowed_auto_transform: bool
    companion_fields: dict[str, str]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    source_verification: SourceVerificationResult
    status: CurationStatus


class FieldInitialLabelResult(ApiModel):
    drafts: list[FieldDraft]
    review_queue: list[ReviewQueueItem]
    notice: str


class ErrorSeed(ApiModel):
    record_id: str = Field(min_length=1, max_length=128)
    source: SourceReference
    record: dict[str, Any] = Field(min_length=1, max_length=200)
    requested_error_types: list[ErrorCaseType] = Field(
        default_factory=lambda: list(ErrorCaseType),
        min_length=1,
    )

    @model_validator(mode="after")
    def unique_error_types(self) -> ErrorSeed:
        self.requested_error_types = list(dict.fromkeys(self.requested_error_types))
        if self.record.get("source_id") != self.source.source_id:
            raise ValueError(
                "error seed record.source_id must match its verified source reference"
            )
        return self


class ErrorConstructionRequest(ApiModel):
    seeds: list[ErrorSeed] = Field(min_length=1, max_length=100)


class ErrorDraft(ApiModel):
    draft_id: str
    primary_actor_id: str = "deterministic-error-constructor-v1"
    seed_record_id: str
    error_type: str
    original_record: str
    expected_detection: bool
    expected_repair: str | None = None
    auto_repair_allowed: bool
    risk_level: RiskLevel
    mutation_description: str
    source_verification: SourceVerificationResult
    status: CurationStatus


class ErrorConstructionResult(ApiModel):
    drafts: list[ErrorDraft]
    skipped_mutations: list[str]
    review_queue: list[ReviewQueueItem]
    notice: str


class RetrievalSecondReviewRequest(ApiModel):
    draft: RetrievalDraft
    reviewer_model_id: str = Field(min_length=1, max_length=200)
    reviewed_label: RetrievalLabel
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class RetrievalReviewedDraft(ApiModel):
    draft: RetrievalDraft
    reviewer_model_id: str
    reviewed_label: RetrievalLabel
    confidence: float = Field(ge=0, le=1)
    rationale: str
    agreement: bool
    status: CurationStatus


class FieldSecondReviewRequest(ApiModel):
    draft: FieldDraft
    reviewer_model_id: str = Field(min_length=1, max_length=200)
    reviewed_canonical_field: str = Field(min_length=1, max_length=256)
    reviewed_canonical_value: str = Field(min_length=1, max_length=5000)
    preserves_medical_meaning: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class FieldReviewedDraft(ApiModel):
    draft: FieldDraft
    reviewer_model_id: str
    reviewed_canonical_field: str
    reviewed_canonical_value: str
    preserves_medical_meaning: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str
    agreement: bool
    status: CurationStatus


class ErrorSecondReviewRequest(ApiModel):
    draft: ErrorDraft
    reviewer_model_id: str = Field(min_length=1, max_length=200)
    reviewed_error_type: str = Field(min_length=1, max_length=256)
    reviewed_expected_detection: bool
    reviewed_expected_repair: str | None = Field(default=None, max_length=20_000)
    reviewed_auto_repair_allowed: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class ErrorReviewedDraft(ApiModel):
    draft: ErrorDraft
    reviewer_model_id: str
    reviewed_error_type: str
    reviewed_expected_detection: bool
    reviewed_expected_repair: str | None = None
    reviewed_auto_repair_allowed: bool
    confidence: float = Field(ge=0, le=1)
    rationale: str
    agreement: bool
    status: CurationStatus


class RuleFinding(ApiModel):
    rule_id: str = Field(min_length=1)
    kind: CurationKind
    case_id: str = Field(min_length=1)
    severity: FindingSeverity
    passed: bool
    message: str = Field(min_length=1)


class GoldSetRuleValidationRequest(ApiModel):
    retrieval: list[RetrievalReviewedDraft] = Field(default_factory=list, max_length=1000)
    fields: list[FieldReviewedDraft] = Field(default_factory=list, max_length=1000)
    errors: list[ErrorReviewedDraft] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def require_cases(self) -> GoldSetRuleValidationRequest:
        if not (self.retrieval or self.fields or self.errors):
            raise ValueError("at least one reviewed Gold Set draft is required")
        return self


class GoldSetRuleValidationResult(ApiModel):
    retrieval_gold: list[RetrievalGoldCase]
    field_gold: list[FieldGoldCase]
    error_gold: list[ErrorGoldCase]
    findings: list[RuleFinding]
    review_queue: list[ReviewQueueItem]
    summary: dict[str, int | bool]
    freeze_eligible: bool
    notice: str
