from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class SchemaMatchV3:
    source_field: str
    target_field: str
    confidence: float
    evidence: dict[str, float | str | bool] = field(default_factory=dict)
    decision: str = "REJECT"
    decision_source: str = "ALGORITHM"
    judge_reason: str | None = None


class SchemaMatcherV3:
    """Auditable schema matcher with selective judge invocation.

    The default path is deterministic and dependency-free. ``judge`` is an
    optional structured callback (for example a Qwen adapter); it is invoked
    only for ambiguous or contradictory candidates and never bypasses the
    final confidence decision.
    """

    VERSION = "schema-matcher-v3.0"
    AUTO_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.65
    JUDGE_MARGIN = 0.08

    def __init__(
        self,
        aliases: Mapping[str, Sequence[str]] | None = None,
        *,
        judge: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
        auto_threshold: float = AUTO_THRESHOLD,
        review_threshold: float = REVIEW_THRESHOLD,
    ) -> None:
        if not 0 <= review_threshold <= auto_threshold <= 1:
            raise ValueError("thresholds must satisfy 0 <= review <= auto <= 1")
        self.aliases = {self._norm(k): tuple(self._norm(v) for v in values) for k, values in (aliases or self._default_aliases()).items()}
        self.judge = judge
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold
        self.qwen_invocation_count = 0

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
    ) -> list[SchemaMatchV3]:
        source_types, target_types = source_types or {}, target_types or {}
        source_values, target_values = source_values or {}, target_values or {}
        source_descriptions, target_descriptions = source_descriptions or {}, target_descriptions or {}
        output: list[SchemaMatchV3] = []
        for source in source_fields:
            ranked = [self._score(source, target, source_types, target_types, source_values, target_values, source_descriptions, target_descriptions, source_table, target_table) for target in target_fields]
            ranked.sort(key=lambda item: (-item.confidence, item.target_field))
            if not ranked:
                continue
            best = ranked[0]
            second = ranked[1].confidence if len(ranked) > 1 else 0.0
            contradiction = bool(best.evidence.get("semantic_contradiction", False))
            ambiguous = best.confidence - second < self.JUDGE_MARGIN
            alias_uncertain = float(best.evidence.get("alias", 0.0)) >= 0.8 and best.confidence >= 0.4
            if self.judge is not None and (ambiguous or best.decision == "REVIEW" or contradiction or alias_uncertain):
                best = self._apply_judge(best, source, ranked, source_types, target_types, source_values, target_values, source_table, target_table)
            output.append(best)
        return output

    def _score(
        self,
        source: str,
        target: str,
        source_types: Mapping[str, str],
        target_types: Mapping[str, str],
        source_values: Mapping[str, Sequence[Any]],
        target_values: Mapping[str, Sequence[Any]],
        source_descriptions: Mapping[str, str],
        target_descriptions: Mapping[str, str],
        source_table: str | None,
        target_table: str | None,
    ) -> SchemaMatchV3:
        s, t = self._norm(source), self._norm(target)
        lexical = SequenceMatcher(None, s, t).ratio()
        alias = self._alias_similarity(s, t)
        value_profile = self._value_profile(source_values.get(source, ()), target_values.get(target, ()))
        type_score = self._type_score(source_types.get(source), target_types.get(target))
        cardinality = self._cardinality_score(source_values.get(source, ()), target_values.get(target, ()))
        embedding = self._semantic_similarity(source_descriptions.get(source, source), target_descriptions.get(target, target))
        table_context = self._table_context(source_table, target_table, source, target)
        ontology = self._ontology_score(s, t)
        contradiction = (type_score == 0.0 and source_types.get(source) and target_types.get(target)) or (self._medical_contradiction(s, t))
        # Declared defaults make the decision auditable: an explicit alias and
        # compatible type are stronger evidence than a name-only similarity.
        # Missing optional context is excluded from the denominator instead of
        # being treated as negative evidence.
        weighted = [(lexical, 0.14), (embedding, 0.10)]
        if alias > 0:
            weighted.append((alias, 0.33))
        if source_values.get(source) and target_values.get(target):
            weighted.extend(((value_profile, 0.10), (cardinality, 0.05)))
        if source_types.get(source) and target_types.get(target):
            weighted.append((type_score, 0.22))
        if source_table and target_table:
            weighted.append((table_context, 0.03))
        if ontology > 0:
            weighted.append((ontology, 0.03))
        available_weight = sum(weight for _value, weight in weighted)
        confidence = min(1.0, sum(value * weight for value, weight in weighted) / max(available_weight, 1e-12))
        if contradiction:
            confidence *= 0.5
        decision = "AUTO" if confidence >= self.auto_threshold and not contradiction else "REVIEW" if confidence >= self.review_threshold else "REJECT"
        return SchemaMatchV3(source, target, round(confidence, 4), {
            "lexical": round(lexical, 4), "alias": round(alias, 4), "value_profile": round(value_profile, 4),
            "type": round(type_score, 4), "cardinality": round(cardinality, 4), "embedding": round(embedding, 4),
            "table_context": round(table_context, 4), "ontology": round(ontology, 4), "semantic_contradiction": bool(contradiction),
        }, decision)

    def _apply_judge(self, best: SchemaMatchV3, source: str, ranked: list[SchemaMatchV3], source_types: Mapping[str, str], target_types: Mapping[str, str], source_values: Mapping[str, Sequence[Any]], target_values: Mapping[str, Sequence[Any]], source_table: str | None, target_table: str | None) -> SchemaMatchV3:
        self.qwen_invocation_count += 1
        payload = {
            "source_field": source, "target_candidates": [item.target_field for item in ranked[:3]],
            "source_type": source_types.get(source), "target_types": {item.target_field: target_types.get(item.target_field) for item in ranked[:3]},
            "source_values": list(source_values.get(source, ()))[:8], "target_values": {item.target_field: list(target_values.get(item.target_field, ()))[:8] for item in ranked[:3]},
            "source_table": source_table, "target_table": target_table,
        }
        try:
            result = dict(self.judge(payload)) if self.judge is not None else {}
        except Exception as exc:  # judge failure is reviewable, never fatal to matching
            return SchemaMatchV3(best.source_field, best.target_field, best.confidence, {**best.evidence, "judge_failed": True}, "REVIEW", "ALGORITHM", f"selective judge failed: {type(exc).__name__}")
        chosen = str(result.get("best_candidate") or best.target_field)
        candidate = next((item for item in ranked if item.target_field == chosen), best)
        confidence = result.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence)))
        else:
            confidence = candidate.confidence
        reason = str(result.get("reason") or "") or None
        contradiction = bool(candidate.evidence.get("semantic_contradiction", False) or result.get("conflict", False))
        decision = "AUTO" if confidence >= self.auto_threshold and not contradiction else "REVIEW" if confidence >= self.review_threshold else "REJECT"
        return SchemaMatchV3(candidate.source_field, candidate.target_field, round(confidence, 4), {**candidate.evidence, "judge_confidence": round(confidence, 4), "judge_conflict": contradiction}, decision, "QWEN_JUDGE", reason)

    @classmethod
    def _default_aliases(cls) -> dict[str, tuple[str, ...]]:
        return {"patient_age": ("age", "age_at_diagnosis"), "her2_status": ("her2", "erbb2", "her2_ihc"), "pcr": ("pathological_complete_response", "pathologic_complete_response", "response"), "patient_id": ("subject_id", "case_id")}

    @staticmethod
    def _norm(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")

    def _alias_similarity(self, source: str, target: str) -> float:
        if target in self.aliases.get(source, ()) or source in self.aliases.get(target, ()):
            return 1.0
        return 0.0

    @staticmethod
    def _value_profile(left: Sequence[Any], right: Sequence[Any]) -> float:
        a = {str(value).strip().casefold() for value in left if str(value).strip()}
        b = {str(value).strip().casefold() for value in right if str(value).strip()}
        return len(a & b) / min(len(a), len(b)) if a and b else 0.0

    @staticmethod
    def _type_score(left: str | None, right: str | None) -> float:
        if not left or not right:
            return 0.0
        return 1.0 if left.casefold() == right.casefold() else 0.0

    @staticmethod
    def _cardinality_score(left: Sequence[Any], right: Sequence[Any]) -> float:
        if not left or not right:
            return 0.0
        ratio = len(set(map(str, left))) / max(1, len(left))
        other = len(set(map(str, right))) / max(1, len(right))
        return max(0.0, 1.0 - abs(ratio - other))

    @staticmethod
    def _semantic_similarity(left: str, right: str) -> float:
        return SequenceMatcher(None, SchemaMatcherV3._norm(left), SchemaMatcherV3._norm(right)).ratio()

    @staticmethod
    def _table_context(source_table: str | None, target_table: str | None, source: str, target: str) -> float:
        if source_table and target_table and SchemaMatcherV3._norm(source_table) == SchemaMatcherV3._norm(target_table):
            return 1.0
        return 0.5 if source_table or target_table else 0.0

    @staticmethod
    def _ontology_score(source: str, target: str) -> float:
        medical = {"her2", "erbb2", "pcr", "pathological_complete_response", "patient", "sample", "mutation", "gene"}
        return 1.0 if source in medical and target in medical else 0.0

    @staticmethod
    def _medical_contradiction(source: str, target: str) -> bool:
        return ({source, target} == {"her2_status", "erbb2_cna"}) or (source == "response" and target in {"auc", "ic50"})
