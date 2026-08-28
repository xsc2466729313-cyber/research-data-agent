from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from backend.app.models import ApiModel


class DecisionSource(str, Enum):
    RULE = "RULE"
    ALGORITHM = "ALGORITHM"
    QWEN = "QWEN"
    HUMAN = "HUMAN"


class DecisionStatus(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class RuleOutcome(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EvidenceRecord(ApiModel):
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    raw_field: str = Field(min_length=1)
    raw_value: Any
    transformation: str = Field(min_length=1)
    model_or_rule: str = Field(min_length=1)
    version: str = Field(min_length=1)
    created_at: datetime


class RuleValidation(ApiModel):
    rule_id: str = Field(min_length=1)
    outcome: RuleOutcome
    action: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class AuditStamp(ApiModel):
    code_revision: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    dataset_manifest: str = Field(min_length=1)
    timestamp: datetime
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class DecisionRecord(ApiModel):
    proposal_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    candidate: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    decision_source: DecisionSource
    rule_validation: list[RuleValidation]
    status: DecisionStatus
    model_version: str = Field(min_length=1)
    created_at: datetime
    audit: AuditStamp

    @model_validator(mode="after")
    def auto_requires_complete_evidence_and_passed_rules(self) -> "DecisionRecord":
        if self.status is not DecisionStatus.AUTO:
            return self
        if not self.evidence:
            raise ValueError("AUTO decisions require at least one complete EvidenceRecord")
        if any(item.outcome is not RuleOutcome.PASS for item in self.rule_validation):
            raise ValueError("AUTO decisions require every safety rule to PASS")
        return self


class ReviewRecord(ApiModel):
    review_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    rule_ids: list[str] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer: str | None = None
    resolution: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
