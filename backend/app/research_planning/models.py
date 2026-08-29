from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from backend.app.literature.models import LiteratureScan
from backend.app.models import ApiModel


class FieldPriority(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class TopicCreateRequest(ApiModel):
    topic: str = Field(min_length=2, max_length=1000)
    domain_hint: str | None = Field(default=None, min_length=2, max_length=100)


class ResearchTopic(ApiModel):
    topic_id: str
    topic: str
    domain: str
    disease: str | None = None
    known_population: str | None = None
    known_exposure: str | None = None
    known_outcome: str | None = None
    known_data_granularity: str | None = None
    ambiguity_level: Literal["low", "medium", "high"]
    missing_dimensions: list[str] = Field(default_factory=list)
    created_at: datetime


class EvidenceReference(ApiModel):
    paper_id: str
    source_id: str
    provider: str
    section: str
    evidence_type: str
    source_url: str
    text: str = Field(min_length=1, max_length=600)
    confidence: float = Field(ge=0, le=1)


class FieldRequirement(ApiModel):
    field_id: str
    canonical_name: str
    label: str
    role: str
    priority: FieldPriority
    aliases: list[str] = Field(default_factory=list)
    granularity: str
    data_type: str
    reason: str
    source_hints: list[str] = Field(default_factory=list)
    literature_evidence: list[EvidenceReference] = Field(default_factory=list)
    evidence_status: Literal["supported", "missing", "operational_rule"] = "missing"
    review_required: bool = False


class MetricRequirement(ApiModel):
    metric_id: str
    label: str
    role: Literal["primary", "supporting", "diagnostic"]
    reason: str
    literature_evidence: list[EvidenceReference] = Field(default_factory=list)


class FeasibilityComponents(ApiModel):
    evidence_strength: float = Field(ge=0, le=1)
    data_availability: float = Field(ge=0, le=1)
    field_coverage: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    traceability: float = Field(ge=0, le=1)


class QuestionCandidate(ApiModel):
    candidate_id: str
    topic_id: str
    question: str
    research_type: str
    population: str
    exposure: str
    outcome: str
    field_hints: list[str] = Field(default_factory=list)
    feasibility: FeasibilityComponents
    feasibility_score: float = Field(ge=0, le=1)
    score_status: Literal["provisional"] = "provisional"
    score_basis: list[str] = Field(default_factory=list)
    literature_evidence: list[EvidenceReference] = Field(default_factory=list)
    recommendation_reason: str
    rank: int = Field(ge=1)
    generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"] = "GENERIC_FALLBACK"
    perspectives: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class QuestionCandidateList(ApiModel):
    topic_id: str
    candidates: list[QuestionCandidate]
    literature_warning: str | None = None


class LiteratureScanResponse(ApiModel):
    scan: LiteratureScan
    candidate_count: int = Field(ge=0)


class QuestionSelectionRequest(ApiModel):
    question_override: str | None = Field(default=None, min_length=5, max_length=2000)
    population_override: str | None = Field(default=None, min_length=2, max_length=500)
    exposure_override: str | None = Field(default=None, min_length=2, max_length=500)
    outcome_override: str | None = Field(default=None, min_length=2, max_length=500)


class ResearchContract(ApiModel):
    contract_id: str
    contract_version: str = "1.0"
    topic_id: str
    candidate_id: str
    topic: str
    research_question: str
    research_type: str
    population: str
    exposure: str
    outcome: str
    required_fields: list[FieldRequirement]
    recommended_fields: list[FieldRequirement] = Field(default_factory=list)
    optional_fields: list[FieldRequirement] = Field(default_factory=list)
    analysis_plan: list[str] = Field(default_factory=list)
    metric_requirements: list[MetricRequirement] = Field(default_factory=list)
    literature_evidence: list[EvidenceReference] = Field(default_factory=list)
    validation_status: Literal[
        "READY_FOR_SOURCE_PLANNING",
        "NEEDS_EVIDENCE",
        "NEEDS_REVIEW",
    ]
    validation_warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    lifecycle_status: Literal["DRAFT", "USER_CONFIRMED", "FROZEN"] = "DRAFT"
    data_granularity: Literal["patient", "sample", "cell_line", "trial", "publication"] = "patient"
    response_domain: Literal["clinical", "preclinical", "none"] = "clinical"
    prohibited_operations: list[str] = Field(
        default_factory=lambda: [
            "cross_cohort_patient_join_without_crosswalk",
            "treat_preclinical_response_as_clinical",
            "auto_merge_low_confidence_identity",
            "map_her2_ihc_2plus_to_positive",
            "equate_erbb2_cna_with_her2_ihc",
        ]
    )
    frozen_at: datetime | None = None
