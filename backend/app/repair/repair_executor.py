from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from backend.app.repair.models import (
    ErrorFinding,
    PolicyAction,
    RecordDisposition,
    RepairChange,
    RepairExecutionStatus,
    RepairLogEntry,
    RepairPolicyDecision,
    RepairRecordInput,
    RepairRecordState,
)
from backend.app.repair.repair_log import RepairLogFactory


@dataclass
class RepairExecutionResult:
    states: list[RepairRecordState]
    logs: list[RepairLogEntry]


class RepairExecutor:
    """Applies only decisions already approved by RepairPolicy."""

    def execute(
        self,
        *,
        task_id: str,
        records: list[RepairRecordInput],
        findings: list[ErrorFinding],
        decisions: list[RepairPolicyDecision],
    ) -> RepairExecutionResult:
        state_by_id = {
            item.record_id: RepairRecordState(
                record_id=item.record_id,
                source_authority=item.source_authority,
                disposition=RecordDisposition.PUBLISHABLE,
                record=deepcopy(item.record),
            )
            for item in records
        }
        finding_by_id = {item.finding_id: item for item in findings}
        ordered = sorted(
            decisions,
            key=lambda item: (
                item.action != PolicyAction.AUTO_REPAIR,
                item.error_type.value == "exact_duplicate",
            ),
        )
        logs: list[RepairLogEntry] = []
        for decision in ordered:
            finding = finding_by_id[decision.finding_id]
            before = self._snapshots(state_by_id, finding.record_ids)
            changes: list[RepairChange] = []
            status = RepairExecutionStatus.NOT_EXECUTED
            rollback_reason: str | None = None
            if decision.action == PolicyAction.AUTO_REPAIR:
                changes, applied = self._apply_candidate(
                    state_by_id=state_by_id,
                    finding=finding,
                )
                if applied:
                    status = RepairExecutionStatus.APPLIED
                else:
                    rollback_reason = "candidate_no_longer_matches_current_record"
                    self._set_disposition(
                        state_by_id,
                        finding.record_ids,
                        RecordDisposition.REVIEW,
                        rollback_reason,
                    )
            elif decision.action == PolicyAction.BLOCK:
                self._set_disposition(
                    state_by_id,
                    finding.record_ids,
                    RecordDisposition.BLOCKED,
                    finding.rule_id,
                )
            else:
                self._set_disposition(
                    state_by_id,
                    finding.record_ids,
                    RecordDisposition.REVIEW,
                    finding.rule_id,
                )
            after = self._snapshots(state_by_id, finding.record_ids)
            logs.append(
                RepairLogFactory.create(
                    task_id=task_id,
                    finding=finding,
                    decision=decision,
                    status=status,
                    before=before,
                    after=after,
                    changes=changes,
                    rollback_reason=rollback_reason,
                )
            )
        states = [state_by_id[item.record_id] for item in records]
        return RepairExecutionResult(states=states, logs=logs)

    def rollback_failed(
        self,
        *,
        task_id: str,
        records: list[RepairRecordInput],
        execution: RepairExecutionResult,
        findings: list[ErrorFinding],
        decisions: list[RepairPolicyDecision],
        failed_record_ids: set[str],
    ) -> RepairExecutionResult:
        if not failed_record_ids:
            return execution
        originals = {item.record_id: item for item in records}
        state_by_id = {item.record_id: item.model_copy(deep=True) for item in execution.states}
        affected_log_ids = {
            log.log_id
            for log in execution.logs
            if log.execution_status == RepairExecutionStatus.APPLIED
            and any(
                change.record_id in failed_record_ids
                for change in log.changes
            )
        }
        affected_record_ids = {
            change.record_id
            for log in execution.logs
            if log.log_id in affected_log_ids
            for change in log.changes
        }
        for record_id in affected_record_ids:
            original = originals[record_id]
            state_by_id[record_id] = RepairRecordState(
                record_id=record_id,
                source_authority=original.source_authority,
                disposition=RecordDisposition.REVIEW,
                record=deepcopy(original.record),
                disposition_reasons=["post_repair_revalidation_failed"],
            )

        finding_by_id = {item.finding_id: item for item in findings}
        decision_by_id = {item.decision_id: item for item in decisions}
        logs: list[RepairLogEntry] = []
        for log in execution.logs:
            if log.log_id not in affected_log_ids:
                logs.append(log)
                continue
            finding = finding_by_id[log.finding_id]
            decision = decision_by_id[log.decision_id]
            after = self._snapshots(state_by_id, finding.record_ids)
            logs.append(
                RepairLogFactory.create(
                    task_id=task_id,
                    finding=finding,
                    decision=decision,
                    status=RepairExecutionStatus.ROLLED_BACK,
                    before=log.before,
                    after=after,
                    changes=log.changes,
                    revalidated=True,
                    validation_passed=False,
                    rollback_reason="post_repair_revalidation_failed",
                    executed_at=log.executed_at,
                )
            )
        return RepairExecutionResult(
            states=[state_by_id[item.record_id] for item in records],
            logs=logs,
        )

    @staticmethod
    def finalize_logs(
        *,
        task_id: str,
        execution: RepairExecutionResult,
        findings: list[ErrorFinding],
        decisions: list[RepairPolicyDecision],
        validation_passed: bool,
    ) -> RepairExecutionResult:
        finding_by_id = {item.finding_id: item for item in findings}
        decision_by_id = {item.decision_id: item for item in decisions}
        logs: list[RepairLogEntry] = []
        for log in execution.logs:
            if log.execution_status != RepairExecutionStatus.APPLIED:
                logs.append(log)
                continue
            logs.append(
                RepairLogFactory.create(
                    task_id=task_id,
                    finding=finding_by_id[log.finding_id],
                    decision=decision_by_id[log.decision_id],
                    status=log.execution_status,
                    before=log.before,
                    after=log.after,
                    changes=log.changes,
                    revalidated=True,
                    validation_passed=validation_passed,
                    executed_at=log.executed_at,
                )
            )
        return RepairExecutionResult(states=execution.states, logs=logs)

    def _apply_candidate(
        self,
        *,
        state_by_id: dict[str, RepairRecordState],
        finding: ErrorFinding,
    ) -> tuple[list[RepairChange], bool]:
        candidate = finding.candidate_repair or {}
        operation = candidate.get("operation")
        if operation == "replace" and len(finding.record_ids) == 1:
            record_id = finding.record_ids[0]
            state = state_by_id[record_id]
            field = candidate.get("field")
            if (
                state.disposition != RecordDisposition.PUBLISHABLE
                or not isinstance(field, str)
                or field not in state.record
                or state.record[field] != finding.observed_value
            ):
                return [], False
            before = deepcopy(state.record[field])
            after = deepcopy(candidate.get("value"))
            state.record[field] = after
            return [
                RepairChange(
                    operation="replace",
                    record_id=record_id,
                    path=f"/record/{field}",
                    before=before,
                    after=after,
                )
            ], True
        if operation == "quarantine_duplicates":
            survivor = candidate.get("survivor_record_id")
            duplicates = candidate.get("duplicate_record_ids")
            if survivor not in state_by_id or not isinstance(duplicates, list):
                return [], False
            if any(
                record_id not in state_by_id
                or state_by_id[record_id].record != state_by_id[survivor].record
                or state_by_id[record_id].disposition != RecordDisposition.PUBLISHABLE
                for record_id in duplicates
            ):
                return [], False
            changes: list[RepairChange] = []
            for record_id in duplicates:
                state = state_by_id[record_id]
                state.disposition = RecordDisposition.QUARANTINED
                self._append_reason(state, finding.rule_id)
                changes.append(
                    RepairChange(
                        operation="quarantine",
                        record_id=record_id,
                        path="/disposition",
                        before=RecordDisposition.PUBLISHABLE.value,
                        after=RecordDisposition.QUARANTINED.value,
                    )
                )
            return changes, True
        return [], False

    @classmethod
    def _set_disposition(
        cls,
        state_by_id: dict[str, RepairRecordState],
        record_ids: list[str],
        disposition: RecordDisposition,
        reason: str,
    ) -> None:
        for record_id in record_ids:
            state = state_by_id[record_id]
            if state.disposition == RecordDisposition.BLOCKED:
                cls._append_reason(state, reason)
                continue
            if disposition == RecordDisposition.BLOCKED or state.disposition == RecordDisposition.PUBLISHABLE:
                state.disposition = disposition
            cls._append_reason(state, reason)

    @staticmethod
    def _append_reason(state: RepairRecordState, reason: str) -> None:
        if reason not in state.disposition_reasons:
            state.disposition_reasons.append(reason)

    @staticmethod
    def _snapshots(
        state_by_id: dict[str, RepairRecordState],
        record_ids: list[str],
    ) -> list[RepairRecordState]:
        return [state_by_id[record_id].model_copy(deep=True) for record_id in record_ids]
