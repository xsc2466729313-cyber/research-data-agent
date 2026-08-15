from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.models import ApiModel, CandidateSource, ResearchSpec, SourceItem


class AgentDataMode(str, Enum):
    LIVE = "live"
    PLAN_ONLY = "plan_only"


class AgentTaskRequest(ApiModel):
    question: str = Field(min_length=5, max_length=2000)
    use_qwen: bool = True
    allow_deterministic_fallback: bool = True
    data_mode: AgentDataMode = AgentDataMode.LIVE
    preferred_sources: list[str] = Field(default_factory=list, max_length=5)
    max_sources: int = Field(default=5, ge=1, le=5)
    max_records: int = Field(default=10_000, ge=10, le=10_000)


class AgentConfigurationStatus(ApiModel):
    provider: str = "阿里云百炼 / 千问"
    configured: bool
    model: str
    base_url_configured: bool
    workspace_configured: bool
    function_calling: bool = True
    secret_persisted_by_application: bool = False
    message: str


class AgentPlanStep(ApiModel):
    step_id: str
    label: str
    status: str
    detail: str


class AgentToolCall(ApiModel):
    call_id: str
    tool_name: str
    tool_label: str
    arguments: dict[str, Any]
    status: str
    source_count: int = Field(default=0, ge=0)
    record_count: int = Field(default=0, ge=0)
    message: str
    started_at: datetime
    completed_at: datetime


class DatasetColumn(ApiModel):
    name: str
    label_zh: str
    data_type: str
    role: str
    source_field: str | None = None
    description: str


class ModelingDataset(ApiModel):
    name: str
    unit_of_analysis: str
    columns: list[DatasetColumn]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    patient_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    target_column: str | None = None
    class_distribution: dict[str, int] = Field(default_factory=dict)


class AnalysisReadinessReport(ApiModel):
    status: str
    analysis_ready: bool
    row_count: int = Field(ge=0)
    feature_count: int = Field(ge=0)
    target_column: str | None = None
    target_missing_rate: float | None = Field(default=None, ge=0, le=1)
    field_completeness_rate: float | None = Field(default=None, ge=0, le=1)
    target_match: bool = False
    requested_variable_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    repeated_patient_count: int = Field(default=0, ge=0)
    duplicate_row_count: int = Field(default=0, ge=0)
    cleaned_value_count: int = Field(default=0, ge=0)
    excluded_orphan_record_count: int = Field(default=0, ge=0)
    cleaning_actions: list[str] = Field(default_factory=list)
    split_strategy: str
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AgentTaskResult(ApiModel):
    task_id: str
    status: str
    agent_mode: str
    model_provider: str
    model_name: str
    used_qwen: bool
    notice: str
    research_spec: ResearchSpec
    plan: list[AgentPlanStep]
    tool_calls: list[AgentToolCall]
    candidate_sources: list[CandidateSource]
    source_items: list[SourceItem]
    modeling_dataset: ModelingDataset
    readiness: AnalysisReadinessReport
    summary_zh: str
    created_at: datetime
