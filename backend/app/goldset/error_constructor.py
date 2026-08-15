from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from backend.app.evaluation.models import RiskLevel
from backend.app.goldset.models import (
    CurationStatus,
    ErrorCaseType,
    ErrorDraft,
    ErrorSeed,
    SourceVerificationResult,
    VerificationStatus,
)


class ErrorCaseConstructor:
    _GENE_ALIASES = {"ERBB2": "HER2", "TP53": "P53"}
    _DRUG_ALIASES = {
        "Trastuzumab": "Herceptin",
        "Pertuzumab": "Perjeta",
        "Alpelisib": "Piqray",
        "Fulvestrant": "Faslodex",
    }
    _MISSING_CANDIDATES = ("study_id", "disease", "raw_field", "raw_value")

    def construct(
        self,
        seed: ErrorSeed,
        verification: SourceVerificationResult,
        *,
        high_risk_types: set[str],
        auto_repair_types: set[str],
    ) -> tuple[list[ErrorDraft], list[str]]:
        drafts = [self._clean_control(seed, verification)]
        skipped: list[str] = []
        for error_type in seed.requested_error_types:
            mutation = self._mutation(error_type, seed.record)
            if mutation is None:
                skipped.append(
                    f"{seed.record_id}:{error_type.value}:not_applicable_to_seed"
                )
                continue
            corrupted, expected_repair, description = mutation
            risk = (
                RiskLevel.HIGH
                if error_type.value in high_risk_types
                else RiskLevel.MEDIUM
                if error_type
                in {ErrorCaseType.MISSING, ErrorCaseType.SCHEMA_MAPPING_ERROR}
                else RiskLevel.LOW
            )
            auto_allowed = (
                error_type.value in auto_repair_types and risk != RiskLevel.HIGH
            )
            drafts.append(
                self._draft(
                    seed=seed,
                    verification=verification,
                    error_type=error_type.value,
                    corrupted=corrupted,
                    expected_repair=expected_repair,
                    auto_repair_allowed=auto_allowed,
                    risk_level=risk,
                    description=description,
                )
            )
        return drafts, skipped

    def _clean_control(
        self,
        seed: ErrorSeed,
        verification: SourceVerificationResult,
    ) -> ErrorDraft:
        return self._draft(
            seed=seed,
            verification=verification,
            error_type="clean_control",
            corrupted=seed.record,
            expected_repair=None,
            auto_repair_allowed=False,
            risk_level=RiskLevel.LOW,
            description="Unmodified clean control for false-positive measurement.",
            expected_detection=False,
        )

    def _draft(
        self,
        *,
        seed: ErrorSeed,
        verification: SourceVerificationResult,
        error_type: str,
        corrupted: dict,
        expected_repair: dict | None,
        auto_repair_allowed: bool,
        risk_level: RiskLevel,
        description: str,
        expected_detection: bool = True,
    ) -> ErrorDraft:
        material = f"{seed.record_id}|{error_type}".encode("utf-8")
        status = (
            CurationStatus.HUMAN_REVIEW_REQUIRED
            if verification.status != VerificationStatus.VERIFIED
            or risk_level == RiskLevel.HIGH
            else CurationStatus.INITIAL_LABELED
        )
        return ErrorDraft(
            draft_id=f"error-draft:{hashlib.sha256(material).hexdigest()[:24]}",
            seed_record_id=seed.record_id,
            error_type=error_type,
            original_record=self._json(corrupted),
            expected_detection=expected_detection,
            expected_repair=(
                self._json(expected_repair) if expected_repair is not None else None
            ),
            auto_repair_allowed=auto_repair_allowed,
            risk_level=risk_level,
            mutation_description=description,
            source_verification=verification,
            status=status,
        )

    def _mutation(
        self,
        error_type: ErrorCaseType,
        record: dict,
    ) -> tuple[dict, dict, str] | None:
        expected = deepcopy(record)
        corrupted = deepcopy(record)
        if error_type == ErrorCaseType.DUPLICATE:
            return (
                {"records": [corrupted, deepcopy(corrupted)]},
                {"records": [expected]},
                "Duplicated the complete record exactly.",
            )
        if error_type == ErrorCaseType.MISSING:
            field = next(
                (name for name in self._MISSING_CANDIDATES if name in corrupted),
                None,
            )
            if field is None:
                return None
            corrupted.pop(field)
            return corrupted, expected, f"Removed required field {field}."
        if error_type == ErrorCaseType.GENE_ALIAS:
            value = corrupted.get("gene")
            alias = self._GENE_ALIASES.get(str(value).upper()) if value else None
            if alias is None:
                return None
            corrupted["gene"] = alias
            return corrupted, expected, f"Replaced canonical gene {value} with alias {alias}."
        if error_type == ErrorCaseType.DRUG_ALIAS:
            value = corrupted.get("drug")
            alias = self._DRUG_ALIASES.get(str(value)) if value else None
            if alias is None:
                return None
            corrupted["drug"] = alias
            return corrupted, expected, f"Replaced canonical drug {value} with alias {alias}."
        if error_type == ErrorCaseType.SCHEMA_MAPPING_ERROR:
            if "gene" in corrupted and "drug" not in corrupted:
                corrupted["drug"] = corrupted.pop("gene")
                return corrupted, expected, "Moved a gene value into the drug field."
            if "drug" in corrupted and "gene" not in corrupted:
                corrupted["gene"] = corrupted.pop("drug")
                return corrupted, expected, "Moved a drug value into the gene field."
            return None
        if error_type == ErrorCaseType.HER2_ASSAY_ERROR:
            assay = str(corrupted.get("her2_assay", "")).upper()
            raw_value = str(corrupted.get("her2_raw_value", "")).replace(" ", "")
            if assay != "IHC" or raw_value not in {"2", "2+"}:
                return None
            corrupted["her2_status"] = "Positive"
            return (
                corrupted,
                expected,
                "Changed HER2 IHC 2+ to unsafe Positive for rule testing.",
            )
        if error_type == ErrorCaseType.PROVENANCE_MISSING:
            if "source_id" not in corrupted:
                return None
            corrupted.pop("source_id")
            return corrupted, expected, "Removed source_id provenance."
        if error_type == ErrorCaseType.PATIENT_SAMPLE_CONFLICT:
            if not corrupted.get("patient_id") or not corrupted.get("sample_id"):
                return None
            corrupted["sample_id"] = f"{corrupted['sample_id']}__CONFLICT__"
            return (
                corrupted,
                expected,
                "Injected a clearly marked synthetic patient/sample conflict.",
            )
        return None

    @staticmethod
    def _json(value: dict) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
