from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from backend.app.models import ApiModel, SourceItem


class DiscoveryRequest(ApiModel):
    query: str = Field(min_length=2, max_length=1000)
    max_records: int = Field(default=20, ge=1, le=100)


class BioSampleRecord(ApiModel):
    uid: str
    accession: str | None = None
    title: str | None = None
    organism: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    url: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    source_item: SourceItem


class EuropePMCRecord(ApiModel):
    record_id: str
    pmid: str | None = None
    doi: str | None = None
    title: str | None = None
    journal: str | None = None
    publication_year: int | None = None
    abstract: str | None = None
    url: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    source_item: SourceItem


class GeoCatalogRecord(ApiModel):
    uid: str
    accession: str
    title: str | None = None
    summary: str | None = None
    n_samples: int | None = None
    dataset_type: str | None = None
    url: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    source_item: SourceItem


class ZenodoDatasetRecord(ApiModel):
    """A public dataset candidate represented by Zenodo's official metadata."""

    record_type: Literal["zenodo_dataset"] = "zenodo_dataset"
    record_id: str
    title: str | None = None
    description: str | None = None
    doi: str | None = None
    publication_date: str | None = None
    keywords: list[str] = Field(default_factory=list)
    file_count: int = Field(default=0, ge=0)
    file_formats: list[str] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    url: str
    raw_record: dict[str, Any] = Field(default_factory=dict)
    source_item: SourceItem


class DiscoveryAdapterResult(ApiModel):
    task_id: str
    adapter: str = "discovery"
    query: str
    source_kind: str
    total_count: int = Field(ge=0)
    records: list[BioSampleRecord | EuropePMCRecord | GeoCatalogRecord | ZenodoDatasetRecord]
    source_items: list[SourceItem]
    request_url: str
    queried_at: datetime
    notice: str
    pmcid: str | None = None
    parse_warnings: list[str] = Field(default_factory=list)
    parsed_field_count: int = Field(default=0, ge=0)
