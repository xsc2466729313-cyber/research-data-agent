from __future__ import annotations

"""Deterministic final quality review for a research data package.

The Quality Agent deliberately does not mutate records.  It is a small facade
over :class:`ErrorClassifier`: deterministic algorithms detect problems and the
medical rules decide whether a problem blocks publication or needs review.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.app.evaluation.models import RiskLevel
from backend.app.models import ApiModel
from backend.app.repair.error_classifier import ErrorClassifier
from backend.app.repair.models import (
    ErrorFinding,
    ErrorClassificationResult,
    RepairErrorType,
    RepairRecordInput,
)


class QualityStatus(str, Enum):
    READY = "READY"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class QualityAgentReport(ApiModel):
    """Auditable, non-mutating quality decision.

    ``findings`` contains the original classifier findings, so callers can
    inspect the medical rule, source record and candidate action without losing
    provenance.  Scores are coverage diagnostics, not model benchmark scores.
    """

    task_id: str
    status: QualityStatus
    publish_allowed: bool
    checked_record_count: int
    findings: list[ErrorFinding]
    blocking_findings: list[str]
    review_findings: list[str]
    low_risk_findings: list[str]
    provenance_completeness: float
    summary: dict[str, int | float | str | bool]
    classifier_version: str
    medical_rules_version: str
    reviewed_at: datetime
    notice: str

    @property
    def ready(self) -> bool:
        return self.status is QualityStatus.READY


class QualityAgent:
    """Final deterministic gate over canonical-shaped records.

    High-risk medical semantics and identity conflicts remain ``REVIEW``;
    missing required/evidence fields and invalid frozen-schema values are
    ``FAIL``.  Low-risk allowlisted findings are reported but do not block
    release because the repair loop can apply them without changing meaning.
    """

    _BLOCKING_TYPES = frozenset(
        {
            RepairErrorType.MISSING_REQUIRED_FIELD,
            RepairErrorType.PROVENANCE_MISSING,
            RepairErrorType.INVALID_SCHEMA_VALUE,
        }
    )

    def __init__(self, *, classifier: ErrorClassifier | None = None) -> None:
        self.classifier = classifier or ErrorClassifier()
        # ErrorClassifier reads the frozen medical rules indirectly through the
        # canonical safety implementation.  Keep the version explicit in the
        # report for reproducibility without modifying either config file.
        self.medical_rules_version = "medical-rules-v0.1"

    def review(
        self,
        task_id: str,
        records: Iterable[RepairRecordInput | Mapping[str, Any]],
    ) -> QualityAgentReport:
        """Review records and return a publishability decision.

        A mapping is accepted as a convenience for adapters, but it must have
        ``record_id`` and ``record`` keys; no values are inferred or invented.
        """

        normalized = [self._record_input(item, index) for index, item in enumerate(records, 1)]
        classification = self.classifier.classify(task_id=task_id, records=normalized)
        return self._report(task_id, normalized, classification)

    def evaluate(
        self,
        task_id: str,
        records: Iterable[RepairRecordInput | Mapping[str, Any]],
    ) -> QualityAgentReport:
        """Alias for :meth:`review`, useful for pipeline integrations."""

        return self.review(task_id, records)

    def build(
        self,
        task_id: str,
        records: Iterable[RepairRecordInput | Mapping[str, Any]],
    ) -> QualityAgentReport:
        """Compatibility alias matching the existing gate builders."""

        return self.review(task_id, records)

    def review_request(self, request: Any) -> QualityAgentReport:
        """Review a ``RepairRequest``-like object without coupling to it."""

        return self.review(request.task_id, request.records)

    def _report(
        self,
        task_id: str,
        records: list[RepairRecordInput],
        classification: ErrorClassificationResult,
    ) -> QualityAgentReport:
        findings = classification.findings
        blocking = [
            finding.finding_id
            for finding in findings
            if finding.error_type in self._BLOCKING_TYPES
        ]
        high_risk = [
            finding.finding_id
            for finding in findings
            if finding.risk_level == RiskLevel.HIGH
            and finding.error_type not in self._BLOCKING_TYPES
        ]
        low_risk = [
            finding.finding_id
            for finding in findings
            if finding.risk_level != RiskLevel.HIGH
        ]
        if blocking:
            status = QualityStatus.FAIL
        elif high_risk:
            status = QualityStatus.REVIEW
        elif not records:
            # An empty table has no evidence from which a research result can
            # be reproduced, even though there is no row-level error to list.
            status = QualityStatus.REVIEW
        else:
            status = QualityStatus.READY

        provenance_complete = sum(
            self._has_provenance(item.record) for item in records
        )
        provenance_rate = round(
            provenance_complete / len(records) if records else 0.0,
            4,
        )
        summary: dict[str, int | float | str | bool] = {
            "record_count": len(records),
            "finding_count": len(findings),
            "blocking_finding_count": len(blocking),
            "high_risk_review_count": len(high_risk),
            "low_risk_finding_count": len(low_risk),
            "provenance_complete_record_count": provenance_complete,
            "provenance_completeness": provenance_rate,
            "publish_allowed": status is QualityStatus.READY,
            "decision_basis": "deterministic_error_classifier_and_frozen_medical_rules",
        }
        return QualityAgentReport(
            task_id=task_id,
            status=status,
            publish_allowed=status is QualityStatus.READY,
            checked_record_count=len(records),
            findings=findings,
            blocking_findings=blocking,
            review_findings=high_risk,
            low_risk_findings=low_risk,
            provenance_completeness=provenance_rate,
            summary=summary,
            classifier_version=classification.classifier_version,
            medical_rules_version=self.medical_rules_version,
            reviewed_at=datetime.now(timezone.utc),
            notice=(
                "本审核只根据冻结 schema、医学安全规则和本次记录中的真实证据作出准入判断；"
                "低风险确定性问题可交给修复流程，高风险医学语义和身份冲突保留 REVIEW，"
                "缺少必填字段、来源证据或非法值直接 FAIL。未生成任何推测成绩。"
            ),
        )

    @staticmethod
    def _has_provenance(record: Mapping[str, Any]) -> bool:
        return all(
            value is not None and str(value).strip()
            for value in (
                record.get("source_id"),
                record.get("raw_field"),
                record.get("raw_value"),
            )
        )

    @staticmethod
    def _record_input(
        item: RepairRecordInput | Mapping[str, Any], index: int
    ) -> RepairRecordInput:
        if isinstance(item, RepairRecordInput):
            return item
        if not isinstance(item, Mapping):
            raise TypeError(f"records[{index}] must be RepairRecordInput or a mapping")
        record_id = item.get("record_id")
        record = item.get("record")
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError(f"records[{index}] is missing a non-empty record_id")
        if not isinstance(record, Mapping):
            raise ValueError(f"records[{index}] is missing a mapping-valued record")
        return RepairRecordInput(
            record_id=record_id,
            source_authority=item.get("source_authority", "standard"),
            record=dict(record),
        )


__all__ = ["QualityAgent", "QualityAgentReport", "QualityStatus"]
