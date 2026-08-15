from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.evaluation.models import RiskLevel
from backend.app.models import ApiModel, SafetyGate
from backend.app.normalization.models import SourceAuthority


class RepairErrorType(str, Enum):
    EXACT_DUPLICATE = "exact_duplicate"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    PROVENANCE_MISSING = "provenance_missing"
    GENE_ALIAS = "gene_alias"
    DRUG_ALIAS = "drug_alias"
    CASING_NORMALIZATION = "casing_normalization"
    SCHEMA_MAPPING_ERROR = "schema_mapping_error"
    INVALID_SCHEMA_VALUE = "invalid_schema_value"
    HER2_ASSAY_ERROR = "her2_assay_error"
    ERBB2_CNA_NOT_IHC = "erbb2_cna_not_ihc"
    PATIENT_SAMPLE_CONFLICT = "patient_sample_conflict"
    HIGH_AUTHORITY_CONFLICT = "high_authority_conflict"
    CROSS_DOMAIN_RESPONSE = "cross_domain_response"


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyAction(str, Enum):
    AUTO_REPAIR = "auto_repair"
    REVIEW = "review"
    BLOCK = "block"


class RepairExecutionStatus(str, Enum):
    APPLIED = "applied"
    NOT_EXECUTED = "not_executed"
    ROLLED_BACK = "rolled_back"


class RecordDisposition(str, Enum):
    PUBLISHABLE = "publishable"
    REVIEW = "review"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"


class ValidationPhase(str, Enum):
    BEFORE_REPAIR = "before_repair"
    AFTER_REPAIR = "after_repair"
    AFTER_ROLLBACK = "after_rollback"


class RepairRecordInput(ApiModel):
    record_id: str = Field(min_length=1, max_length=512)
    source_authority: SourceAuthority = SourceAuthority.STANDARD
    record: dict[str, Any] = Field(min_length=1, max_length=200)

    @field_validator("record")
    @classmethod
    def validate_record_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(not isinstance(key, str) or not key.strip() for key in value):
            raise ValueError("record field names must be non-empty strings")
        return value


class RepairRequest(ApiModel):
    task_id: str = Field(min_length=1, max_length=512)
    records: list[RepairRecordInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_record_ids(self) -> RepairRequest:
        ids = [item.record_id for item in self.records]
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        if duplicates:
            raise ValueError(f"record_id values must be unique: {duplicates}")
        return self


class ErrorFinding(ApiModel):
    finding_id: str = Field(min_length=1)
    error_type: RepairErrorType
    rule_id: str = Field(min_length=1)
    record_ids: list[str] = Field(min_length=1)
    field: str | None = None
    observed_value: Any = None
    candidate_repair: dict[str, Any] | None = None
    risk_level: RiskLevel
    severity: FindingSeverity
    deterministic: bool
    message: str = Field(min_length=1)


class ErrorClassificationResult(ApiModel):
    task_id: str
    classifier_version: str
    findings: list[ErrorFinding]
    summary: dict[str, int]
    classified_at: datetime


class RepairPolicyDecision(ApiModel):
    decision_id: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    error_type: RepairErrorType
    action: PolicyAction
    policy_rule: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class RepairChange(ApiModel):
    operation: str = Field(pattern=r"^(replace|quarantine)$")
    record_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    before: Any = None
    after: Any = None


class RepairRecordState(ApiModel):
    record_id: str = Field(min_length=1)
    source_authority: SourceAuthority
    disposition: RecordDisposition
    record: dict[str, Any]
    disposition_reasons: list[str] = Field(default_factory=list)


class RepairLogEntry(ApiModel):
    log_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    finding_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    error_type: RepairErrorType
    action: PolicyAction
    execution_status: RepairExecutionStatus
    before: list[RepairRecordState] = Field(min_length=1)
    after: list[RepairRecordState] = Field(min_length=1)
    changes: list[RepairChange]
    revalidated: bool = False
    validation_passed: bool | None = None
    rollback_reason: str | None = None
    policy_rule: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_at: datetime


class QualityValidationFinding(ApiModel):
    finding_id: str
    record_ids: list[str] = Field(min_length=1)
    rule_id: str
    severity: FindingSeverity
    message: str


class QualityValidationResult(ApiModel):
    validation_id: str
    phase: ValidationPhase
    checked_record_count: int = Field(ge=0)
    excluded_record_ids: list[str]
    findings: list[QualityValidationFinding]
    failed_record_ids: list[str]
    passed: bool
    validated_at: datetime


class RepairLoopResult(ApiModel):
    task_id: str
    pipeline: str = "repair_loop"
    classification: ErrorClassificationResult
    policy_decisions: list[RepairPolicyDecision]
    record_states: list[RepairRecordState]
    publishable_records: list[RepairRecordInput]
    review_records: list[RepairRecordInput]
    blocked_records: list[RepairRecordInput]
    quarantined_records: list[RepairRecordInput]
    repair_log: list[RepairLogEntry]
    quality_before: QualityValidationResult
    quality_after: QualityValidationResult
    validation_history: list[QualityValidationResult] = Field(min_length=2)
    safety_gate: SafetyGate
    summary: dict[str, int | bool | str | None]
    completed_at: datetime
    notice: str
