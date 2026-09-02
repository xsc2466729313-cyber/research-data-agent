from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.app.models import ApiModel


AccessMode = Literal[
    "OPEN_API",
    "API_KEY",
    "OAUTH",
    "LOGIN_REQUIRED",
    "MANUAL_DOWNLOAD",
    "CONTROLLED_ACCESS",
    "UNAVAILABLE",
]


class SourceCapability(ApiModel):
    source_id: str
    source_name: str
    source_kind: str
    source_url: str
    domains: list[str] = Field(default_factory=list)
    access_modes: list[AccessMode] = Field(default_factory=list)
    structuredness: float = Field(ge=0, le=1)
    authority: float = Field(ge=0, le=1)
    traceability: float = Field(ge=0, le=1)
    cost: float = Field(ge=0, le=1)
    supports_api: bool
    supports_patient_level: bool
    supports_sample_level: bool
    profile_status: Literal["seed_requires_runtime_verification"] = "seed_requires_runtime_verification"


class ResourceDescriptor(ApiModel):
    resource_id: str
    dataset_id: str
    source_id: str
    resource_type: str
    source_url: str
    access_mode: AccessMode
    expected_format: str | None = None


class DatasetCandidate(ApiModel):
    dataset_id: str
    source_id: str
    accession: str | None = None
    title: str
    source_url: str
    diseases: list[str] = Field(default_factory=list)
    declared_granularity: list[str] = Field(default_factory=list)
    field_hints: list[str] = Field(default_factory=list)
    sample_count: int | None = Field(default=None, ge=0)
    access_mode: AccessMode
    discovery_evidence_ids: list[str] = Field(default_factory=list)
    resources: list[ResourceDescriptor] = Field(default_factory=list)
    capability_status: Literal[
        "seed_requires_runtime_verification",
        "literature_hint_requires_profiling",
        "live_verified",
    ]
    authority: float = Field(ge=0, le=1)
    traceability: float = Field(ge=0, le=1)
    structuredness: float = Field(ge=0, le=1)
    cost: float = Field(ge=0, le=1)


class FieldCoverageCell(ApiModel):
    field_id: str
    priority: Literal["required", "recommended", "optional"]
    dataset_id: str
    coverage: float = Field(ge=0, le=1)
    match_basis: str
    runtime_verified: bool = False


class FieldCoverageMatrix(ApiModel):
    contract_id: str
    field_ids: list[str]
    dataset_ids: list[str]
    cells: list[FieldCoverageCell]
    notice: str


class JoinPolicy(ApiModel):
    left_dataset_id: str
    right_dataset_id: str
    decision: Literal[
        "SAME_DATASET_ONLY",
        "FORBIDDEN_PATIENT_JOIN",
        "REVIEW_REQUIRED",
    ]
    reason: str
    identity_evidence_ids: list[str] = Field(default_factory=list)


class SourcePlanRequest(ApiModel):
    max_selected_datasets: int = Field(default=3, ge=1, le=6)
    preferred_dataset_ids: list[str] = Field(default_factory=list, max_length=20)
    public_data_only: bool = True


class SourcePlan(ApiModel):
    source_plan_id: str
    contract_id: str
    version: int = 1
    status: Literal["READY", "PARTIAL", "NEEDS_REVIEW"]
    selected_dataset_ids: list[str]
    selected_resource_ids: list[str]
    dataset_roles: dict[str, str]
    required_field_coverage: float = Field(ge=0, le=1)
    portfolio_required_field_coverage: float = Field(ge=0, le=1)
    recommended_field_coverage: float = Field(ge=0, le=1)
    uncovered_required_fields: list[str]
    uncovered_recommended_fields: list[str]
    join_policies: list[JoinPolicy]
    access_requirements: list[AccessMode]
    fallback_dataset_ids: list[str]
    objective_score: float = Field(ge=0, le=1)
    explanation: list[str]
    warnings: list[str]
    created_at: datetime


class SourcePlanningResult(ApiModel):
    contract_id: str
    sources: list[SourceCapability]
    dataset_candidates: list[DatasetCandidate]
    coverage_matrix: FieldCoverageMatrix
    source_plan: SourcePlan
