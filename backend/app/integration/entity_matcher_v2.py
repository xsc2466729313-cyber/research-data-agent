from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EntityMatch:
    left_id: str
    right_id: str
    confidence: float
    status: str
    reason: str


class EntityMatcherV2:
    """High-recall candidate generation followed by a conservative safety gate."""

    VERSION = "entity-matcher-v2"

    def match(self, left: list[dict[str, Any]], right: list[dict[str, Any]], *, id_field: str = "id", study_field: str = "study_id") -> list[EntityMatch]:
        output: list[EntityMatch] = []
        for lrow in left:
            candidates = self._candidates(lrow, right, study_field)
            for rrow in candidates:
                confidence = self._similarity(lrow, rrow)
                status, reason = self._safety(lrow, rrow, confidence, study_field)
                output.append(EntityMatch(str(lrow.get(id_field)), str(rrow.get(id_field)), round(confidence, 4), status, reason))
        return output

    def _candidates(self, row: dict[str, Any], right: list[dict[str, Any]], study_field: str) -> list[dict[str, Any]]:
        study = row.get(study_field)
        same = [item for item in right if study and item.get(study_field) == study]
        return same or right

    @staticmethod
    def _similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
        keys = (set(left) & set(right)) - {"id", "study_id"}
        scores = []
        for key in keys:
            a = re.sub(r"\W+", "", str(left[key]).casefold())
            b = re.sub(r"\W+", "", str(right[key]).casefold())
            if a and b:
                scores.append(1.0 if a == b else (0.5 if a in b or b in a else 0.0))
        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def _safety(left: dict[str, Any], right: dict[str, Any], confidence: float, study_field: str) -> tuple[str, str]:
        if left.get(study_field) and right.get(study_field) and left.get(study_field) != right.get(study_field):
            return "REJECT", "study_id 冲突，禁止跨研究自动合并"
        if left.get("patient_id") and right.get("patient_id") and left["patient_id"] != right["patient_id"] and confidence < 1:
            return "REJECT", "患者编号冲突"
        if confidence >= 0.90:
            return "AUTO", "高置信度且身份边界一致"
        if confidence >= 0.65:
            return "REVIEW", "候选相似但仍需人工确认"
        return "REJECT", "相似度低于安全阈值"
