from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from backend.app.models import ApiModel, SearchPlan, SourceItem


class CBioPortalTableType(str, Enum):
    CLINICAL_SAMPLE = "clinical_sample"
    CLINICAL_PATIENT = "clinical_patient"
    MUTATIONS = "mutations"
    DISCRETE_CNA = "discrete_cna"


class CBioPortalCNAEventType(str, Enum):
    ALL = "ALL"
    HOMDEL_AND_AMP = "HOMDEL_AND_AMP"
    HOMDEL = "HOMDEL"
    AMP = "AMP"
    GAIN = "GAIN"
    HETLOSS = "HETLOSS"
    DIPLOID = "DIPLOID"


class CBioPortalAdapterOptions(ApiModel):
    study_id: str = Field(default="brca_metabric", min_length=1, max_length=128)
    tables: list[CBioPortalTableType] = Field(
        default_factory=lambda: list(CBioPortalTableType), min_length=1
    )
    gene_symbols: list[str] = Field(
        default_factory=lambda: ["ERBB2", "PIK3CA", "TP53"], min_length=1
    )
    max_records_per_table: int = Field(default=100, ge=1, le=10_000)
    cna_event_type: CBioPortalCNAEventType = CBioPortalCNAEventType.ALL
    sample_list_id: str | None = Field(default=None, min_length=1, max_length=256)
    mutation_profile_id: str | None = Field(
        default=None, min_length=1, max_length=256
    )
    cna_profile_id: str | None = Field(default=None, min_length=1, max_length=256)
    refresh_cache: bool = False

    @field_validator("study_id", mode="before")
    @classmethod
    def normalize_study_id(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("tables")
    @classmethod
    def unique_tables(
        cls, value: list[CBioPortalTableType]
    ) -> list[CBioPortalTableType]:
        return list(dict.fromkeys(value))

    @field_validator("gene_symbols", mode="before")
    @classmethod
    def normalize_gene_symbols(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized = [
            item.strip().upper() if isinstance(item, str) else item for item in value
        ]
        return list(dict.fromkeys(normalized))


class CBioPortalAdapterRequest(ApiModel):
    search_plan: SearchPlan
    options: CBioPortalAdapterOptions = Field(
        default_factory=CBioPortalAdapterOptions
    )


class CBioPortalRequestTrace(ApiModel):
    method: str
    url: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None


class CBioPortalStudyRecord(ApiModel):
    study_id: str
    portal_url: str
    raw_metadata: dict[str, Any]
    source_item: SourceItem


class CBioPortalRawTable(ApiModel):
    table_name: str
    study_id: str
    raw_fields: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    upstream_row_count: int | None = Field(default=None, ge=0)
    truncated: bool
    request: CBioPortalRequestTrace
    source_item: SourceItem


class CBioPortalSelection(ApiModel):
    mutation_profile_id: str | None = None
    cna_profile_id: str | None = None
    mutation_sample_list_id: str | None = None
    cna_sample_list_id: str | None = None
    genes: list[dict[str, Any]] = Field(default_factory=list)


class CBioPortalAdapterResult(ApiModel):
    task_id: str
    adapter: str = "cbioportal"
    study: CBioPortalStudyRecord
    selection: CBioPortalSelection
    tables: list[CBioPortalRawTable]
    source_items: list[SourceItem]
    cache_hit: dict[str, bool]
    queried_at: datetime
    notice: str
