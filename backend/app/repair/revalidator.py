from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.app.models import CanonicalRecord
from backend.app.repair.error_classifier import ErrorClassifier
from backend.app.repair.models import (
    FindingSeverity,
    QualityValidationFinding,
    QualityValidationResult,
    RecordDisposition,
    RepairRecordInput,
    RepairRecordState,
    ValidationPhase,
)


class Revalidator:
    """Re-runs the frozen schema and medical classifier after each repair batch."""

    def __init__(self, *, classifier: ErrorClassifier | None = None) -> None:
        self.classifier = classifier or ErrorClassifier()

    def validate(
        self,
        *,
        task_id: str,
        states: list[RepairRecordState],
        phase: ValidationPhase,
    ) -> QualityValidationResult:
        checked_states = [
            state
            for state in states
            if state.disposition == RecordDisposition.PUBLISHABLE
        ]
        excluded_record_ids = [
            state.record_id
            for state in states
            if state.disposition != RecordDisposition.PUBLISHABLE
        ]
        checked = [
            RepairRecordInput(
                record_id=state.record_id,
                source_authority=state.source_authority,
                record=state.record,
            )
            for state in checked_states
        ]
        classification = self.classifier.classify(
            task_id=f"{task_id}:{phase.value}",
            records=checked,
        ) if checked else None
        findings = [
            QualityValidationFinding(
                finding_id=finding.finding_id,
                record_ids=finding.record_ids,
                rule_id=finding.rule_id,
                severity=finding.severity,
                message=finding.message,
            )
            for finding in (classification.findings if classification else [])
        ]
        classified_record_ids = {
            record_id for finding in findings for record_id in finding.record_ids
        }
        for state in checked_states:
            if state.record_id in classified_record_ids:
                continue
            try:
                CanonicalRecord.model_validate(state.record)
            except ValidationError as exc:
                messages = [
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors(include_url=False)
                ]
                material = f"{state.record_id}|{'|'.join(messages)}"
                digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
                findings.append(
                    QualityValidationFinding(
                        finding_id=f"validation-finding:{digest}",
                        record_ids=[state.record_id],
                        rule_id="CANONICAL_RECORD_MODEL",
                        severity=FindingSeverity.CRITICAL,
                        message="; ".join(messages),
                    )
                )
        failed_record_ids = list(
            dict.fromkeys(
                record_id
                for finding in findings
                for record_id in finding.record_ids
            )
        )
        material = {
            "task_id": task_id,
            "phase": phase.value,
            "records": [item.model_dump(mode="json") for item in checked],
            "excluded_record_ids": excluded_record_ids,
            "finding_ids": [item.finding_id for item in findings],
        }
        digest = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:24]
        return QualityValidationResult(
            validation_id=f"validation:{digest}",
            phase=phase,
            checked_record_count=len(checked),
            excluded_record_ids=excluded_record_ids,
            findings=findings,
            failed_record_ids=failed_record_ids,
            passed=not findings,
            validated_at=datetime.now(timezone.utc),
        )
