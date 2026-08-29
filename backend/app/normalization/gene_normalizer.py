from __future__ import annotations

import re
from typing import Any

from backend.app.normalization.models import (
    NormalizationStatus,
    NormalizedValue,
)


class GeneNormalizer:
    """Deterministic, deliberately small alias normalizer."""

    _ALIASES = {
        "HER2": "ERBB2",
        "HER-2": "ERBB2",
        "ERBB-2": "ERBB2",
        "C-ERBB2": "ERBB2",
        "P53": "TP53",
        "PGR": "PGR",
    }
    _SYMBOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,31}$")

    def normalize(self, raw_value: Any) -> NormalizedValue:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return NormalizedValue(
                values={},
                method="gene_unresolved",
                confidence=0,
                status=NormalizationStatus.UNRESOLVED,
                reason="Gene value is not a non-empty string.",
            )
        stripped = raw_value.strip()
        alias_key = stripped.upper()
        if alias_key in self._ALIASES:
            return NormalizedValue(
                values={"gene": self._ALIASES[alias_key]},
                method="gene_alias_exact_v1",
                confidence=1.0,
                status=NormalizationStatus.NORMALIZED,
            )
        if not self._SYMBOL_PATTERN.fullmatch(stripped):
            return NormalizedValue(
                values={},
                method="gene_unresolved",
                confidence=0.4,
                status=NormalizationStatus.UNRESOLVED,
                reason="Gene value does not match the supported symbol syntax.",
            )
        canonical = stripped.upper()
        return NormalizedValue(
            values={"gene": canonical},
            method=(
                "gene_identity_v1" if canonical == stripped else "gene_symbol_casing_v1"
            ),
            confidence=0.98,
            status=(
                NormalizationStatus.IDENTITY
                if canonical == stripped
                else NormalizationStatus.NORMALIZED
            ),
        )
