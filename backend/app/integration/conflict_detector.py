from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from backend.app.evidence import EvidenceBuilder
from backend.app.integration.models import FieldConflict
from backend.app.normalization.models import (
    MappedCanonicalRecord,
    NormalizationStatus,
    SourceAuthority,
)


@dataclass(frozen=True)
class FieldObservation:
    raw_record_id: str
    mapped_record_id: str
    semantic_key: str
    field: str
    dimension: str
    value: Any
    evidence_id: str
    source_id: str
    source_authority: SourceAuthority
    normalization_status: NormalizationStatus


class ConflictDetector:
    def collect_observations(
        self,
        *,
        groups: dict[str, list[str]],
        mapped_records: list[MappedCanonicalRecord],
    ) -> dict[str, dict[str, list[FieldObservation]]]:
        entity_by_raw_id = {
            raw_record_id: entity_key
            for entity_key, raw_record_ids in groups.items()
            for raw_record_id in raw_record_ids
        }
        observations: dict[str, dict[str, list[FieldObservation]]] = {
            entity_key: {} for entity_key in groups
        }
        for mapped in mapped_records:
            entity_key = entity_by_raw_id[mapped.raw_record_id]
            canonical = mapped.canonical_record.model_dump(mode="json")
            for field in mapped.mapped_fields:
                dimension = self._dimension(canonical=canonical, field=field)
                semantic_key = f"{field}|{dimension}"
                observation = FieldObservation(
                    raw_record_id=mapped.raw_record_id,
                    mapped_record_id=mapped.mapped_record_id,
                    semantic_key=semantic_key,
                    field=field,
                    dimension=dimension,
                    value=canonical[field],
                    evidence_id=EvidenceBuilder.evidence_id_for(
                        mapped_record_id=mapped.mapped_record_id,
                        field=field,
                        canonical_value=canonical[field],
                    ),
                    source_id=mapped.canonical_record.source_id,
                    source_authority=mapped.source_authority,
                    normalization_status=mapped.normalization_status,
                )
                observations[entity_key].setdefault(semantic_key, []).append(
                    observation
                )
        return observations

    def detect(
        self,
        observations: dict[str, dict[str, list[FieldObservation]]],
    ) -> list[FieldConflict]:
        conflicts: list[FieldConflict] = []
        for entity_key, fields in observations.items():
            for semantic_key, items in fields.items():
                values = self._unique(item.value for item in items)
                if len(values) < 2:
                    continue
                high_sources_by_value: dict[str, set[str]] = {}
                for item in items:
                    if item.source_authority == SourceAuthority.HIGH:
                        high_sources_by_value.setdefault(
                            self._value_token(item.value), set()
                        ).add(item.source_id)
                distinct_high_sources = {
                    source_id
                    for source_ids in high_sources_by_value.values()
                    for source_id in source_ids
                }
                high_authority_conflict = (
                    len(high_sources_by_value) >= 2
                    and len(distinct_high_sources) >= 2
                )
                evidence_ids = list(dict.fromkeys(item.evidence_id for item in items))
                source_ids = list(dict.fromkeys(item.source_id for item in items))
                token = json.dumps(
                    {
                        "entity_key": entity_key,
                        "semantic_key": semantic_key,
                        "values": values,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                conflicts.append(
                    FieldConflict(
                        conflict_id=(
                            "conflict:"
                            + hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
                        ),
                        entity_key=entity_key,
                        semantic_key=semantic_key,
                        field=items[0].field,
                        dimension=items[0].dimension,
                        values=values,
                        evidence_ids=evidence_ids,
                        source_ids=source_ids,
                        high_authority_conflict=high_authority_conflict,
                        reason=(
                            "Conflicting values are supported by multiple high-authority "
                            "sources; automatic selection is forbidden."
                            if high_authority_conflict
                            else "Conflicting normalized values require review; no value selected."
                        ),
                    )
                )
        return conflicts

    @staticmethod
    def _dimension(*, canonical: dict[str, Any], field: str) -> str:
        if field in {"her2_status", "her2_raw_value"}:
            return f"assay={canonical.get('her2_assay') or 'Unknown'}"
        if field == "her2_assay":
            return f"assay={canonical.get('her2_assay') or 'Unknown'}"
        if field in {"response", "response_type", "response_domain"}:
            return (
                f"domain={canonical.get('response_domain') or 'Unknown'};"
                f"type={canonical.get('response_type') or 'Unknown'}"
            )
        if field in {"variant", "mutation_status"}:
            return (
                f"gene={canonical.get('gene') or 'Unknown'};"
                f"variant={canonical.get('variant') or 'Unknown'}"
            )
        if field == "gene":
            return f"gene={canonical.get('gene') or 'Unknown'}"
        if field == "drug":
            return f"drug={canonical.get('drug') or 'Unknown'}"
        if field == "treatment":
            return f"treatment={canonical.get('treatment') or 'Unknown'}"
        return "default"

    @classmethod
    def _unique(cls, values: Any) -> list[Any]:
        unique: dict[str, Any] = {}
        for value in values:
            unique.setdefault(cls._value_token(value), value)
        return list(unique.values())

    @staticmethod
    def _value_token(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
