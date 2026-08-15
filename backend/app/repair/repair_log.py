from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.app.repair.models import (
    ErrorFinding,
    RepairChange,
    RepairExecutionStatus,
    RepairLogEntry,
    RepairPolicyDecision,
    RepairRecordState,
)


class RepairLogFactory:
    """Creates reproducible audit identities while retaining wall-clock execution time."""

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        finding: ErrorFinding,
        decision: RepairPolicyDecision,
        status: RepairExecutionStatus,
        before: list[RepairRecordState],
        after: list[RepairRecordState],
        changes: list[RepairChange],
        revalidated: bool = False,
        validation_passed: bool | None = None,
        rollback_reason: str | None = None,
        executed_at: datetime | None = None,
    ) -> RepairLogEntry:
        material = {
            "task_id": task_id,
            "finding_id": finding.finding_id,
            "decision_id": decision.decision_id,
            "error_type": finding.error_type.value,
            "action": decision.action.value,
            "execution_status": status.value,
            "before": [item.model_dump(mode="json") for item in before],
            "after": [item.model_dump(mode="json") for item in after],
            "changes": [item.model_dump(mode="json") for item in changes],
            "revalidated": revalidated,
            "validation_passed": validation_passed,
            "rollback_reason": rollback_reason,
            "policy_rule": decision.policy_rule,
            "policy_version": decision.policy_version,
        }
        audit_sha256 = hashlib.sha256(cls._json(material).encode("utf-8")).hexdigest()
        return RepairLogEntry(
            log_id=f"repair-log:{audit_sha256[:24]}",
            task_id=task_id,
            finding_id=finding.finding_id,
            decision_id=decision.decision_id,
            error_type=finding.error_type,
            action=decision.action,
            execution_status=status,
            before=before,
            after=after,
            changes=changes,
            revalidated=revalidated,
            validation_passed=validation_passed,
            rollback_reason=rollback_reason,
            policy_rule=decision.policy_rule,
            policy_version=decision.policy_version,
            audit_sha256=audit_sha256,
            executed_at=executed_at or datetime.now(timezone.utc),
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
