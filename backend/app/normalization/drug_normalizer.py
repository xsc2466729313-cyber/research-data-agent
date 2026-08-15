from __future__ import annotations

import re
from typing import Any

from backend.app.normalization.models import (
    NormalizationStatus,
    NormalizedValue,
)


class DrugNormalizer:
    _ALIASES = {
        "herceptin": "Trastuzumab",
        "trastuzumab": "Trastuzumab",
        "perjeta": "Pertuzumab",
        "pertuzumab": "Pertuzumab",
        "piqray": "Alpelisib",
        "alpelisib": "Alpelisib",
        "faslodex": "Fulvestrant",
        "fulvestrant": "Fulvestrant",
        "kadcyla": "Trastuzumab emtansine",
        "t-dm1": "Trastuzumab emtansine",
        "trastuzumab emtansine": "Trastuzumab emtansine",
        "enhertu": "Trastuzumab deruxtecan",
        "t-dxd": "Trastuzumab deruxtecan",
        "trastuzumab deruxtecan": "Trastuzumab deruxtecan",
    }

    def normalize(self, raw_value: Any) -> NormalizedValue:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return NormalizedValue(
                values={},
                method="drug_unresolved",
                confidence=0,
                status=NormalizationStatus.UNRESOLVED,
                reason="Drug value is not a non-empty string.",
            )
        stripped = re.sub(r"\s+", " ", raw_value.strip())
        if "+" in stripped or re.search(r"\s(?:and|with)\s", stripped, re.I):
            return NormalizedValue(
                values={"drug": stripped},
                method="drug_combination_preserved_v1",
                confidence=0.6,
                status=NormalizationStatus.REVIEW,
                reason="Combination text is preserved; map treatment components separately.",
            )
        canonical = self._ALIASES.get(stripped.casefold())
        if canonical is None:
            return NormalizedValue(
                values={"drug": stripped},
                method="drug_identity_v1",
                confidence=0.9,
                status=NormalizationStatus.IDENTITY,
            )
        return NormalizedValue(
            values={"drug": canonical},
            method=(
                "drug_identity_v1"
                if stripped == canonical
                else "drug_alias_exact_v1"
            ),
            confidence=1.0,
            status=(
                NormalizationStatus.IDENTITY
                if stripped == canonical
                else NormalizationStatus.NORMALIZED
            ),
        )
