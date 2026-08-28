from __future__ import annotations

import hashlib

from backend.app.quality_v2.models import (
    DetectedError,
    ReadinessReport,
    RepairCandidate,
    ReviewQueueItem,
)


class ReviewQueueBuilder:
    VERSION = "quality-review-queue-v2"

    def build(self, findings: list[DetectedError], candidates: list[RepairCandidate], readiness: ReadinessReport) -> list[ReviewQueueItem]:
        items: list[ReviewQueueItem] = []
        for finding in findings:
            if finding.recommended_action.value == "AUTO":
                continue
            priority = "HIGH" if finding.risk_level.value == "HIGH" or finding.recommended_action.value == "BLOCK" else "MEDIUM" if finding.risk_level.value == "MEDIUM" else "LOW"
            digest = hashlib.sha256(f"{finding.finding_id}|{','.join(finding.record_ids)}".encode()).hexdigest()[:20]
            items.append(ReviewQueueItem(review_id=f"review:{digest}", record_ids=finding.record_ids, finding_id=finding.finding_id, priority=priority, reason=finding.message, required_action="确认来源、医学语义或身份关系后再决定发布/修复"))
        for gate in readiness.hard_gates:
            if gate.status.value == "PASS":
                continue
            digest = hashlib.sha256(f"gate|{readiness.task_id}|{gate.gate_id}".encode()).hexdigest()[:20]
            priority = "HIGH" if gate.status.value == "FAIL" else "MEDIUM"
            items.append(ReviewQueueItem(review_id=f"review:{digest}", record_ids=gate.affected_record_ids or ["dataset"], reason=gate.evidence, required_action=f"处理硬门禁 {gate.gate_id}", priority=priority))
        rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted({item.review_id: item for item in items}.values(), key=lambda item: (rank[item.priority], item.review_id))
