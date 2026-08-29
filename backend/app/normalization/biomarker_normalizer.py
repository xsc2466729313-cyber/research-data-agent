from __future__ import annotations

import re
from typing import Any

from backend.app.normalization.models import (
    NormalizationStatus,
    NormalizedValue,
)


class BiomarkerNormalizer:
    _POSITIVE = {"positive", "pos", "+", "detected", "阳性"}
    _NEGATIVE = {"negative", "neg", "-", "notdetected", "阴性"}
    _EQUIVOCAL = {"equivocal", "borderline", "indeterminate", "可疑"}
    _UNKNOWN = {"unknown", "na", "n/a", "notavailable", "notreported", "未知"}

    def normalize(
        self,
        *,
        raw_field: str,
        raw_value: Any,
        canonical_field: str,
    ) -> NormalizedValue:
        field_key = re.sub(r"[^A-Z0-9]+", "_", raw_field.upper()).strip("_")
        value = self._value_key(raw_value)
        if not value:
            return self._unresolved("Biomarker value is empty.")

        if self._is_erbb2_cna(field_key):
            if value in {"amplified", "amplification", "amp"}:
                return NormalizedValue(
                    values={"gene": "ERBB2", "variant": "Amplification"},
                    method="erbb2_cna_amplification_v1",
                    confidence=1.0,
                    status=NormalizationStatus.NORMALIZED,
                    reason=(
                        "ERBB2 CNA is retained as a gene/variant observation and is not "
                        "mapped to HER2 IHC status."
                    ),
                )
            return NormalizedValue(
                values={"gene": "ERBB2", "variant": self._display_value(raw_value)},
                method="erbb2_cna_preserved_v1",
                confidence=0.65,
                status=NormalizationStatus.REVIEW,
                reason=(
                    "Non-amplification CNA terminology is preserved without inferring "
                    "HER2 protein status."
                ),
            )

        if "HER2" in field_key or "ERBB2" in field_key:
            assay = self._her2_assay(field_key)
            if assay == "Unknown" and value in {"0", "0+", "1", "1+", "2", "2+", "3", "3+"}:
                assay = "IHC"
            return self._normalize_her2(value=value, assay=assay, raw_value=raw_value)

        if self._is_receptor_field(field_key, "ER", canonical_field, "er_status"):
            return self._normalize_receptor(value=value, field="er_status", label="ER")
        if self._is_receptor_field(field_key, "PR", canonical_field, "pr_status"):
            return self._normalize_receptor(value=value, field="pr_status", label="PR")
        return self._unresolved(
            f"Unsupported biomarker field for deterministic mapping: {raw_field}"
        )

    def _normalize_her2(
        self, *, value: str, assay: str, raw_value: Any
    ) -> NormalizedValue:
        fragments = {
            "her2_assay": assay,
            "her2_raw_value": self._display_value(raw_value),
        }
        if assay == "IHC":
            if value in {"0", "0+", "1", "1+", *self._NEGATIVE}:
                status = "Negative"
            elif value in {"2", "2+", *self._EQUIVOCAL}:
                status = "Equivocal"
            elif value in {"3", "3+", *self._POSITIVE}:
                status = "Positive"
            elif value in self._UNKNOWN or value in {"her2low", "low"}:
                status = "Unknown"
            else:
                return NormalizedValue(
                    values={**fragments, "her2_status": "Unknown"},
                    method="her2_ihc_unresolved_v1",
                    confidence=0.5,
                    status=NormalizationStatus.REVIEW,
                    reason="Unsupported HER2 IHC value; no positive/negative inference made.",
                )
            return NormalizedValue(
                values={**fragments, "her2_status": status},
                method="her2_ihc_rule_v1",
                confidence=1.0 if status != "Unknown" else 0.6,
                status=(
                    NormalizationStatus.NORMALIZED
                    if status != "Unknown"
                    else NormalizationStatus.REVIEW
                ),
                reason=(
                    "HER2 IHC 2+ is mapped to Equivocal, never directly to Positive."
                    if value in {"2", "2+"}
                    else None
                ),
            )

        if assay in {"FISH", "ISH", "CISH", "SISH"}:
            if value in {"amplified", "amplification", "amp", *self._POSITIVE}:
                status = "Positive"
            elif value in {
                "nonamplified",
                "notamplified",
                "noamplification",
                *self._NEGATIVE,
            }:
                status = "Negative"
            elif value in self._EQUIVOCAL:
                status = "Equivocal"
            elif value in self._UNKNOWN:
                status = "Unknown"
            else:
                return NormalizedValue(
                    values={**fragments, "her2_status": "Unknown"},
                    method=f"her2_{assay.casefold()}_unresolved_v1",
                    confidence=0.5,
                    status=NormalizationStatus.REVIEW,
                    reason=(
                        "Numeric or unsupported in-situ hybridization value is preserved; "
                        "assay-specific thresholds were not inferred."
                    ),
                )
            return NormalizedValue(
                values={**fragments, "her2_status": status},
                method=f"her2_{assay.casefold()}_rule_v1",
                confidence=1.0 if status != "Unknown" else 0.6,
                status=(
                    NormalizationStatus.NORMALIZED
                    if status != "Unknown"
                    else NormalizationStatus.REVIEW
                ),
            )

        if value in self._POSITIVE | self._NEGATIVE | self._EQUIVOCAL | self._UNKNOWN:
            status = self._status_from_key(value)
            return NormalizedValue(
                values={**fragments, "her2_status": status},
                method="her2_assay_unknown_preserved_v1",
                confidence=0.7 if status != "Unknown" else 0.5,
                status=NormalizationStatus.REVIEW,
                reason="HER2 status is explicit but assay dimension is unknown.",
            )
        return NormalizedValue(
            values={**fragments, "her2_status": "Unknown"},
            method="her2_unresolved_v1",
            confidence=0.4,
            status=NormalizationStatus.UNRESOLVED,
            reason="HER2 value or assay is ambiguous.",
        )

    def _normalize_receptor(
        self, *, value: str, field: str, label: str
    ) -> NormalizedValue:
        if value in self._POSITIVE | self._NEGATIVE | self._EQUIVOCAL | self._UNKNOWN:
            status = self._status_from_key(value)
            return NormalizedValue(
                values={field: status},
                method=f"{label.casefold()}_status_exact_v1",
                confidence=1.0 if status != "Unknown" else 0.6,
                status=(
                    NormalizationStatus.NORMALIZED
                    if status != "Unknown"
                    else NormalizationStatus.REVIEW
                ),
            )
        return NormalizedValue(
            values={field: "Unknown"},
            method=f"{label.casefold()}_status_unresolved_v1",
            confidence=0.4,
            status=NormalizationStatus.REVIEW,
            reason=(
                f"{label} percentages or free text require protocol-specific review; "
                "no threshold was inferred."
            ),
        )

    @staticmethod
    def _is_erbb2_cna(field_key: str) -> bool:
        return ("ERBB2" in field_key or "HER2" in field_key) and any(
            token in field_key
            for token in ("CNA", "COPY_NUMBER", "CNV", "AMPLIFICATION")
        )

    @staticmethod
    def _her2_assay(field_key: str) -> str:
        if "IHC" in field_key:
            return "IHC"
        if "FISH" in field_key:
            return "FISH"
        if "CISH" in field_key:
            return "CISH"
        if "SISH" in field_key:
            return "SISH"
        if "ISH" in field_key:
            return "ISH"
        return "Unknown"

    @staticmethod
    def _is_receptor_field(
        field_key: str, token: str, canonical_field: str, expected: str
    ) -> bool:
        return canonical_field == expected or field_key in {
            token,
            f"{token}_STATUS",
            f"{token}_RESULT",
        }

    @classmethod
    def _status_from_key(cls, value: str) -> str:
        if value in cls._POSITIVE:
            return "Positive"
        if value in cls._NEGATIVE:
            return "Negative"
        if value in cls._EQUIVOCAL:
            return "Equivocal"
        return "Unknown"

    @staticmethod
    def _value_key(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"[\s_-]+", "", str(value).strip().casefold())

    @staticmethod
    def _display_value(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _unresolved(reason: str) -> NormalizedValue:
        return NormalizedValue(
            values={},
            method="biomarker_unresolved",
            confidence=0,
            status=NormalizationStatus.UNRESOLVED,
            reason=reason,
        )
