from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from backend.app.models import ApiModel, ResponseDomain, SearchPlan, SourceItem


class CIViCTableName(str, Enum):
    EVIDENCE_ITEMS = "evidence_items"
    MOLECULAR_PROFILES = "molecular_profiles"
    DISEASES = "diseases"
    GENES = "genes"
    VARIANTS = "variants"
    THERAPIES = "therapies"
    SOURCES = "sources"
    EVIDENCE_RELATIONS = "evidence_relations"


class CIViCEvidenceType(str, Enum):
    PREDICTIVE = "PREDICTIVE"
    DIAGNOSTIC = "DIAGNOSTIC"
    PROGNOSTIC = "PROGNOSTIC"
    PREDISPOSING = "PREDISPOSING"
    ONCOGENIC = "ONCOGENIC"
    FUNCTIONAL = "FUNCTIONAL"


class CIViCEvidenceLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class CIViCAdapterOptions(ApiModel):
    disease_name: str = Field(default="Breast Cancer", min_length=1, max_length=256)
    molecular_profile_name: str | None = Field(
        default=None, min_length=1, max_length=256
    )
    therapy_name: str | None = Field(default=None, min_length=1, max_length=256)
    evidence_type: CIViCEvidenceType | None = None
    evidence_level: CIViCEvidenceLevel | None = None
    max_evidence_items: int = Field(default=5, ge=1, le=25)
    max_rows_per_table: int = Field(default=10_000, ge=1, le=50_000)
    after_cursor: str | None = Field(default=None, min_length=1, max_length=4096)
    refresh_cache: bool = False

    @field_validator(
        "disease_name",
        "molecular_profile_name",
        "therapy_name",
        "after_cursor",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CIViCAdapterRequest(ApiModel):
    search_plan: SearchPlan
    options: CIViCAdapterOptions = Field(default_factory=CIViCAdapterOptions)


class CIViCRequestTrace(ApiModel):
    method: str
    url: str
    query: str
    variables: dict[str, Any]


class CIViCEvidenceRecord(ApiModel):
    civic_evidence_id: int = Field(ge=1)
    evidence_id: str
    name: str
    evidence_url: str
    status: str
    evidence_type: str
    evidence_level: str
    evidence_rating: int | None = Field(default=None, ge=1, le=5)
    evidence_direction: str
    significance: str
    disease_name: str
    molecular_profile_name: str
    therapy_names: list[str] = Field(default_factory=list)
    publication_citation: str | None = None
    publication_id: str | None = None
    raw_evidence: dict[str, Any]
    source_item: SourceItem


class CIViCRawTable(ApiModel):
    table_name: CIViCTableName
    raw_fields: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    upstream_row_count: int = Field(ge=0)
    truncated: bool


class CIViCAdapterResult(ApiModel):
    task_id: str
    adapter: str = "civic"
    response_domain: ResponseDomain = ResponseDomain.KNOWLEDGE_EVIDENCE
    disease_name: str
    status_filter: str = "ACCEPTED"
    total_count: int = Field(ge=0)
    next_cursor: str | None = None
    search_request: CIViCRequestTrace
    evidence_items: list[CIViCEvidenceRecord]
    tables: list[CIViCRawTable]
    source_items: list[SourceItem]
    cache_hit: bool
    queried_at: datetime
    notice: str
