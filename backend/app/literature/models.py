from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from backend.app.models import ApiModel


class LiteratureSearchRequest(ApiModel):
    query: str = Field(min_length=2, max_length=1000)
    max_records: int = Field(default=20, ge=1, le=100)


class LiteratureProviderTrace(ApiModel):
    provider: str
    query: str
    requested_at: datetime
    completed_at: datetime
    status: Literal["success", "failed", "skipped"]
    source_url: str | None = None
    result_count: int = Field(default=0, ge=0)
    error_type: str | None = None


class PaperRecord(ApiModel):
    paper_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    abstract: str | None = None
    pmid: str | None = None
    doi: str | None = None
    journal: str | None = None
    publication_year: int | None = Field(default=None, ge=1600, le=2200)
    authors: list[str] = Field(default_factory=list)
    fulltext_available: bool = False
    sections: dict[str, str] = Field(default_factory=dict)
    dataset_accessions: list[str] = Field(default_factory=list)
    acquisition_traces: list[LiteratureProviderTrace] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class PaperEvidence(ApiModel):
    evidence_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    section: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1200)
    confidence: float = Field(ge=0, le=1)


class LiteratureSearchResult(ApiModel):
    provider: str
    query: str
    papers: list[PaperRecord] = Field(default_factory=list)
    trace: LiteratureProviderTrace


class LiteratureScanRequest(ApiModel):
    query: str | None = Field(default=None, min_length=2, max_length=1000)
    max_records: int = Field(default=20, ge=1, le=100)


class LiteratureScan(ApiModel):
    topic_id: str
    query: str
    papers: list[PaperRecord] = Field(default_factory=list)
    provider_traces: list[LiteratureProviderTrace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scanned_at: datetime
