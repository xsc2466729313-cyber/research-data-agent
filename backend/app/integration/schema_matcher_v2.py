from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True)
class SchemaMatch:
    source_field: str
    target_field: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    decision: str = "REJECT"


class SchemaMatcherV2:
    """Hybrid field matcher with explicit AUTO/REVIEW/REJECT safety thresholds."""

    VERSION = "schema-matcher-v2"

    def __init__(self, aliases: dict[str, tuple[str, ...]] | None = None) -> None:
        self.aliases = aliases or {
            "patient_age": ("age", "age_at_diagnosis"),
            "her2_status": ("her2", "erbb2", "her2_ihc"),
            "pcr": ("pathological_complete_response", "pathologic_complete_response", "response"),
        }

    def match(self, source_fields: list[str], target_fields: list[str], *, source_types: dict[str, str] | None = None, target_types: dict[str, str] | None = None, source_values: dict[str, list[Any]] | None = None, target_values: dict[str, list[Any]] | None = None) -> list[SchemaMatch]:
        source_types, target_types = source_types or {}, target_types or {}
        source_values, target_values = source_values or {}, target_values or {}
        output: list[SchemaMatch] = []
        for source in source_fields:
            ranked = [self._score(source, target, source_types, target_types, source_values, target_values) for target in target_fields]
            if ranked:
                output.append(sorted(ranked, key=lambda item: (-item.confidence, item.target_field))[0])
        return output

    def _score(self, source: str, target: str, st: dict[str, str], tt: dict[str, str], sv: dict[str, list[Any]], tv: dict[str, list[Any]]) -> SchemaMatch:
        s, t = self._norm(source), self._norm(target)
        lexical = SequenceMatcher(None, s, t).ratio()
        semantic = 1.0 if t in self.aliases.get(s, ()) or s in self.aliases.get(t, ()) else 0.0
        type_score = 1.0 if st.get(source) and st.get(source) == tt.get(target) else 0.0
        left, right = set(map(str, sv.get(source, []))), set(map(str, tv.get(target, [])))
        distribution = len(left & right) / max(1, min(len(left), len(right))) if left and right else 0.0
        confidence = min(1.0, 0.45 * lexical + 0.3 * semantic + 0.15 * type_score + 0.1 * distribution)
        decision = "AUTO" if confidence >= 0.90 else "REVIEW" if confidence >= 0.65 else "REJECT"
        return SchemaMatch(source, target, round(confidence, 4), {"lexical": round(lexical, 4), "semantic": round(semantic, 4), "type": type_score, "distribution": round(distribution, 4)}, decision)

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
