from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.app.models import ApiModel


DiagnosisType = Literal[
    "ALL_MET",
    "NO_PATIENT_TABLE",
    "MISSING_EXPOSURE",
    "MISSING_OUTCOME",
    "OUTCOME_MISMATCH",
    "MISSING_COVARIATES",
    "IDENTITY_UNRESOLVED",
    "FORBIDDEN_JOIN",
    "MISSING_EVIDENCE",
    "SEMANTIC_CONFLICT",
    "PARSING_FAILURE",
    "RESIDUAL_GAPS",
]


class GapDiagnosis(ApiModel):
    diagnosis_type: DiagnosisType
    severity: Literal["info", "warning", "blocker"]
    affected_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class CriticReport(ApiModel):
    contract_id: str | None = None
    answers_contract: bool
    diagnoses: list[GapDiagnosis]
    notice: str
