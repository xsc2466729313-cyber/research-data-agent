from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator

from backend.app.models import ApiModel, SearchPlan, SourceItem


class GEOResourceType(str, Enum):
    SERIES_MATRIX = "series_matrix"
    SOFT = "soft"
    SUPPLEMENT = "supplement"


class GEOAdapterOptions(ApiModel):
    accession: str = Field(min_length=1, max_length=32)
    resource_types: list[GEOResourceType] = Field(
        default_factory=lambda: list(GEOResourceType), min_length=1
    )
    max_files_per_type: int = Field(default=10, ge=1, le=100)
    download: bool = False
    max_download_bytes: int = Field(
        default=25_000_000, ge=1, le=2_000_000_000
    )
    refresh_cache: bool = False

    @field_validator("accession", mode="before")
    @classmethod
    def normalize_accession(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("resource_types")
    @classmethod
    def unique_resource_types(
        cls, value: list[GEOResourceType]
    ) -> list[GEOResourceType]:
        return list(dict.fromkeys(value))


class GEOAdapterRequest(ApiModel):
    search_plan: SearchPlan
    options: GEOAdapterOptions


class GEOResourceAvailability(ApiModel):
    resource_type: GEOResourceType
    directory_url: str
    status: str
    file_count: int = Field(ge=0)


class GEOResourceRecord(ApiModel):
    accession: str
    resource_type: GEOResourceType
    file_name: str
    download_url: str
    status: str
    file_size: int | None = Field(default=None, ge=0)
    source_item: SourceItem


class GEOCacheStatus(ApiModel):
    accession_directory: bool
    resource_directories: dict[str, bool]


class GEOAdapterResult(ApiModel):
    task_id: str
    adapter: str = "geo"
    accession: str
    portal_url: str
    availability: list[GEOResourceAvailability]
    resources: list[GEOResourceRecord]
    source_items: list[SourceItem]
    cache_hit: GEOCacheStatus
    queried_at: datetime
    notice: str
