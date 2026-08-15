from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.models import ApiModel, CanonicalRecord, ResponseDomain


class NormalizationStatus(str, Enum):
    NORMALIZED = "normalized"
    IDENTITY = "identity"
    REVIEW = "review"
    UNRESOLVED = "unresolved"


class NormalizerKind(str, Enum):
    PASSTHROUGH = "passthrough"
    GENE = "gene"
    DRUG = "drug"
    BIOMARKER = "biomarker"
    MUTATION_STATUS = "mutation_status"
    RESPONSE_DOMAIN = "response_domain"


class SourceAuthority(str, Enum):
    HIGH = "high"
    STANDARD = "standard"
    LOW = "low"


class RawSourceRecord(ApiModel):
    record_id: str = Field(min_length=1, max_length=512)
    source_id: str = Field(min_length=1, max_length=512)
    source_authority: SourceAuthority = SourceAuthority.STANDARD
    fields: dict[str, Any] = Field(min_length=1)
    default_confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("fields")
    @classmethod
    def validate_field_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(not isinstance(key, str) or not key.strip() for key in value):
            raise ValueError("raw field names must be non-empty strings")
        return value


class FieldMapping(ApiModel):
    mapping_id: str = Field(min_length=1, max_length=512)
    source_id: str | None = Field(default=None, min_length=1, max_length=512)
    raw_field: str = Field(min_length=1, max_length=1024)
    canonical_field: str = Field(min_length=1, max_length=128)
    normalizer: NormalizerKind = NormalizerKind.PASSTHROUGH
    confidence: float = Field(default=1.0, ge=0, le=1)
    response_domain: ResponseDomain | None = None
    response_type: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_frozen_target_and_normalizer(self) -> FieldMapping:
        if self.canonical_field not in CanonicalRecord.model_fields:
            raise ValueError(
                f"canonical_field is not in frozen CanonicalRecord: {self.canonical_field}"
            )
        if self.canonical_field in {
            "source_id",
            "raw_field",
            "raw_value",
            "confidence",
        }:
            raise ValueError(
                f"provenance field is assigned by SchemaMapper: {self.canonical_field}"
            )
        expected_fields = {
            NormalizerKind.GENE: {"gene"},
            NormalizerKind.DRUG: {"drug"},
            NormalizerKind.MUTATION_STATUS: {"mutation_status"},
            NormalizerKind.RESPONSE_DOMAIN: {"response_domain"},
        }
        allowed = expected_fields.get(self.normalizer)
        if allowed is not None and self.canonical_field not in allowed:
            raise ValueError(
                f"{self.normalizer.value} cannot target {self.canonical_field}"
            )
        required_normalizer = {
            "gene": NormalizerKind.GENE,
            "drug": NormalizerKind.DRUG,
            "mutation_status": NormalizerKind.MUTATION_STATUS,
            "response_domain": NormalizerKind.RESPONSE_DOMAIN,
            "er_status": NormalizerKind.BIOMARKER,
            "pr_status": NormalizerKind.BIOMARKER,
            "her2_status": NormalizerKind.BIOMARKER,
            "her2_assay": NormalizerKind.BIOMARKER,
            "her2_raw_value": NormalizerKind.BIOMARKER,
        }.get(self.canonical_field)
        if required_normalizer is not None and self.normalizer != required_normalizer:
            raise ValueError(
                f"{self.canonical_field} requires {required_normalizer.value} normalizer"
            )
        if self.response_domain is not None and self.canonical_field not in {
            "response",
            "response_type",
        }:
            raise ValueError("response_domain hint is only valid for response mappings")
        if self.response_type is not None and self.canonical_field != "response":
            raise ValueError("response_type hint is only valid when mapping response")
        return self


class NormalizedValue(ApiModel):
    values: dict[str, Any]
    method: str
    confidence: float = Field(ge=0, le=1)
    status: NormalizationStatus
    reason: str | None = None


class MappedCanonicalRecord(ApiModel):
    mapped_record_id: str = Field(min_length=1)
    raw_record_id: str = Field(min_length=1)
    mapping_id: str = Field(min_length=1)
    source_authority: SourceAuthority
    canonical_record: CanonicalRecord
    original_raw_value: Any
    mapped_fields: list[str] = Field(min_length=1)
    normalization_method: str = Field(min_length=1)
    normalization_status: NormalizationStatus
    review_reason: str | None = None


class NormalizedIdentity(ApiModel):
    raw_record_id: str
    study_id: str
    patient_id: str | None = None
    sample_id: str | None = None


class MappingIssue(ApiModel):
    raw_record_id: str
    mapping_id: str | None = None
    code: str
    message: str
    raw_field: str | None = None
    status: NormalizationStatus = NormalizationStatus.UNRESOLVED


class SchemaMappingResult(ApiModel):
    records: list[MappedCanonicalRecord]
    identities: list[NormalizedIdentity]
    issues: list[MappingIssue]
    blocked_record_ids: list[str]
