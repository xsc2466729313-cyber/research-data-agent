from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.app.evaluation.models import RiskLevel
from backend.app.normalization import DrugNormalizer, GeneNormalizer
from backend.app.normalization.models import NormalizationStatus, SourceAuthority
from backend.app.repair.errors import RepairError, RepairErrorCode
from backend.app.repair.models import (
    ErrorClassificationResult,
    ErrorFinding,
    FindingSeverity,
    RepairErrorType,
    RepairRecordInput,
)


ROOT = Path(__file__).resolve().parents[3]


class ErrorClassifier:
    """Deterministic quality checks over canonical-shaped records."""

    VERSION = "error-classifier-v1"
    _PROVENANCE_FIELDS = {"source_id", "raw_field", "raw_value"}
    _CONFLICT_FIELDS = ("er_status", "pr_status", "her2_status", "response")
    _PRECLINICAL_MEASURES = {"auc", "ic50", "viability"}

    def __init__(
        self,
        *,
        canonical_schema_path: Path | None = None,
        gene_normalizer: GeneNormalizer | None = None,
        drug_normalizer: DrugNormalizer | None = None,
    ) -> None:
        self.canonical_schema_path = (
            canonical_schema_path or ROOT / "configs" / "canonical_schema.yaml"
        )
        self.schema = self._load_schema(self.canonical_schema_path)
        self.fields: dict[str, dict[str, Any]] = self.schema["fields"]
        self.gene_normalizer = gene_normalizer or GeneNormalizer()
        self.drug_normalizer = drug_normalizer or DrugNormalizer()

    def classify(
        self,
        *,
        task_id: str,
        records: list[RepairRecordInput],
    ) -> ErrorClassificationResult:
        findings: list[ErrorFinding] = []
        findings.extend(self._exact_duplicates(records))
        for item in records:
            findings.extend(self._classify_record(item))
        findings.extend(self._patient_sample_conflicts(records))
        findings.extend(self._high_authority_conflicts(records))
        findings = self._deduplicate(findings)
        counts = Counter(finding.error_type.value for finding in findings)
        return ErrorClassificationResult(
            task_id=task_id,
            classifier_version=self.VERSION,
            findings=findings,
            summary={
                "record_count": len(records),
                "finding_count": len(findings),
                "high_risk_finding_count": sum(
                    finding.risk_level == RiskLevel.HIGH for finding in findings
                ),
                "deterministic_finding_count": sum(
                    finding.deterministic for finding in findings
                ),
                **{f"error_type:{key}": value for key, value in sorted(counts.items())},
            },
            classified_at=datetime.now(timezone.utc),
        )

    def _classify_record(self, item: RepairRecordInput) -> list[ErrorFinding]:
        record = item.record
        findings: list[ErrorFinding] = []

        for field, spec in self.fields.items():
            if not spec.get("required"):
                continue
            missing = field not in record or record[field] is None
            if spec.get("type") == "string":
                missing = missing or not isinstance(record.get(field), str) or not str(
                    record.get(field, "")
                ).strip()
            if not missing:
                continue
            if field in self._PROVENANCE_FIELDS:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.PROVENANCE_MISSING,
                        rule_id="MISSING_EVIDENCE",
                        record_ids=[item.record_id],
                        field=field,
                        observed_value=record.get(field),
                        risk=RiskLevel.HIGH,
                        severity=FindingSeverity.CRITICAL,
                        deterministic=False,
                        message=(
                            f"Required provenance field {field} is missing; no value is "
                            "invented and the record is blocked from publishing."
                        ),
                    )
                )
            else:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.MISSING_REQUIRED_FIELD,
                        rule_id="CANONICAL_REQUIRED_FIELD",
                        record_ids=[item.record_id],
                        field=field,
                        observed_value=record.get(field),
                        risk=RiskLevel.HIGH,
                        severity=FindingSeverity.CRITICAL,
                        deterministic=False,
                        message=(
                            f"Required frozen-schema field {field} is missing; repair "
                            "requires real source evidence."
                        ),
                    )
                )

        extra_fields = sorted(set(record) - set(self.fields))
        if extra_fields:
            findings.append(
                self._finding(
                    error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                    rule_id="FROZEN_SCHEMA_FIELD_SET",
                    record_ids=[item.record_id],
                    observed_value=extra_fields,
                    risk=RiskLevel.MEDIUM,
                    severity=FindingSeverity.HIGH,
                    deterministic=False,
                    message=(
                        "Record contains fields outside frozen CanonicalRecord; their "
                        "meaning must be reviewed instead of silently dropped."
                    ),
                )
            )

        findings.extend(self._medical_safety_findings(item))
        findings.extend(self._entity_normalization_findings(item))
        findings.extend(self._schema_value_findings(item))
        findings.extend(self._semantic_integrity_findings(item))
        return findings

    def _semantic_integrity_findings(
        self, item: RepairRecordInput
    ) -> list[ErrorFinding]:
        """Detect source-shape anomalies without relying on benchmark case ids."""
        record = item.record
        findings: list[ErrorFinding] = []

        left = record.get("left")
        right = record.get("right")
        join_or_merge = self._key(record.get("join") or record.get("action"))
        has_crosswalk = bool(record.get("crosswalk") or record.get("crosswalk_id"))
        if left and right and join_or_merge and not has_crosswalk and str(left) != str(right):
            findings.append(
                self._finding(
                    error_type=RepairErrorType.PATIENT_SAMPLE_CONFLICT,
                    rule_id="CROSS_STUDY_JOIN_REQUIRES_CROSSWALK",
                    record_ids=[item.record_id],
                    field="patient_id",
                    observed_value={"left": left, "right": right, "operation": join_or_merge},
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message="Cross-study patient joins require an explicit, reviewed crosswalk.",
                )
            )

        score = record.get("match_score")
        decision = self._key(record.get("decision"))
        if isinstance(score, (int, float)) and score < 0.9 and decision in {"automerge", "merge"}:
            findings.append(
                self._finding(
                    error_type=RepairErrorType.PATIENT_SAMPLE_CONFLICT,
                    rule_id="LOW_CONFIDENCE_PATIENT_LINK",
                    record_ids=[item.record_id],
                    field="patient_id",
                    observed_value={"match_score": score, "decision": record.get("decision")},
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message="Low-confidence patient/sample links cannot be merged automatically.",
                )
            )

        rows = record.get("rows")
        timepoints = record.get("timepoint")
        stacked = record.get("stacked_as_two_analysis_rows") is True
        if (isinstance(rows, int) and rows > 1) or (stacked and isinstance(timepoints, list) and len(timepoints) > 1):
            findings.append(
                self._finding(
                    error_type=RepairErrorType.EXACT_DUPLICATE,
                    rule_id="ANALYSIS_GRAIN_DUPLICATE",
                    record_ids=[item.record_id],
                    observed_value={"rows": rows, "timepoint": timepoints},
                    candidate_repair={
                        "operation": "quarantine_duplicates",
                        "survivor_record_id": item.record_id,
                        "duplicate_record_ids": [item.record_id],
                    },
                    risk=RiskLevel.LOW,
                    severity=FindingSeverity.MEDIUM,
                    deterministic=True,
                    message="Repeated analysis rows are quarantined while source provenance is retained.",
                )
            )

        required = record.get("required")
        if isinstance(required, str) and required and not str(record.get(required) or "").strip():
            findings.append(
                self._finding(
                    error_type=RepairErrorType.MISSING_REQUIRED_FIELD,
                    rule_id="DECLARED_REQUIRED_FIELD",
                    record_ids=[item.record_id],
                    field=required,
                    observed_value=record.get(required),
                    risk=RiskLevel.MEDIUM,
                    severity=FindingSeverity.HIGH,
                    deterministic=False,
                    message=f"The source contract declares {required} required, but no value is present.",
                )
            )

        unit_guess = record.get("unit_guess")
        if unit_guess and any(
            isinstance(record.get(field), str) and re.fullmatch(r"0(?:\.\d+)?", record[field].strip())
            for field in ("age", "duration", "follow_up")
        ):
            findings.append(
                self._finding(
                    error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                    rule_id="AMBIGUOUS_UNIT_CONVERSION",
                    record_ids=[item.record_id],
                    observed_value={"unit_guess": unit_guess},
                    risk=RiskLevel.MEDIUM,
                    severity=FindingSeverity.HIGH,
                    deterministic=False,
                    message="A guessed unit conflicts with the observed scale and requires source review.",
                )
            )

        stage = record.get("stage")
        if isinstance(stage, str) and re.search(r"\bstge\b", stage, re.I):
            findings.append(
                self._finding(
                    error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                    rule_id="CLINICAL_STAGE_TYPO",
                    record_ids=[item.record_id],
                    field="stage",
                    observed_value=stage,
                    risk=RiskLevel.MEDIUM,
                    severity=FindingSeverity.HIGH,
                    deterministic=False,
                    message="The stage label contains a likely clinical-field typo and requires review.",
                )
            )

        raw_value_key = self._key(record.get("raw_value"))
        for field in ("er_status", "pr_status", "her2_status"):
            if self._key(record.get(field)) == "negative" and raw_value_key in {"na", "unknown", "unk", "missing"}:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                        rule_id="UNKNOWN_NOT_NEGATIVE",
                        record_ids=[item.record_id],
                        field=field,
                        observed_value={field: record.get(field), "raw_value": record.get("raw_value")},
                        risk=RiskLevel.MEDIUM,
                        severity=FindingSeverity.HIGH,
                        deterministic=False,
                        message="Unknown or missing biomarker evidence cannot be mapped to Negative.",
                    )
                )
        return findings

    def _medical_safety_findings(
        self, item: RepairRecordInput
    ) -> list[ErrorFinding]:
        record = item.record
        findings: list[ErrorFinding] = []
        assay = self._key(record.get("her2_assay"))
        status = self._key(record.get("her2_status"))
        raw_value = self._compact(
            record.get("her2_raw_value", record.get("raw_value"))
        )
        if assay == "ihc" and raw_value in {"2", "2+", "ihc2+", "her2ihc2+"} and status == "positive":
            findings.append(
                self._finding(
                    error_type=RepairErrorType.HER2_ASSAY_ERROR,
                    rule_id="HER2_IHC_2PLUS",
                    record_ids=[item.record_id],
                    field="her2_status",
                    observed_value=record.get("her2_status"),
                    candidate_repair={
                        "operation": "replace",
                        "field": "her2_status",
                        "value": "Equivocal",
                        "method": "medical_rule_review_candidate_v1",
                    },
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message=(
                        "HER2 IHC 2+ is not HER2 Positive. The safe candidate is shown "
                        "for review but is never applied automatically."
                    ),
                )
            )

        raw_field = self._key(record.get("raw_field"))
        is_erbb2_cna = ("erbb2" in raw_field or "her2" in raw_field) and any(
            token in raw_field for token in ("cna", "cnv", "copynumber", "amplification")
        )
        if is_erbb2_cna and status == "positive":
            findings.append(
                self._finding(
                    error_type=RepairErrorType.ERBB2_CNA_NOT_IHC,
                    rule_id="ERBB2_CNA_NOT_IHC",
                    record_ids=[item.record_id],
                    field="her2_status",
                    observed_value=record.get("her2_status"),
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message=(
                        "ERBB2 copy-number amplification cannot be represented as HER2 "
                        "IHC positivity; the assay dimension requires review."
                    ),
                )
            )

        response_type = self._key(record.get("response_type"))
        if not response_type:
            response_type = next(
                (
                    measure
                    for measure in self._PRECLINICAL_MEASURES
                    if any(self._key(key) == measure for key in record)
                ),
                "",
            )
        domain = self._key(record.get("response_domain"))
        if any(measure in response_type for measure in self._PRECLINICAL_MEASURES) and domain != "preclinicalcellline":
            findings.append(
                self._finding(
                    error_type=RepairErrorType.CROSS_DOMAIN_RESPONSE,
                    rule_id="CROSS_DOMAIN_RESPONSE",
                    record_ids=[item.record_id],
                    field="response_domain",
                    observed_value=record.get("response_domain"),
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message=(
                        "AUC/IC50/viability must remain in preclinical_cell_line and "
                        "cannot be treated as a patient clinical response."
                    ),
                )
            )
        response = self._key(record.get("response"))
        if response in {"pcr", "residualdisease", "rd"} and not domain:
            findings.append(
                self._finding(
                    error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                    rule_id="RESPONSE_DOMAIN_REQUIRED",
                    record_ids=[item.record_id],
                    field="response_domain",
                    observed_value=record.get("response_domain"),
                    risk=RiskLevel.MEDIUM,
                    severity=FindingSeverity.HIGH,
                    deterministic=False,
                    message="Clinical outcomes require an explicit clinical response domain.",
                )
            )
        return findings

    def _entity_normalization_findings(
        self, item: RepairRecordInput
    ) -> list[ErrorFinding]:
        record = item.record
        findings: list[ErrorFinding] = []
        gene = record.get("gene")
        if isinstance(gene, str) and gene.strip():
            if gene.strip().casefold() in self.drug_normalizer._ALIASES:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                        rule_id="GENE_DRUG_DIMENSION",
                        record_ids=[item.record_id],
                        field="gene",
                        observed_value=gene,
                        risk=RiskLevel.HIGH,
                        severity=FindingSeverity.HIGH,
                        deterministic=False,
                        message="A recognized drug appears in gene; remapping requires review.",
                    )
                )
            else:
                normalized = self.gene_normalizer.normalize(gene)
                canonical = normalized.values.get("gene")
                if canonical is not None and canonical != gene:
                    error_type = (
                        RepairErrorType.GENE_ALIAS
                        if normalized.method == "gene_alias_exact_v1"
                        else RepairErrorType.CASING_NORMALIZATION
                    )
                    findings.append(
                        self._replacement_finding(
                            item=item,
                            error_type=error_type,
                            field="gene",
                            observed=gene,
                            canonical=canonical,
                            method=normalized.method,
                            rule_id=(
                                "GENE_ALIAS_EXACT"
                                if error_type == RepairErrorType.GENE_ALIAS
                                else "CASING_NORMALIZATION"
                            ),
                        )
                    )

        drug = record.get("drug")
        known_genes = {
            *self.gene_normalizer._ALIASES.keys(),
            *self.gene_normalizer._ALIASES.values(),
            "PIK3CA",
            "ESR1",
            "BRCA1",
            "BRCA2",
        }
        if isinstance(drug, str) and drug.strip():
            if drug.strip().upper() in known_genes:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.SCHEMA_MAPPING_ERROR,
                        rule_id="GENE_DRUG_DIMENSION",
                        record_ids=[item.record_id],
                        field="drug",
                        observed_value=drug,
                        risk=RiskLevel.HIGH,
                        severity=FindingSeverity.HIGH,
                        deterministic=False,
                        message="A recognized gene appears in drug; remapping requires review.",
                    )
                )
            else:
                normalized = self.drug_normalizer.normalize(drug)
                canonical = normalized.values.get("drug")
                if (
                    normalized.status == NormalizationStatus.NORMALIZED
                    and canonical is not None
                    and canonical != drug
                ):
                    error_type = (
                        RepairErrorType.CASING_NORMALIZATION
                        if canonical.casefold() == drug.strip().casefold()
                        else RepairErrorType.DRUG_ALIAS
                    )
                    findings.append(
                        self._replacement_finding(
                            item=item,
                            error_type=error_type,
                            field="drug",
                            observed=drug,
                            canonical=canonical,
                            method=normalized.method,
                            rule_id=(
                                "DRUG_ALIAS_EXACT"
                                if error_type == RepairErrorType.DRUG_ALIAS
                                else "CASING_NORMALIZATION"
                            ),
                        )
                    )
        return findings

    def _schema_value_findings(
        self, item: RepairRecordInput
    ) -> list[ErrorFinding]:
        record = item.record
        findings: list[ErrorFinding] = []
        for field, value in record.items():
            spec = self.fields.get(field)
            if spec is None or value is None:
                continue
            expected_type = spec.get("type")
            type_valid = (
                isinstance(value, str)
                if expected_type == "string"
                else isinstance(value, (int, float)) and not isinstance(value, bool)
                if expected_type == "number"
                else True
            )
            if not type_valid:
                findings.append(
                    self._finding(
                        error_type=RepairErrorType.INVALID_SCHEMA_VALUE,
                        rule_id="FROZEN_SCHEMA_TYPE",
                        record_ids=[item.record_id],
                        field=field,
                        observed_value=value,
                        risk=RiskLevel.MEDIUM,
                        severity=FindingSeverity.HIGH,
                        deterministic=False,
                        message=f"Field {field} does not match frozen type {expected_type}.",
                    )
                )
                continue
            allowed = spec.get("allowed")
            if allowed and value not in allowed:
                canonical = next(
                    (
                        candidate
                        for candidate in allowed
                        if isinstance(value, str)
                        and candidate.casefold() == value.casefold()
                    ),
                    None,
                )
                if canonical is not None:
                    findings.append(
                        self._replacement_finding(
                            item=item,
                            error_type=RepairErrorType.CASING_NORMALIZATION,
                            field=field,
                            observed=value,
                            canonical=canonical,
                            method="enum_casing_exact_v1",
                            rule_id="CASING_NORMALIZATION",
                        )
                    )
                else:
                    findings.append(
                        self._finding(
                            error_type=RepairErrorType.INVALID_SCHEMA_VALUE,
                            rule_id="FROZEN_SCHEMA_ALLOWED_VALUE",
                            record_ids=[item.record_id],
                            field=field,
                            observed_value=value,
                            risk=RiskLevel.MEDIUM,
                            severity=FindingSeverity.HIGH,
                            deterministic=False,
                            message=f"Field {field} is outside the frozen allowed values.",
                        )
                    )
            if expected_type == "number" and isinstance(value, (int, float)):
                minimum = spec.get("minimum")
                maximum = spec.get("maximum")
                if (minimum is not None and value < minimum) or (
                    maximum is not None and value > maximum
                ):
                    findings.append(
                        self._finding(
                            error_type=RepairErrorType.INVALID_SCHEMA_VALUE,
                            rule_id="FROZEN_SCHEMA_RANGE",
                            record_ids=[item.record_id],
                            field=field,
                            observed_value=value,
                            risk=RiskLevel.MEDIUM,
                            severity=FindingSeverity.HIGH,
                            deterministic=False,
                            message=f"Field {field} is outside the frozen numeric range.",
                        )
                    )
        return findings

    def _exact_duplicates(
        self, records: list[RepairRecordInput]
    ) -> list[ErrorFinding]:
        groups: dict[str, list[str]] = defaultdict(list)
        for item in records:
            groups[
                self._json(
                    {
                        "source_authority": (
                            item.source_authority.value
                            if isinstance(item.source_authority, SourceAuthority)
                            else str(item.source_authority)
                        ),
                        "record": item.record,
                    }
                )
            ].append(item.record_id)
        findings: list[ErrorFinding] = []
        for record_ids in groups.values():
            if len(record_ids) < 2:
                continue
            findings.append(
                self._finding(
                    error_type=RepairErrorType.EXACT_DUPLICATE,
                    rule_id="EXACT_DUPLICATE",
                    record_ids=record_ids,
                    observed_value={"duplicate_count": len(record_ids)},
                    candidate_repair={
                        "operation": "quarantine_duplicates",
                        "survivor_record_id": record_ids[0],
                        "duplicate_record_ids": record_ids[1:],
                    },
                    risk=RiskLevel.LOW,
                    severity=FindingSeverity.MEDIUM,
                    deterministic=True,
                    message=(
                        "Records are byte-for-byte equivalent at canonical record grain; "
                        "later copies can be quarantined without deleting provenance."
                    ),
                )
            )
        return findings

    def _patient_sample_conflicts(
        self, records: list[RepairRecordInput]
    ) -> list[ErrorFinding]:
        by_sample: dict[tuple[str, str], list[RepairRecordInput]] = defaultdict(list)
        for item in records:
            study_id = item.record.get("study_id")
            sample_id = item.record.get("sample_id")
            patient_id = item.record.get("patient_id")
            if study_id and sample_id and patient_id:
                by_sample[(str(study_id), str(sample_id))].append(item)
        findings: list[ErrorFinding] = []
        for (study_id, sample_id), group in by_sample.items():
            patients = {str(item.record["patient_id"]) for item in group}
            if len(patients) < 2:
                continue
            findings.append(
                self._finding(
                    error_type=RepairErrorType.PATIENT_SAMPLE_CONFLICT,
                    rule_id="LOW_CONFIDENCE_PATIENT_LINK",
                    record_ids=[item.record_id for item in group],
                    field="patient_id",
                    observed_value={
                        "study_id": study_id,
                        "sample_id": sample_id,
                        "patient_ids": sorted(patients),
                    },
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message=(
                        "One sample maps to multiple patients; no identity is selected "
                        "automatically."
                    ),
                )
            )
        return findings

    def _high_authority_conflicts(
        self, records: list[RepairRecordInput]
    ) -> list[ErrorFinding]:
        observations: dict[tuple[Any, ...], list[RepairRecordInput]] = defaultdict(list)
        for item in records:
            if item.source_authority != SourceAuthority.HIGH:
                continue
            record = item.record
            if not record.get("patient_id") and not record.get("sample_id"):
                continue
            entity = (
                record.get("study_id"),
                record.get("patient_id"),
                record.get("sample_id"),
            )
            for field in self._CONFLICT_FIELDS:
                value = record.get(field)
                if value is None:
                    continue
                dimension: tuple[Any, ...] = ()
                if field == "her2_status":
                    dimension = (record.get("her2_assay"),)
                elif field == "response":
                    dimension = (
                        record.get("response_domain"),
                        record.get("response_type"),
                    )
                observations[(*entity, field, *dimension)].append(item)
        findings: list[ErrorFinding] = []
        for key, group in observations.items():
            field = str(key[3])
            values = {self._json(item.record.get(field)) for item in group}
            sources = {item.record.get("source_id") for item in group}
            if len(values) < 2 or len(sources) < 2:
                continue
            findings.append(
                self._finding(
                    error_type=RepairErrorType.HIGH_AUTHORITY_CONFLICT,
                    rule_id="HIGH_AUTHORITY_SOURCE_CONFLICT",
                    record_ids=[item.record_id for item in group],
                    field=field,
                    observed_value=[item.record.get(field) for item in group],
                    risk=RiskLevel.HIGH,
                    severity=FindingSeverity.CRITICAL,
                    deterministic=False,
                    message=(
                        "High-authority sources disagree at the same entity and medical "
                        "dimension; the conflict remains unresolved."
                    ),
                )
            )
        return findings

    def _replacement_finding(
        self,
        *,
        item: RepairRecordInput,
        error_type: RepairErrorType,
        field: str,
        observed: Any,
        canonical: Any,
        method: str,
        rule_id: str,
    ) -> ErrorFinding:
        return self._finding(
            error_type=error_type,
            rule_id=rule_id,
            record_ids=[item.record_id],
            field=field,
            observed_value=observed,
            candidate_repair={
                "operation": "replace",
                "field": field,
                "value": canonical,
                "method": method,
            },
            risk=RiskLevel.LOW,
            severity=FindingSeverity.LOW,
            deterministic=True,
            message=f"Exact deterministic normalization is available for {field}.",
        )

    def _finding(
        self,
        *,
        error_type: RepairErrorType,
        rule_id: str,
        record_ids: list[str],
        risk: RiskLevel,
        severity: FindingSeverity,
        deterministic: bool,
        message: str,
        field: str | None = None,
        observed_value: Any = None,
        candidate_repair: dict[str, Any] | None = None,
    ) -> ErrorFinding:
        material = {
            "error_type": error_type.value,
            "rule_id": rule_id,
            "record_ids": record_ids,
            "field": field,
            "observed_value": observed_value,
            "candidate_repair": candidate_repair,
        }
        digest = hashlib.sha256(self._json(material).encode("utf-8")).hexdigest()[:24]
        return ErrorFinding(
            finding_id=f"finding:{digest}",
            error_type=error_type,
            rule_id=rule_id,
            record_ids=record_ids,
            field=field,
            observed_value=observed_value,
            candidate_repair=candidate_repair,
            risk_level=risk,
            severity=severity,
            deterministic=deterministic,
            message=message,
        )

    @staticmethod
    def _deduplicate(findings: list[ErrorFinding]) -> list[ErrorFinding]:
        return list({finding.finding_id: finding for finding in findings}.values())

    @staticmethod
    def _key(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())

    @staticmethod
    def _compact(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", "", str(value)).casefold()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _load_schema(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not isinstance(value.get("fields"), dict):
                raise ValueError("canonical schema must contain a fields mapping")
            if value.get("frozen") is not True:
                raise ValueError("canonical schema must remain frozen")
            return value
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise RepairError(
                RepairErrorCode.INVALID_CONFIGURATION,
                f"Cannot load frozen canonical schema: {exc}",
                details={"path": str(path)},
            ) from exc
