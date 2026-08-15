from __future__ import annotations

import hashlib

from backend.app.goldset.models import (
    CurationKind,
    ReviewPriority,
    ReviewQueueItem,
)


class ReviewQueueBuilder:
    def build(
        self,
        *,
        kind: CurationKind,
        case_id: str,
        source_id: str,
        reasons: list[str],
    ) -> ReviewQueueItem:
        unique_reasons = list(dict.fromkeys(reasons))
        high_markers = (
            "high_risk",
            "medical_rule",
            "source_unverified",
            "provenance",
            "patient_sample",
        )
        priority = (
            ReviewPriority.HIGH
            if any(marker in reason for marker in high_markers for reason in unique_reasons)
            else ReviewPriority.MEDIUM
        )
        material = f"{kind.value}|{case_id}|{'|'.join(unique_reasons)}".encode("utf-8")
        return ReviewQueueItem(
            queue_id=f"review:{hashlib.sha256(material).hexdigest()[:24]}",
            kind=kind,
            case_id=case_id,
            priority=priority,
            reasons=unique_reasons,
            source_id=source_id,
        )
