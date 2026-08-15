from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    """Common strict API model configuration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BiomarkerStatus(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    EQUIVOCAL = "Equivocal"
    UNKNOWN = "Unknown"


class Her2Assay(str, Enum):
    IHC = "IHC"
    FISH = "FISH"
    ISH = "ISH"
    CISH = "CISH"
    SISH = "SISH"
    OTHER = "Other"
    UNKNOWN = "Unknown"


class MutationStatus(str, Enum):
    MUTATED = "Mutated"
    WILD_TYPE = "WildType"
    UNKNOWN = "Unknown"


class ResponseDomain(str, Enum):
    CLINICAL = "clinical"
    PRECLINICAL_CELL_LINE = "preclinical_cell_line"
    CLINICAL_TRIAL = "clinical_trial"
    KNOWLEDGE_EVIDENCE = "knowledge_evidence"


class SafetyGate(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class ResearchQuestion(ApiModel):
    question: str = Field(min_length=5, max_length=1000)


class ResearchSpec(ApiModel):
    task_id: str = Field(min_length=1)
    research_goal: str = Field(min_length=1)
    disease: str = Field(min_length=1)
    subtype: str | None = None
    genes: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    drugs: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    required_data_types: list[str] = Field(min_length=1)
    target_fields: list[str] = Field(default_factory=list)


class SearchPlanItem(ApiModel):
    source: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    priority: int = Field(ge=1)
    mode: str = "mock"


class SearchPlan(ApiModel):
    task_id: str = Field(min_length=1)
    plans: list[SearchPlanItem] = Field(min_length=1)


class CandidateSource(ApiModel):
    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    source_database: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    sample_count: int | None = Field(default=None, ge=0)
    has_treatment: bool
    has_response: bool
    public_access: bool
    relevance_score: float = Field(ge=0, le=1)
    url: str = Field(min_length=1)
    accession: str | None = None


class SourceItem(ApiModel):
    source_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    accession: str | None = None
    url: str = Field(min_length=1)
    file_type: str | None = None
    local_path: str | None = None
    checksum: str | None = None
    status: str = Field(min_length=1)


class CanonicalRecord(ApiModel):
    """Frozen fields from configs/canonical_schema.yaml v0.1."""

    study_id: str = Field(min_length=1)
    patient_id: str | None = None
    sample_id: str | None = None
    disease: str = Field(min_length=1)
    subtype: str | None = None
    stage: str | None = None
    er_status: BiomarkerStatus | None = None
    pr_status: BiomarkerStatus | None = None
    her2_status: BiomarkerStatus | None = None
    her2_assay: Her2Assay | None = None
    her2_raw_value: str | None = None
    gene: str | None = None
    variant: str | None = None
    mutation_status: MutationStatus | None = None
    drug: str | None = None
    treatment: str | None = None
    response_domain: ResponseDomain | None = None
    response_type: str | None = None
    response: str | None = None
    source_id: str = Field(min_length=1)
    raw_field: str = Field(min_length=1)
    raw_value: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def block_unsafe_her2_ihc_mapping(self) -> CanonicalRecord:
        raw_value = (self.her2_raw_value or self.raw_value).strip().replace(" ", "")
        if (
            self.her2_assay == Her2Assay.IHC
            and raw_value in {"2+", "IHC2+", "HER2IHC2+"}
            and self.her2_status == BiomarkerStatus.POSITIVE
        ):
            raise ValueError(
                "HER2 IHC 2+ cannot be automatically mapped to HER2 Positive; "
                "use Equivocal or route the record to review"
            )
        return self


class EvidenceCell(ApiModel):
    evidence_id: str = Field(min_length=1)
    patient_id: str | None = None
    sample_id: str | None = None
    field: str = Field(min_length=1)
    canonical_value: Any
    raw_field: str | None = None
    raw_value: Any
    source_id: str = Field(min_length=1)
    normalization_method: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: str = "unverified"


class QualityReport(ApiModel):
    task_id: str = Field(min_length=1)
    metrics: dict[str, Any]
    safety_gate: SafetyGate
    errors: list[Any] = Field(default_factory=list)
    repairs: list[Any] = Field(default_factory=list)


class MockPipelineResult(ApiModel):
    mode: str = "mock"
    notice: str
    research_spec: ResearchSpec
    search_plan: SearchPlan
    candidate_sources: list[CandidateSource]
    source_items: list[SourceItem]
    canonical_dataset: list[CanonicalRecord]
    evidence: list[EvidenceCell]
    quality_report: QualityReport

