from __future__ import annotations

import hashlib
import json

from backend.app.models import EvidenceCell
from backend.app.normalization.models import (
    MappedCanonicalRecord,
    NormalizationStatus,
)


class EvidenceBuilder:
    def build(self, records: list[MappedCanonicalRecord]) -> list[EvidenceCell]:
        evidence: list[EvidenceCell] = []
        seen_ids: set[str] = set()
        for mapped in records:
            canonical = mapped.canonical_record.model_dump(mode="json")
            for field in mapped.mapped_fields:
                canonical_value = canonical[field]
                evidence_id = self.evidence_id_for(
                    mapped_record_id=mapped.mapped_record_id,
                    field=field,
                    canonical_value=canonical_value,
                )
                if evidence_id in seen_ids:
                    continue
                seen_ids.add(evidence_id)
                evidence.append(
                    EvidenceCell(
                        evidence_id=evidence_id,
                        patient_id=mapped.canonical_record.patient_id,
                        sample_id=mapped.canonical_record.sample_id,
                        field=field,
                        canonical_value=canonical_value,
                        raw_field=mapped.canonical_record.raw_field,
                        raw_value=mapped.original_raw_value,
                        source_id=mapped.canonical_record.source_id,
                        normalization_method=mapped.normalization_method,
                        confidence=mapped.canonical_record.confidence,
                        status=(
                            "verified"
                            if mapped.normalization_status
                            in {
                                NormalizationStatus.NORMALIZED,
                                NormalizationStatus.IDENTITY,
                            }
                            else "review"
                        ),
                    )
                )
        return evidence

    @staticmethod
    def evidence_id_for(
        *, mapped_record_id: str, field: str, canonical_value: object
    ) -> str:
        encoded = json.dumps(
            {
                "mapped_record_id": mapped_record_id,
                "field": field,
                "canonical_value": canonical_value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"evidence:{hashlib.sha256(encoded).hexdigest()[:24]}"
