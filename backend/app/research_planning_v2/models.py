from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.app.literature.models import PaperRecord
from backend.app.models import ApiModel


class ResearchPlanningV2Request(ApiModel):
    topic: str = Field(min_length=2, max_length=2000)
    user_constraints: dict[str, Any] = Field(default_factory=dict)
    retrieved_papers: list[PaperRecord] = Field(default_factory=list, max_length=100)
    known_data_sources: list[str] = Field(default_factory=list, max_length=100)
    previous_contract: dict[str, Any] | None = None


class ResearchQuestionCandidateV2(ApiModel):
    candidate_id: str
    question: str
    research_type: str
    population: str
    exposure: str
    outcome: str
    rank: int = Field(ge=1)
    feasibility_score: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"]


class EvidencePackItemV2(ApiModel):
    """A source-backed evidence item used by the Research Agent.

    ``raw_value`` is kept separate from the normalized excerpt so callers can
    distinguish what the provider returned from what the agent displays.
    """

    evidence_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    section: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1200)
    raw_field: str = "paper.section"
    raw_value: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class StructuredExtractionV2(ApiModel):
    """PICO/PECO-like extraction with explicit provenance and uncertainty."""

    population: list[str] = Field(default_factory=list)
    intervention: list[str] = Field(default_factory=list)
    exposure: list[str] = Field(default_factory=list)
    comparator: list[str] = Field(default_factory=list)
    outcome: list[str] = Field(default_factory=list)
    covariates: list[str] = Field(default_factory=list)
    subgroups: list[str] = Field(default_factory=list)
    granularity: str = "patient_or_sample"
    research_type: str = "association"
    evidence_refs: list[str] = Field(default_factory=list)
    extraction_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK"]
    confidence: float = Field(ge=0, le=1)


class VariableSpecV2(ApiModel):
    field_id: str
    role: str
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    availability: Literal["supported", "missing", "operational_rule"]
    priority: Literal["required", "recommended", "optional"]


class ResearchPlanningV2Response(ApiModel):
    candidate_questions: list[ResearchQuestionCandidateV2]
    selected_question: ResearchQuestionCandidateV2 | None = None
    required_fields: list[VariableSpecV2] = Field(default_factory=list)
    recommended_fields: list[VariableSpecV2] = Field(default_factory=list)
    optional_fields: list[VariableSpecV2] = Field(default_factory=list)
    study_design: dict[str, Any]
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    question_generation_source: Literal["EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"]
    structured_extraction: StructuredExtractionV2 | None = None
    evidence_pack: list[EvidencePackItemV2] = Field(default_factory=list)
    fallback_template_only: bool = True
    agent_version: str = "research-agent-v2"
    audit: dict[str, Any] = Field(default_factory=dict)
    notice: str
