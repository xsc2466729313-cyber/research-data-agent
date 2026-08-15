from __future__ import annotations

import hashlib
from typing import Any

from backend.app.integration.conflict_detector import FieldObservation
from backend.app.integration.models import (
    FieldConflict,
    LinkDecision,
    MergedField,
    MergedRecord,
)
from backend.app.normalization.models import NormalizationStatus, NormalizedIdentity


class MergeEngine:
    def build_groups(
        self,
        *,
        identities: list[NormalizedIdentity],
        decisions: list[LinkDecision],
    ) -> dict[str, list[str]]:
        parent = {identity.raw_record_id: identity.raw_record_id for identity in identities}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for decision in decisions:
            if decision.auto_merge_allowed:
                union(decision.left_record_id, decision.right_record_id)

        grouped: dict[str, list[str]] = {}
        for raw_record_id in parent:
            grouped.setdefault(find(raw_record_id), []).append(raw_record_id)
        groups: dict[str, list[str]] = {}
        for raw_record_ids in grouped.values():
            ordered = sorted(raw_record_ids)
            token = "|".join(ordered)
            entity_key = f"entity:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:24]}"
            groups[entity_key] = ordered
        return groups

    def merge(
        self,
        *,
        groups: dict[str, list[str]],
        identities: list[NormalizedIdentity],
        observations: dict[str, dict[str, list[FieldObservation]]],
        conflicts: list[FieldConflict],
    ) -> list[MergedRecord]:
        identity_by_id = {identity.raw_record_id: identity for identity in identities}
        conflict_by_key = {
            (conflict.entity_key, conflict.semantic_key): conflict
            for conflict in conflicts
        }
        merged: list[MergedRecord] = []
        for entity_key, raw_record_ids in groups.items():
            group_identities = [identity_by_id[record_id] for record_id in raw_record_ids]
            fields: list[MergedField] = []
            conflict_ids: list[str] = []
            has_review = False
            for semantic_key, items in observations.get(entity_key, {}).items():
                values = self._unique(item.value for item in items)
                evidence_ids = list(dict.fromkeys(item.evidence_id for item in items))
                source_ids = list(dict.fromkeys(item.source_id for item in items))
                conflict = conflict_by_key.get((entity_key, semantic_key))
                if conflict is not None:
                    conflict_ids.append(conflict.conflict_id)
                    status = "unresolved"
                    selected_value = None
                elif any(
                    item.normalization_status
                    in {NormalizationStatus.REVIEW, NormalizationStatus.UNRESOLVED}
                    for item in items
                ):
                    has_review = True
                    status = "review"
                    selected_value = values[0]
                else:
                    status = "resolved"
                    selected_value = values[0]
                fields.append(
                    MergedField(
                        semantic_key=semantic_key,
                        field=items[0].field,
                        dimension=items[0].dimension,
                        selected_value=selected_value,
                        observed_values=values,
                        evidence_ids=evidence_ids,
                        source_ids=source_ids,
                        status=status,
                    )
                )
            if conflict_ids:
                status = "unresolved"
            elif has_review:
                status = "review"
            elif len(raw_record_ids) > 1:
                status = "merged"
            else:
                status = "single"
            merged.append(
                MergedRecord(
                    entity_key=entity_key,
                    raw_record_ids=raw_record_ids,
                    study_id=self._single_value(group_identities, "study_id"),
                    patient_id=self._single_optional(group_identities, "patient_id"),
                    sample_id=self._single_optional(group_identities, "sample_id"),
                    fields=fields,
                    conflict_ids=conflict_ids,
                    status=status,
                )
            )
        return merged

    @staticmethod
    def _single_value(identities: list[NormalizedIdentity], field: str) -> str:
        values = {getattr(identity, field) for identity in identities}
        if len(values) != 1:
            raise ValueError(f"Merged entity has conflicting {field} values")
        return values.pop()

    @staticmethod
    def _single_optional(
        identities: list[NormalizedIdentity], field: str
    ) -> str | None:
        values = {
            value
            for identity in identities
            if (value := getattr(identity, field)) is not None
        }
        if len(values) > 1:
            raise ValueError(f"Merged entity has conflicting {field} values")
        return next(iter(values), None)

    @staticmethod
    def _unique(values: Any) -> list[Any]:
        unique: list[Any] = []
        for value in values:
            if value not in unique:
                unique.append(value)
        return unique
