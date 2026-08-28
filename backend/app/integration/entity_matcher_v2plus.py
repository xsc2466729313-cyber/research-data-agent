from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.app.integration.entity_matcher_v2 import EntityMatcherV2
from backend.app.integration.entity_matcher_v3 import EntityMatcherV3
from backend.app.integration.patient_sample_linker import PatientSampleLinker


@dataclass(frozen=True)
class EntityMatchV2Plus:
    """V2 match proposal with V3 feature audit and stricter identity guards."""

    left_record_id: str
    right_record_id: str
    confidence: float
    decision: str
    reason: str
    similarity_features: dict[str, float] = field(default_factory=dict)
    safety_rule_hits: list[str] = field(default_factory=list)
    decision_source: str = "V2_WITH_V3_AUDIT"


class EntityMatcherV2Plus:
    """Preserve V2 proposals; use V3 only for audit and safety tightening.

    The public benchmark has already selected V2.  This adapter deliberately
    does not fit a new ensemble on the benchmark test split.
    """

    VERSION = "entity-matcher-v2plus.0"

    def __init__(self) -> None:
        self._v2 = EntityMatcherV2()
        self._v3 = EntityMatcherV3()

    def match(
        self,
        left: Sequence[Mapping[str, Any]],
        right: Sequence[Mapping[str, Any]],
        *,
        id_field: str = "id",
        study_field: str = "study_id",
        linker_authorized: bool = False,
    ) -> list[EntityMatchV2Plus]:
        v2_matches = self._v2.match([dict(row) for row in left], [dict(row) for row in right], id_field=id_field, study_field=study_field)
        right_by_id = {str(row.get(id_field, "")): row for row in right}
        left_by_id = {str(row.get(id_field, "")): row for row in left}
        output: list[EntityMatchV2Plus] = []
        linker = PatientSampleLinker() if linker_authorized else None
        for base in v2_matches:
            left_row, right_row = left_by_id.get(base.left_id), right_by_id.get(base.right_id)
            if left_row is None or right_row is None:
                continue
            features = self._v3._features(left_row, right_row)
            audit_score, _basis = self._v3._model_score(features, left_row, right_row)
            audit_decision, audit_hits = self._v3._safety(
                left_row, right_row, audit_score, study_field=study_field, patient_sample_linker=linker
            )
            hits = list(audit_hits) + self._explicit_identity_hits(left_row, right_row)
            decision, reason = self._guard_decision(base.status, base.reason, audit_decision, hits)
            output.append(EntityMatchV2Plus(
                left_record_id=base.left_id,
                right_record_id=base.right_id,
                confidence=base.confidence,
                decision=decision,
                reason=reason,
                similarity_features=features,
                safety_rule_hits=sorted(set(hits)),
            ))
        return output

    @staticmethod
    def _explicit_identity_hits(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
        hits: list[str] = []
        if left.get("patient_id") and right.get("patient_id") and left["patient_id"] != right["patient_id"]:
            hits.append("PATIENT_ID_CONTRADICTION")
        if left.get("sample_id") and right.get("sample_id") and left["sample_id"] != right["sample_id"]:
            hits.append("SAMPLE_ID_CONTRADICTION")
        return hits

    @staticmethod
    def _guard_decision(base_status: str, base_reason: str, audit_decision: str, hits: list[str]) -> tuple[str, str]:
        blocking = {"CROSS_STUDY_JOIN_FORBIDDEN", "PATIENT_ID_CONTRADICTION", "SAMPLE_ID_CONTRADICTION"}
        if blocking.intersection(hits):
            return "REJECT", "V2 proposal blocked by explicit identity safety rule"
        if base_status != "AUTO":
            return base_status, base_reason
        if audit_decision != "LINK":
            return "REVIEW", "V2 high-confidence proposal requires V3/linker authorization before automatic use"
        return "AUTO", base_reason
