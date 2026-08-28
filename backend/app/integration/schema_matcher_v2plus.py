from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.app.integration.schema_matcher_v2 import SchemaMatcherV2
from backend.app.integration.schema_matcher_v3 import SchemaMatcherV3


@dataclass(frozen=True)
class SchemaMatchV2Plus:
    """V2 proposal with V3 audit evidence and non-bypassable safety guards."""

    source_field: str
    target_field: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    decision: str = "REJECT"
    decision_source: str = "V2_WITH_V3_AUDIT"
    safety_rule_hits: list[str] = field(default_factory=list)


class SchemaMatcherV2Plus:
    """Keep the validated V2 ranking while adding V3 audit and safety evidence.

    This is intentionally not a score-level ensemble.  Choosing weights from
    the public test tasks after seeing their labels would make the reported
    comparison optimistic.  V2 remains the selection path; V3 supplies only
    explainable evidence and can make an unsafe automatic proposal stricter.
    """

    VERSION = "schema-matcher-v2plus.0"

    def __init__(self) -> None:
        self._v2 = SchemaMatcherV2()
        self._v3 = SchemaMatcherV3()

    def match(
        self,
        source_fields: Sequence[str],
        target_fields: Sequence[str],
        *,
        source_types: Mapping[str, str] | None = None,
        target_types: Mapping[str, str] | None = None,
        source_values: Mapping[str, Sequence[Any]] | None = None,
        target_values: Mapping[str, Sequence[Any]] | None = None,
        source_table: str | None = None,
        target_table: str | None = None,
        source_descriptions: Mapping[str, str] | None = None,
        target_descriptions: Mapping[str, str] | None = None,
    ) -> list[SchemaMatchV2Plus]:
        source_types, target_types = source_types or {}, target_types or {}
        source_values, target_values = source_values or {}, target_values or {}
        source_descriptions, target_descriptions = source_descriptions or {}, target_descriptions or {}
        base_matches = self._v2.match(
            list(source_fields),
            list(target_fields),
            source_types=dict(source_types),
            target_types=dict(target_types),
            source_values={key: list(values) for key, values in source_values.items()},
            target_values={key: list(values) for key, values in target_values.items()},
        )
        output: list[SchemaMatchV2Plus] = []
        for base in base_matches:
            audit = self._v3._score(
                base.source_field, base.target_field, source_types, target_types,
                source_values, target_values, source_descriptions, target_descriptions,
                source_table, target_table,
            )
            hits = self._safety_hits(base.source_field, base.target_field, source_values, audit.evidence)
            decision = self._guard_decision(base.decision, hits)
            output.append(SchemaMatchV2Plus(
                source_field=base.source_field,
                target_field=base.target_field,
                confidence=base.confidence,
                evidence={"v2": base.evidence, "v3_audit": audit.evidence},
                decision=decision,
                safety_rule_hits=hits,
            ))
        return output

    @classmethod
    def _safety_hits(
        cls,
        source: str,
        target: str,
        source_values: Mapping[str, Sequence[Any]],
        audit: Mapping[str, Any],
    ) -> list[str]:
        normalized_source, normalized_target = cls._norm(source), cls._norm(target)
        values = {cls._norm(value) for value in source_values.get(source, ()) if cls._norm(value)}
        hits: list[str] = []
        if "erbb2" in normalized_source and any(token in normalized_source for token in ("cna", "cnv", "copy_number")) and normalized_target == "her2_status":
            hits.append("ERBB2_CNA_NOT_IHC")
        if "her2" in normalized_source and "ihc" in normalized_source and normalized_target == "her2_status" and any(value in {"2", "2_plus", "2plus"} for value in values):
            hits.append("HER2_IHC_2PLUS")
        if normalized_source == "response" and normalized_target in {"auc", "ic50", "viability"}:
            hits.append("CROSS_DOMAIN_RESPONSE")
        if bool(audit.get("semantic_contradiction")):
            hits.append("SEMANTIC_CONTRADICTION")
        return hits

    @staticmethod
    def _guard_decision(base_decision: str, hits: list[str]) -> str:
        if any(hit in {"ERBB2_CNA_NOT_IHC", "CROSS_DOMAIN_RESPONSE"} for hit in hits):
            return "REJECT"
        if hits and base_decision == "AUTO":
            return "REVIEW"
        return base_decision

    @staticmethod
    def _norm(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
