from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable, Mapping

from backend.app.quality_v2.error_detector import ErrorDetectionEngine, _normalize
from backend.app.quality_v2.models import (
    DetectionRisk,
    ErrorDetectionResult,
    QualityRecord,
    RepairCandidate,
    RepairCandidateResult,
)


class RepairCandidateGenerator:
    VERSION = "quality-repair-candidate-v2"
    _HIGH_RISK_FIELDS = frozenset({
        "her2_status", "her2_assay", "her2_raw_value", "er_status", "pr_status",
        "response", "response_type", "response_domain", "patient_id", "sample_id",
        "survival_outcome", "source_id", "raw_field", "raw_value",
    })
    _SAFE_TYPES = frozenset({"gene_alias", "drug_alias", "casing_normalization", "exact_duplicate"})

    def generate(self, detection: ErrorDetectionResult, records: Iterable[QualityRecord], *, task_id: str | None = None) -> RepairCandidateResult:
        by_id = {item.record_id: item for item in records}
        guarded_ids = {
            record_id
            for finding in detection.findings
            if finding.risk_level is DetectionRisk.HIGH or finding.recommended_action.value == "BLOCK"
            for record_id in finding.record_ids
        }
        candidates: list[RepairCandidate] = []
        for finding in detection.findings:
            repair = self._candidate_repair(finding)
            if not isinstance(repair, Mapping):
                continue
            for record_id in finding.record_ids:
                if record_id not in by_id:
                    continue
                if finding.error_type == "exact_duplicate" and isinstance(repair, Mapping):
                    if record_id not in set(repair.get("duplicate_record_ids", [])):
                        continue
                candidates.append(self._make(finding, record_id, repair, guarded=record_id in guarded_ids))
        return RepairCandidateResult(
            task_id=task_id or detection.task_id,
            generator_version=self.VERSION,
            candidates=candidates,
            summary={
                "finding_count": len(detection.findings),
                "candidate_count": len(candidates),
                "safe_candidate_count": sum(item.safe_to_apply for item in candidates),
                "review_candidate_count": sum(item.requires_review for item in candidates),
                "blocked_candidate_count": sum(bool(item.blocked_reason) for item in candidates),
                "high_risk_auto_repairs": 0,
            },
            generated_at=datetime.now(timezone.utc),
        )

    def generate_repair_candidates(self, detection, records, *, task_id: str | None = None):
        return self.generate(detection, records, task_id=task_id)

    def _candidate_repair(self, finding):
        # Detection is deliberately the only source of proposed values. Nothing is inferred here.
        return finding.candidate_repair

    def _make(self, finding, record_id: str, repair: Mapping[str, object] | None, *, guarded: bool = False) -> RepairCandidate:
        error_type = finding.error_type
        proposed = repair.get("value") if isinstance(repair, Mapping) else None
        high = finding.risk_level is DetectionRisk.HIGH or finding.field in self._HIGH_RISK_FIELDS
        is_duplicate = error_type == "exact_duplicate" and isinstance(repair, Mapping)
        safe = (error_type in self._SAFE_TYPES and not high and not guarded and proposed is not None) or (is_duplicate and not guarded)
        requires_review = not safe and not finding.recommended_action.value == "BLOCK"
        blocked_reason = "missing deterministic proposal, frozen/high-risk field, or guarded record" if not safe and not requires_review else None
        if guarded and error_type in self._SAFE_TYPES:
            requires_review = True
            blocked_reason = None
        if finding.recommended_action.value == "BLOCK":
            blocked_reason = "required evidence or schema validity is missing"
            requires_review = False
        digest = hashlib.sha256(f"{finding.finding_id}|{record_id}|{error_type}".encode()).hexdigest()[:20]
        return RepairCandidate(
            candidate_id=f"repair-candidate:{digest}",
            finding_id=finding.finding_id,
            error_type=error_type,
            record_id=record_id,
            field=finding.field,
            operation="quarantine" if error_type == "exact_duplicate" else "replace",
            proposed_value=proposed,
            expected_value=finding.observed_value,
            confidence=finding.detection_confidence,
            risk_level=finding.risk_level,
            safe_to_apply=safe,
            requires_review=requires_review,
            basis=[finding.rule_id, "deterministic allowlist required", "provenance preserved"],
            preserves_provenance=True,
            blocked_reason=blocked_reason,
        )


def generate_repair_candidates(records, *, task_id: str = "quality-candidates", detection: ErrorDetectionResult | None = None) -> RepairCandidateResult:
    normalized = [_normalize(item, index) for index, item in enumerate(records, 1)]
    quality_records = [QualityRecord(record_id=item.record_id, record=item.record, source_authority=item.source_authority) for item in normalized]
    detected = detection or ErrorDetectionEngine().detect(normalized, task_id=task_id)
    return RepairCandidateGenerator().generate(detected, quality_records, task_id=task_id)
