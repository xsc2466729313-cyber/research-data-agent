from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable

from backend.app.quality_v2.error_detector import ErrorDetectionEngine
from backend.app.quality_v2.models import (
    AppliedChange,
    DetectionRisk,
    QualityRecord,
    RepairCandidate,
    RepairCandidateResult,
    SafeApplyResult,
)


class SafeRepairApplier:
    VERSION = "quality-safe-apply-v2"
    _SAFE_ERROR_TYPES = frozenset({"gene_alias", "drug_alias", "casing_normalization", "exact_duplicate"})
    _HIGH_RISK_FIELDS = frozenset({"her2_status", "her2_assay", "her2_raw_value", "er_status", "pr_status", "response", "response_type", "response_domain", "patient_id", "sample_id", "survival_outcome", "source_id", "raw_field", "raw_value"})

    def apply(
        self,
        records: Iterable[QualityRecord],
        candidates: RepairCandidateResult | Iterable[RepairCandidate],
        *,
        task_id: str = "quality-apply",
    ) -> SafeApplyResult:
        original = [item.model_copy(deep=True) for item in records]
        states = {item.record_id: item for item in original}
        candidate_list = list(candidates.candidates if isinstance(candidates, RepairCandidateResult) else candidates)
        changes: list[AppliedChange] = []
        for candidate in candidate_list:
            unsafe_field = candidate.field in self._HIGH_RISK_FIELDS
            if candidate.error_type not in self._SAFE_ERROR_TYPES or unsafe_field or not candidate.safe_to_apply or candidate.risk_level is not DetectionRisk.LOW or not candidate.preserves_provenance:
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, status="BLOCKED" if candidate.blocked_reason else "SKIPPED", reason=candidate.blocked_reason or "requires human review"))
                continue
            state = states.get(candidate.record_id)
            if state is None:
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, status="BLOCKED", reason="record not found"))
                continue
            if candidate.operation == "quarantine":
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, operation=candidate.operation, status="APPLIED", reason="duplicate retained in audit and excluded from publish set"))
                continue
            if candidate.operation != "replace" or not candidate.field:
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, status="SKIPPED", reason="only safe top-level replacements are executable"))
                continue
            before = state.record.get(candidate.field)
            if candidate.expected_value is not None and before != candidate.expected_value:
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, before=before, status="SKIPPED", reason="candidate_observed_value_no_longer_matches"))
                continue
            if candidate.proposed_value is None:
                changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, before=before, status="SKIPPED", reason="candidate has no deterministic value"))
                continue
            state.record[candidate.field] = candidate.proposed_value
            changes.append(AppliedChange(candidate_id=candidate.candidate_id, record_id=candidate.record_id, field=candidate.field, operation=candidate.operation, before=before, after=candidate.proposed_value, status="APPLIED"))
        applied_records = list(states.values())
        post_detection = ErrorDetectionEngine().detect(applied_records, task_id=f"{task_id}:post")
        material = {"task_id": task_id, "records": [item.model_dump(mode="json") for item in applied_records], "changes": [item.model_dump(mode="json") for item in changes]}
        audit = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()
        quarantined = [item.record_id for item in changes if item.operation == "quarantine" and item.status == "APPLIED"]
        return SafeApplyResult(task_id=task_id, applier_version=self.VERSION, records=applied_records, changes=changes, applied_count=sum(item.status == "APPLIED" for item in changes), review_count=sum(item.status == "SKIPPED" for item in changes), blocked_count=sum(item.status == "BLOCKED" for item in changes), quarantined_record_ids=quarantined, post_detection=post_detection, audit_sha256=audit, applied_at=datetime.now(timezone.utc))

    def apply_safe_repairs(self, records, candidates, *, task_id: str = "quality-apply"):
        return self.apply(records, candidates, task_id=task_id)


def apply_safe_repairs(records, candidates: RepairCandidateResult | Iterable[RepairCandidate], *, task_id: str = "quality-apply") -> SafeApplyResult:
    normalized = [item if isinstance(item, QualityRecord) else QualityRecord.model_validate(item) for item in records]
    return SafeRepairApplier().apply(normalized, candidates, task_id=task_id)
