from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class EntityMatchV3:
    left_record_id: str
    right_record_id: str
    similarity_features: dict[str, float] = field(default_factory=dict)
    model_confidence: float = 0.0
    decision: str = "REJECT"
    basis: list[str] = field(default_factory=list)
    safety_rule_hits: list[str] = field(default_factory=list)
    candidate_generated: bool = True


@dataclass(frozen=True)
class EntityMatcherV3Config:
    """Threshold selected on train/validation data only."""

    review_threshold: float = 0.65
    auto_threshold: float = 0.90
    fit_split: str = "train_valid"


class EntityMatcherV3:
    """Blocking plus conservative entity matching with a patient safety gate.

    The matcher maximizes candidate recall, while automatic linking requires an
    explicit ``PatientSampleLinker`` authorization. Without it, even a 0.99
    model score is returned as REVIEW and cannot merge records.
    """

    VERSION = "entity-matcher-v3.0"
    AUTO_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.65

    def __init__(self, *, learned_matcher: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None, config: EntityMatcherV3Config | None = None) -> None:
        self.learned_matcher = learned_matcher
        self.config = config or EntityMatcherV3Config()
        if not 0 <= self.config.review_threshold <= self.config.auto_threshold <= 1:
            raise ValueError("entity matcher thresholds must satisfy 0 <= review <= auto <= 1")
        self.learned_invocation_count = 0

    def match(
        self,
        left: Sequence[Mapping[str, Any]],
        right: Sequence[Mapping[str, Any]],
        *,
        id_field: str = "id",
        study_field: str = "study_id",
        patient_sample_linker: Any | None = None,
    ) -> list[EntityMatchV3]:
        output: list[EntityMatchV3] = []
        for left_row in left:
            for right_row in self._blocked_candidates(left_row, right, study_field=study_field):
                features = self._features(left_row, right_row)
                score, basis = self._model_score(features, left_row, right_row)
                decision, safety = self._safety(
                    left_row, right_row, score, study_field=study_field,
                    patient_sample_linker=patient_sample_linker,
                )
                output.append(EntityMatchV3(
                    left_record_id=str(left_row.get(id_field, "")),
                    right_record_id=str(right_row.get(id_field, "")),
                    similarity_features=features,
                    model_confidence=round(score, 4),
                    decision=decision,
                    basis=basis,
                    safety_rule_hits=safety,
                ))
        return output

    def _blocked_candidates(self, row: Mapping[str, Any], right: Sequence[Mapping[str, Any]], *, study_field: str) -> list[Mapping[str, Any]]:
        study = self._value(row.get(study_field))
        same_study = [item for item in right if study and self._value(item.get(study_field)) == study]
        pool = same_study if same_study else list(right)
        if not pool:
            return []
        keys = self._blocking_keys(row)
        if not keys:
            return pool[:100]
        blocked = [item for item in pool if keys & self._blocking_keys(item)]
        # Preserve high recall when a noisy identifier is absent: retain the
        # strongest name candidates in addition to exact blocking hits.
        if blocked:
            return blocked
        return sorted(pool, key=lambda item: -self._name_similarity(row, item))[:100]

    @classmethod
    def _blocking_keys(cls, row: Mapping[str, Any]) -> set[str]:
        keys: set[str] = set()
        for field_name in ("patient_id", "sample_id", "name", "title", "email", "dob"):
            value = cls._value(row.get(field_name))
            if value:
                keys.add(f"{field_name}:{value}")
        return keys

    def _model_score(self, features: dict[str, float], left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[float, list[str]]:
        if self.learned_matcher is not None:
            self.learned_invocation_count += 1
            try:
                result = dict(self.learned_matcher({"left": dict(left), "right": dict(right), "features": features}))
                score = result.get("confidence")
                if isinstance(score, (int, float)):
                    return max(0.0, min(1.0, float(score))), [str(result.get("reason") or "learned matcher")]
            except Exception:
                pass
        score = 0.40 * features["name_similarity"] + 0.25 * features["name_containment"] + 0.25 * features["supporting_field_agreement"] + 0.10 * features["identifier_agreement"]
        basis = ["blocking candidate", "deterministic name/field similarity"]
        if features["identifier_agreement"] == 1.0:
            basis.append("exact patient/sample identifier agreement")
        return score, basis

    def _safety(self, left: Mapping[str, Any], right: Mapping[str, Any], score: float, *, study_field: str, patient_sample_linker: Any | None) -> tuple[str, list[str]]:
        hits: list[str] = []
        if self._value(left.get(study_field)) and self._value(right.get(study_field)) and self._value(left.get(study_field)) != self._value(right.get(study_field)):
            return "REJECT", ["CROSS_STUDY_JOIN_FORBIDDEN"]
        if self._value(left.get("patient_id")) and self._value(right.get("patient_id")) and self._value(left.get("patient_id")) != self._value(right.get("patient_id")):
            return "REJECT", ["PATIENT_ID_CONTRADICTION"]
        if self._value(left.get("sample_id")) and self._value(right.get("sample_id")) and self._value(left.get("sample_id")) != self._value(right.get("sample_id")):
            hits.append("SAMPLE_ID_DIFFERENCE")
        if score < self.config.review_threshold:
            return "REJECT", hits + ["LOW_CONFIDENCE"]
        if patient_sample_linker is None:
            return "REVIEW", hits + ["PATIENT_SAMPLE_LINKER_REQUIRED"]
        if score < self.config.auto_threshold:
            return "REVIEW", hits + ["BELOW_AUTO_THRESHOLD"]
        # The concrete linker is the final authority. This protocol is kept
        # intentionally narrow so a model cannot authorize itself.
        authorize = getattr(patient_sample_linker, "authorize_candidate", None)
        if callable(authorize):
            try:
                if authorize(left, right, score):
                    return "LINK", hits
            except Exception:
                pass
        return "REVIEW", hits + ["LINKER_NOT_AUTHORIZED"]

    @classmethod
    def _features(cls, left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, float]:
        left_name = cls._name(left)
        right_name = cls._name(right)
        name_similarity = SequenceMatcher(None, left_name, right_name).ratio() if left_name and right_name else 0.0
        left_tokens, right_tokens = set(left_name.split()), set(right_name.split())
        containment = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
        fields = [field for field in set(left) & set(right) if field not in {"id", "study_id", "patient_id", "sample_id", "name", "title"}]
        agreements = [1.0 if cls._value(left.get(field)) == cls._value(right.get(field)) else 0.0 for field in fields if cls._value(left.get(field)) and cls._value(right.get(field))]
        identifiers = [field for field in ("patient_id", "sample_id") if cls._value(left.get(field)) and cls._value(right.get(field))]
        return {"name_similarity": round(name_similarity, 4), "name_containment": round(containment, 4), "supporting_field_agreement": round(sum(agreements) / len(agreements) if agreements else 0.0, 4), "identifier_agreement": round(sum(cls._value(left.get(field)) == cls._value(right.get(field)) for field in identifiers) / len(identifiers) if identifiers else 0.0, 4)}

    @classmethod
    def _name(cls, row: Mapping[str, Any]) -> str:
        for field_name in ("name", "title", "full_name", "subject_name", "product_name", "beer_name", "restaurant_name", "company_name"):
            value = cls._value(row.get(field_name))
            if value:
                return value
        return ""

    @classmethod
    def _name_similarity(cls, left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
        left_name, right_name = cls._name(left), cls._name(right)
        if not left_name or not right_name:
            return 0.0
        return SequenceMatcher(None, left_name, right_name).ratio()

    @staticmethod
    def _value(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").casefold()).strip()
