from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping

from backend.app.repair.error_classifier import ErrorClassifier
from backend.app.repair.models import RepairRecordInput
from backend.app.quality_v2.models import (
    DetectedError,
    DetectionRisk,
    ErrorDetectionResult,
    QualityRecord,
    RecommendedAction,
)


class ErrorDetectionEngine:
    """Adapter that exposes detection separately from repair execution."""

    VERSION = "quality-error-detector-v2"

    def __init__(self, classifier: ErrorClassifier | None = None) -> None:
        self.classifier = classifier or ErrorClassifier()

    def detect(
        self,
        records: Iterable[QualityRecord | RepairRecordInput | Mapping[str, object]],
        *,
        task_id: str = "quality-detection",
    ) -> ErrorDetectionResult:
        normalized = [_normalize(item, index) for index, item in enumerate(records, 1)]
        classified = self.classifier.classify(task_id=task_id, records=normalized)
        findings = [self._convert(item) for item in classified.findings]
        auto = sum(item.recommended_action is RecommendedAction.AUTO for item in findings)
        review = sum(item.recommended_action is RecommendedAction.REVIEW for item in findings)
        block = sum(item.recommended_action is RecommendedAction.BLOCK for item in findings)
        return ErrorDetectionResult(
            task_id=task_id,
            detector_version=self.VERSION,
            findings=findings,
            checked_record_count=len(normalized),
            summary={
                "finding_count": len(findings),
                "auto_candidate_count": auto,
                "review_count": review,
                "block_count": block,
                "high_risk_count": sum(item.risk_level is DetectionRisk.HIGH for item in findings),
                "detection_is_separate_from_repair": True,
            },
            detected_at=datetime.now(timezone.utc),
        )

    def detect_errors(self, records, *, task_id: str = "quality-detection") -> ErrorDetectionResult:
        return self.detect(records, task_id=task_id)

    def _convert(self, finding) -> DetectedError:
        risk = DetectionRisk.HIGH if finding.risk_level.value == "high" else DetectionRisk.MEDIUM if finding.risk_level.value == "medium" else DetectionRisk.LOW
        if finding.error_type.value in {"provenance_missing", "missing_required_field", "invalid_schema_value"}:
            action = RecommendedAction.BLOCK
        elif risk is DetectionRisk.HIGH:
            action = RecommendedAction.REVIEW
        elif finding.deterministic and finding.candidate_repair is not None:
            action = RecommendedAction.AUTO
        else:
            action = RecommendedAction.REVIEW
        confidence = 0.99 if finding.deterministic else 0.82 if risk is DetectionRisk.HIGH else 0.72
        evidence = [finding.rule_id, f"record_ids={','.join(finding.record_ids)}"]
        return DetectedError(
            finding_id=finding.finding_id,
            record_ids=finding.record_ids,
            field=finding.field,
            error_type=finding.error_type.value,
            rule_id=finding.rule_id,
            detection_confidence=confidence,
            risk_level=risk,
            severity=finding.severity.value,
            deterministic=finding.deterministic,
            observed_value=finding.observed_value,
            candidate_repair=finding.candidate_repair,
            evidence=evidence,
            recommended_action=action,
            message=finding.message,
        )


def _normalize(item, index: int) -> RepairRecordInput:
    if isinstance(item, RepairRecordInput):
        return item
    if isinstance(item, QualityRecord):
        return RepairRecordInput(record_id=item.record_id, record=item.record, source_authority=item.source_authority)
    if not isinstance(item, Mapping):
        raise TypeError(f"records[{index}] must be a QualityRecord or mapping")
    return RepairRecordInput(
        record_id=str(item.get("record_id") or f"record-{index}"),
        record=dict(item.get("record") or item),
        source_authority=item.get("source_authority", "standard"),
    )


def detect_errors(records, *, task_id: str = "quality-detection", classifier: ErrorClassifier | None = None) -> ErrorDetectionResult:
    return ErrorDetectionEngine(classifier=classifier).detect(records, task_id=task_id)
