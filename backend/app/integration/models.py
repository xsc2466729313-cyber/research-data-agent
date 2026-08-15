from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from backend.app.models import ApiModel, CanonicalRecord, EvidenceCell, SourceItem
from backend.app.normalization.models import (
    FieldMapping,
    MappedCanonicalRecord,
    MappingIssue,
    RawSourceRecord,
)


class LinkScope(str, Enum):
    PATIENT = "patient"
    SAMPLE = "sample"


class LinkStatus(str, Enum):
    LINKED = "linked"
    LINKED_PATIENT_ONLY = "linked_patient_only"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class PatientSampleLinkCandidate(ApiModel):
    left_record_id: str = Field(min_length=1)
    right_record_id: str = Field(min_length=1)
    scope: LinkScope
    confidence: float = Field(ge=0, le=1)
    basis: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def prevent_self_link(self) -> PatientSampleLinkCandidate:
        if self.left_record_id == self.right_record_id:
            raise ValueError("a record cannot be linked to itself")
        return self


class LinkDecision(ApiModel):
    link_id: str
    left_record_id: str
    right_record_id: str
    scope: LinkScope
    confidence: float = Field(ge=0, le=1)
    method: str
    status: LinkStatus
    auto_merge_allowed: bool
    reason: str


class ConflictStatus(str, Enum):
    UNRESOLVED = "unresolved"


class FieldConflict(ApiModel):
    conflict_id: str
    entity_key: str
    semantic_key: str
    field: str
    dimension: str
    values: list[Any] = Field(min_length=2)
    evidence_ids: list[str] = Field(min_length=2)
    source_ids: list[str] = Field(min_length=1)
    high_authority_conflict: bool
    status: ConflictStatus = ConflictStatus.UNRESOLVED
    reason: str


class MergedField(ApiModel):
    semantic_key: str
    field: str
    dimension: str
    selected_value: Any = None
    observed_values: list[Any]
    evidence_ids: list[str]
    source_ids: list[str]
    status: str


class MergedRecord(ApiModel):
    entity_key: str
    raw_record_ids: list[str] = Field(min_length=1)
    study_id: str
    patient_id: str | None = None
    sample_id: str | None = None
    fields: list[MergedField]
    conflict_ids: list[str]
    status: str


class NormalizationIntegrationRequest(ApiModel):
    task_id: str = Field(min_length=1)
    source_items: list[SourceItem] = Field(min_length=1, max_length=500)
    records: list[RawSourceRecord] = Field(min_length=1, max_length=500)
    mappings: list[FieldMapping] = Field(min_length=1, max_length=500)
    link_candidates: list[PatientSampleLinkCandidate] = Field(
        default_factory=list, max_length=2_000
    )


class NormalizationIntegrationResult(ApiModel):
    task_id: str
    pipeline: str = "normalization_integration"
    canonical_records: list[CanonicalRecord]
    mapped_records: list[MappedCanonicalRecord]
    evidence: list[EvidenceCell]
    link_decisions: list[LinkDecision]
    conflicts: list[FieldConflict]
    merged_records: list[MergedRecord]
    mapping_issues: list[MappingIssue]
    blocked_record_ids: list[str]
    source_items: list[SourceItem]
    summary: dict[str, int]
    processed_at: datetime
    notice: str
