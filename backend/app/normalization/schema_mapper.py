from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from pydantic import ValidationError

from backend.app.models import CanonicalRecord, MutationStatus, ResponseDomain
from backend.app.normalization.biomarker_normalizer import BiomarkerNormalizer
from backend.app.normalization.drug_normalizer import DrugNormalizer
from backend.app.normalization.gene_normalizer import GeneNormalizer
from backend.app.normalization.models import (
    FieldMapping,
    MappedCanonicalRecord,
    MappingIssue,
    NormalizationStatus,
    NormalizedIdentity,
    NormalizedValue,
    NormalizerKind,
    RawSourceRecord,
    SchemaMappingResult,
)


class SchemaMapper:
    _CONTEXT_FIELDS = {
        "study_id",
        "disease",
        "patient_id",
        "sample_id",
        "response_domain",
        "response_type",
    }
    _PRECLINICAL_MEASURES = {"auc", "ic50", "viability"}

    def __init__(
        self,
        *,
        gene_normalizer: GeneNormalizer | None = None,
        drug_normalizer: DrugNormalizer | None = None,
        biomarker_normalizer: BiomarkerNormalizer | None = None,
    ) -> None:
        self.gene_normalizer = gene_normalizer or GeneNormalizer()
        self.drug_normalizer = drug_normalizer or DrugNormalizer()
        self.biomarker_normalizer = biomarker_normalizer or BiomarkerNormalizer()

    def map(
        self,
        *,
        records: list[RawSourceRecord],
        mappings: list[FieldMapping],
    ) -> SchemaMappingResult:
        mapped_records: list[MappedCanonicalRecord] = []
        identities: list[NormalizedIdentity] = []
        issues: list[MappingIssue] = []
        blocked_record_ids: list[str] = []

        for raw_record in records:
            normalized: list[tuple[FieldMapping, Any, NormalizedValue]] = []
            for mapping in mappings:
                if mapping.source_id is not None and mapping.source_id != raw_record.source_id:
                    continue
                found, raw_value = self._extract(raw_record.fields, mapping.raw_field)
                if not found:
                    issues.append(
                        MappingIssue(
                            raw_record_id=raw_record.record_id,
                            mapping_id=mapping.mapping_id,
                            code="raw_field_missing",
                            message=f"Raw field is missing: {mapping.raw_field}",
                            raw_field=mapping.raw_field,
                            status=NormalizationStatus.REVIEW,
                        )
                    )
                    continue
                value = self._normalize(mapping=mapping, raw_value=raw_value)
                normalized.append((mapping, raw_value, value))
                if value.status in {
                    NormalizationStatus.REVIEW,
                    NormalizationStatus.UNRESOLVED,
                }:
                    issues.append(
                        MappingIssue(
                            raw_record_id=raw_record.record_id,
                            mapping_id=mapping.mapping_id,
                            code="normalization_review",
                            message=value.reason or "Normalization requires review.",
                            raw_field=mapping.raw_field,
                            status=value.status,
                        )
                    )

            context, context_issues = self._context(
                raw_record_id=raw_record.record_id,
                normalized=normalized,
            )
            issues.extend(context_issues)
            if "study_id" not in context or "disease" not in context or context_issues:
                blocked_record_ids.append(raw_record.record_id)
                continue
            identities.append(
                NormalizedIdentity(
                    raw_record_id=raw_record.record_id,
                    study_id=context["study_id"],
                    patient_id=context.get("patient_id"),
                    sample_id=context.get("sample_id"),
                )
            )

            for mapping, raw_value, normalized_value in normalized:
                if not normalized_value.values:
                    continue
                fragments = dict(normalized_value.values)
                evidence_fields = set(fragments)
                if mapping.response_domain is not None:
                    evidence_fields.add("response_domain")
                if mapping.response_type is not None:
                    evidence_fields.add("response_type")
                response_issue = self._attach_and_validate_response_context(
                    mapping=mapping,
                    fragments=fragments,
                    context=context,
                )
                if response_issue is not None:
                    issues.append(
                        MappingIssue(
                            raw_record_id=raw_record.record_id,
                            mapping_id=mapping.mapping_id,
                            code="unsafe_response_domain",
                            message=response_issue,
                            raw_field=mapping.raw_field,
                        )
                    )
                    continue
                payload: dict[str, Any] = {
                    "study_id": context["study_id"],
                    "patient_id": context.get("patient_id"),
                    "sample_id": context.get("sample_id"),
                    "disease": context["disease"],
                    "source_id": raw_record.source_id,
                    "raw_field": mapping.raw_field,
                    "raw_value": self._raw_to_string(raw_value),
                    "confidence": min(
                        raw_record.default_confidence,
                        mapping.confidence,
                        normalized_value.confidence,
                    ),
                    **fragments,
                }
                try:
                    canonical_record = CanonicalRecord.model_validate(payload)
                except ValidationError as exc:
                    issues.append(
                        MappingIssue(
                            raw_record_id=raw_record.record_id,
                            mapping_id=mapping.mapping_id,
                            code="canonical_validation_failed",
                            message=str(exc),
                            raw_field=mapping.raw_field,
                        )
                    )
                    continue
                mapped_fields = [
                    field
                    for field in CanonicalRecord.model_fields
                    if field in evidence_fields
                    and field in fragments
                    and fragments[field] is not None
                ]
                mapped_id = self._mapped_record_id(
                    raw_record_id=raw_record.record_id,
                    mapping=mapping,
                    raw_value=raw_value,
                )
                mapped_records.append(
                    MappedCanonicalRecord(
                        mapped_record_id=mapped_id,
                        raw_record_id=raw_record.record_id,
                        mapping_id=mapping.mapping_id,
                        source_authority=raw_record.source_authority,
                        canonical_record=canonical_record,
                        original_raw_value=raw_value,
                        mapped_fields=mapped_fields,
                        normalization_method=normalized_value.method,
                        normalization_status=normalized_value.status,
                        review_reason=normalized_value.reason,
                    )
                )

        return SchemaMappingResult(
            records=mapped_records,
            identities=identities,
            issues=issues,
            blocked_record_ids=list(dict.fromkeys(blocked_record_ids)),
        )

    def _normalize(self, *, mapping: FieldMapping, raw_value: Any) -> NormalizedValue:
        if mapping.normalizer == NormalizerKind.GENE:
            return self.gene_normalizer.normalize(raw_value)
        if mapping.normalizer == NormalizerKind.DRUG:
            return self.drug_normalizer.normalize(raw_value)
        if mapping.normalizer == NormalizerKind.BIOMARKER:
            return self.biomarker_normalizer.normalize(
                raw_field=mapping.raw_field,
                raw_value=raw_value,
                canonical_field=mapping.canonical_field,
            )
        if mapping.normalizer == NormalizerKind.MUTATION_STATUS:
            return self._normalize_mutation_status(raw_value)
        if mapping.normalizer == NormalizerKind.RESPONSE_DOMAIN:
            return self._normalize_response_domain(raw_value)
        if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
            return NormalizedValue(
                values={},
                method="passthrough_unresolved",
                confidence=0,
                status=NormalizationStatus.UNRESOLVED,
                reason="Raw value is empty.",
            )
        value = raw_value.strip() if isinstance(raw_value, str) else self._raw_to_string(raw_value)
        return NormalizedValue(
            values={mapping.canonical_field: value},
            method="schema_passthrough_v1",
            confidence=1.0,
            status=NormalizationStatus.IDENTITY,
        )

    @classmethod
    def _context(
        cls,
        *,
        raw_record_id: str,
        normalized: list[tuple[FieldMapping, Any, NormalizedValue]],
    ) -> tuple[dict[str, Any], list[MappingIssue]]:
        candidates: dict[str, list[Any]] = defaultdict(list)
        for _, _, value in normalized:
            for field, normalized_value in value.values.items():
                if field in cls._CONTEXT_FIELDS and normalized_value is not None:
                    candidates[field].append(normalized_value)
        context: dict[str, Any] = {}
        issues: list[MappingIssue] = []
        for field, values in candidates.items():
            unique = list(dict.fromkeys(values))
            if len(unique) > 1:
                issues.append(
                    MappingIssue(
                        raw_record_id=raw_record_id,
                        code="context_conflict",
                        message=f"Conflicting {field} values within one raw record.",
                        status=NormalizationStatus.UNRESOLVED,
                    )
                )
            elif unique:
                context[field] = unique[0]
        for required in ("study_id", "disease"):
            if required not in context:
                issues.append(
                    MappingIssue(
                        raw_record_id=raw_record_id,
                        code="missing_required_context",
                        message=f"Required canonical context is missing: {required}",
                        status=NormalizationStatus.UNRESOLVED,
                    )
                )
        return context, issues

    @classmethod
    def _attach_and_validate_response_context(
        cls,
        *,
        mapping: FieldMapping,
        fragments: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        response_related = bool(
            {"response", "response_type", "response_domain"} & fragments.keys()
        )
        if not response_related:
            return None
        domain = mapping.response_domain or fragments.get("response_domain") or context.get(
            "response_domain"
        )
        if isinstance(domain, str):
            domain = ResponseDomain(domain)
        if domain is None and "response" in fragments:
            return "Response value is blocked because response_domain is missing."
        if domain is not None:
            fragments["response_domain"] = domain.value
        response_type = mapping.response_type or fragments.get("response_type") or context.get(
            "response_type"
        )
        if response_type is not None:
            fragments["response_type"] = str(response_type)
        measure_text = f"{mapping.raw_field} {response_type or ''}".casefold()
        preclinical_measure = any(
            re.search(rf"\b{re.escape(measure)}\b", measure_text)
            for measure in cls._PRECLINICAL_MEASURES
        )
        if preclinical_measure and domain != ResponseDomain.PRECLINICAL_CELL_LINE:
            return (
                "AUC/IC50/viability cannot be mapped outside "
                "preclinical_cell_line response_domain."
            )
        return None

    @staticmethod
    def _normalize_mutation_status(raw_value: Any) -> NormalizedValue:
        key = re.sub(r"[\s_-]+", "", str(raw_value).strip().casefold())
        mutated = {"mutated", "mutation", "variant", "present", "detected", "positive"}
        wild_type = {"wildtype", "wt", "negative", "notdetected", "absent"}
        if key in mutated:
            status = MutationStatus.MUTATED
        elif key in wild_type:
            status = MutationStatus.WILD_TYPE
        elif key in {"unknown", "na", "n/a", "notreported"}:
            status = MutationStatus.UNKNOWN
        else:
            return NormalizedValue(
                values={"mutation_status": MutationStatus.UNKNOWN.value},
                method="mutation_status_unresolved_v1",
                confidence=0.4,
                status=NormalizationStatus.REVIEW,
                reason="Mutation status terminology is ambiguous.",
            )
        return NormalizedValue(
            values={"mutation_status": status.value},
            method="mutation_status_exact_v1",
            confidence=1.0 if status != MutationStatus.UNKNOWN else 0.6,
            status=(
                NormalizationStatus.NORMALIZED
                if status != MutationStatus.UNKNOWN
                else NormalizationStatus.REVIEW
            ),
        )

    @staticmethod
    def _normalize_response_domain(raw_value: Any) -> NormalizedValue:
        key = re.sub(r"[\s_-]+", "", str(raw_value).strip().casefold())
        aliases = {
            "clinical": ResponseDomain.CLINICAL,
            "patient": ResponseDomain.CLINICAL,
            "preclinicalcellline": ResponseDomain.PRECLINICAL_CELL_LINE,
            "cellline": ResponseDomain.PRECLINICAL_CELL_LINE,
            "invitro": ResponseDomain.PRECLINICAL_CELL_LINE,
            "clinicaltrial": ResponseDomain.CLINICAL_TRIAL,
            "trial": ResponseDomain.CLINICAL_TRIAL,
            "knowledgeevidence": ResponseDomain.KNOWLEDGE_EVIDENCE,
            "evidence": ResponseDomain.KNOWLEDGE_EVIDENCE,
        }
        domain = aliases.get(key)
        if domain is None:
            return NormalizedValue(
                values={},
                method="response_domain_unresolved_v1",
                confidence=0,
                status=NormalizationStatus.UNRESOLVED,
                reason="Unsupported response domain.",
            )
        return NormalizedValue(
            values={"response_domain": domain.value},
            method="response_domain_exact_v1",
            confidence=1.0,
            status=NormalizationStatus.NORMALIZED,
        )

    @staticmethod
    def _extract(fields: dict[str, Any], raw_field: str) -> tuple[bool, Any]:
        current: Any = fields
        for part in raw_field.split("."):
            if not isinstance(current, dict) or part not in current:
                return False, None
            current = current[part]
        return True, current

    @staticmethod
    def _raw_to_string(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _mapped_record_id(
        cls,
        *,
        raw_record_id: str,
        mapping: FieldMapping,
        raw_value: Any,
    ) -> str:
        encoded = json.dumps(
            {
                "raw_record_id": raw_record_id,
                "mapping_id": mapping.mapping_id,
                "raw_field": mapping.raw_field,
                "raw_value": raw_value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"mapped:{hashlib.sha256(encoded).hexdigest()[:24]}"
