from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from backend.app.models import ApiModel, SearchPlan, SourceItem


class AACTTableName(str, Enum):
    STUDIES = "studies"
    CONDITIONS = "conditions"
    INTERVENTIONS = "interventions"
    ELIGIBILITIES = "eligibilities"
    OUTCOMES = "outcomes"
    OUTCOME_MEASUREMENTS = "outcome_measurements"


class TrialResultsStatus(str, Enum):
    AVAILABLE = "available"
    NOT_REPORTED = "not_reported"
    INCONSISTENT = "inconsistent"


class AACTAdapterOptions(ApiModel):
    condition: str = Field(default="Breast Cancer", min_length=1, max_length=256)
    query_terms: str | None = Field(default=None, min_length=1, max_length=1000)
    max_trials: int = Field(default=5, ge=1, le=25)
    max_rows_per_table: int = Field(default=10_000, ge=1, le=50_000)
    page_token: str | None = Field(default=None, min_length=1, max_length=4096)
    refresh_cache: bool = False

    @field_validator("condition", "query_terms", "page_token", mode="before")
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class AACTAdapterRequest(ApiModel):
    search_plan: SearchPlan
    options: AACTAdapterOptions = Field(default_factory=AACTAdapterOptions)


class AACTRequestTrace(ApiModel):
    method: str
    url: str
    parameters: dict[str, Any]


class AACTUnifiedTrial(ApiModel):
    nct_id: str
    trial_id: str
    brief_title: str
    official_title: str | None = None
    overall_status: str | None = None
    study_type: str | None = None
    phases: list[str] = Field(default_factory=list)
    enrollment_count: int | None = Field(default=None, ge=0)
    has_results: bool | None = None
    results_status: TrialResultsStatus
    study_url: str
    raw_study: dict[str, Any]
    source_item: SourceItem


class AACTRawTable(ApiModel):
    table_name: AACTTableName
    primary_key: str = "nct_id"
    raw_fields: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    upstream_row_count: int = Field(ge=0)
    truncated: bool


class AACTAdapterResult(ApiModel):
    task_id: str
    adapter: str = "aact"
    condition: str
    total_count: int = Field(ge=0)
    next_page_token: str | None = None
    search_request: AACTRequestTrace
    trials: list[AACTUnifiedTrial]
    tables: list[AACTRawTable]
    source_items: list[SourceItem]
    cache_hit: bool
    queried_at: datetime
    notice: str
