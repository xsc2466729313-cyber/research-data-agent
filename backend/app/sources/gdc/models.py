from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.app.models import ApiModel, ResearchSpec, SearchPlan, SourceItem


class GDCAdapterOptions(ApiModel):
    project_id: str = Field(default="TCGA-BRCA", pattern=r"^[A-Za-z0-9]+-[A-Za-z0-9-]+$")
    data_types: list[str] = Field(default_factory=lambda: ["Clinical Supplement"])
    max_files: int = Field(default=5, ge=1, le=100)
    download: bool = False
    max_download_bytes: int = Field(default=25_000_000, ge=1, le=500_000_000)
    open_access_only: bool = True
    refresh_cache: bool = False


class GDCAdapterRequest(ApiModel):
    research_spec: ResearchSpec
    search_plan: SearchPlan
    options: GDCAdapterOptions = Field(default_factory=GDCAdapterOptions)


class GDCProjectRecord(ApiModel):
    project_id: str
    name: str
    state: str
    released: bool
    primary_site: list[str] = Field(default_factory=list)
    disease_type: list[str] = Field(default_factory=list)
    case_count: int = Field(ge=0)
    api_url: str
    portal_url: str


class GDCFileRecord(ApiModel):
    file_id: str
    project_id: str
    file_name: str
    md5sum: str
    file_size: int = Field(ge=0)
    state: str
    access: str
    data_category: str
    data_type: str
    data_format: str
    experimental_strategy: str | None = None
    download_url: str
    source_item: SourceItem


class GDCCacheStatus(ApiModel):
    project_metadata: bool
    file_metadata: bool


class GDCAdapterResult(ApiModel):
    task_id: str
    adapter: str = "gdc"
    project: GDCProjectRecord
    files: list[GDCFileRecord]
    source_items: list[SourceItem]
    cache_hit: GDCCacheStatus
    queried_at: datetime
    notice: str

