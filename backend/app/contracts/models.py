from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from backend.app.models import ApiModel


DataGranularity = Literal["patient", "sample", "cell_line", "trial", "publication"]
ResponseDomain = Literal["clinical", "preclinical", "none"]
ContractLifecycle = Literal["DRAFT", "USER_CONFIRMED", "FROZEN"]
FieldPriorityName = Literal["required", "recommended", "optional"]


class PopulationSpec(ApiModel):
    disease: str
    subtype: str | None = None
    treatment_context: str | None = None
    notes: str | None = None


class VariableSpec(ApiModel):
    name: str
    canonical_field: str | None = None
    description: str | None = None
    evidence_count: int = Field(default=0, ge=0)


class ContractFieldRequirement(ApiModel):
    field_id: str
    label: str
    canonical_name: str
    role: str
    priority: FieldPriorityName
    reason: str
    evidence_status: Literal["supported", "missing", "operational_rule"] = "missing"
    aliases: list[str] = Field(default_factory=list)


class FrozenResearchContract(ApiModel):
    """Production Research Contract. Agent plans against this frozen demand."""

    contract_id: str
    topic_id: str | None = None
    candidate_id: str | None = None
    research_goal: str
    population: PopulationSpec
    exposure: VariableSpec | None = None
    outcome: VariableSpec | None = None
    required_fields: list[ContractFieldRequirement] = Field(default_factory=list)
    recommended_fields: list[ContractFieldRequirement] = Field(default_factory=list)
    optional_fields: list[ContractFieldRequirement] = Field(default_factory=list)
    data_granularity: DataGranularity = "patient"
    treatment_context: str | None = None
    response_domain: ResponseDomain = "clinical"
    allowed_source_types: list[str] = Field(default_factory=lambda: ["structured_database", "geo_series", "publication"])
    prohibited_operations: list[str] = Field(
        default_factory=lambda: [
            "cross_cohort_patient_join_without_crosswalk",
            "treat_preclinical_response_as_clinical",
            "auto_merge_low_confidence_identity",
            "map_her2_ihc_2plus_to_positive",
            "equate_erbb2_cna_with_her2_ihc",
        ]
    )
    provenance_required: bool = True
    human_review_required_for: list[str] = Field(
        default_factory=lambda: ["patient_identity", "her2_ambiguity", "clinical_outcome_inference"]
    )
    unresolved_questions: list[str] = Field(default_factory=list)
    literature_evidence_count: int = Field(default=0, ge=0)
    generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"] = "GENERIC_FALLBACK"
    status: ContractLifecycle = "DRAFT"
    frozen_at: datetime | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


class ClarifyRequest(ApiModel):
    topic: str = Field(min_length=2, max_length=2000)
    max_papers: int = Field(default=8, ge=0, le=20)


class PerspectivePrompt(ApiModel):
    perspective: Literal["clinical", "molecular", "treatment", "outcome", "data", "methodology"]
    prompt: str


class RequirementCandidate(ApiModel):
    candidate_id: str
    question: str
    research_type: str
    population: str
    exposure: str
    outcome: str
    required_field_hints: list[str] = Field(default_factory=list)
    perspectives: list[str] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)
    data_availability: str
    unresolved_questions: list[str] = Field(default_factory=list)
    generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"]
    feasibility_score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)


class ClarifyResponse(ApiModel):
    topic_id: str
    topic: str
    perspectives: list[PerspectivePrompt]
    candidates: list[RequirementCandidate]
    literature_warning: str | None = None
    paper_count: int = Field(ge=0)
    generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"]
    notice: str


class ContractCreateRequest(ApiModel):
    topic_id: str
    candidate_id: str
    question_override: str | None = Field(default=None, min_length=5, max_length=2000)


class ContractFreezeRequest(ApiModel):
    confirmed: bool = True
