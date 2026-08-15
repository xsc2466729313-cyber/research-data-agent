from __future__ import annotations

from datetime import datetime, timezone

from backend.app.models import SafetyGate
from backend.app.repair.error_classifier import ErrorClassifier
from backend.app.repair.models import (
    ErrorClassificationResult,
    RecordDisposition,
    RepairExecutionStatus,
    RepairLoopResult,
    RepairRecordInput,
    RepairRecordState,
    RepairRequest,
    ValidationPhase,
)
from backend.app.repair.repair_executor import RepairExecutionResult, RepairExecutor
from backend.app.repair.repair_policy import RepairPolicy
from backend.app.repair.revalidator import Revalidator


class RepairLoopService:
    def __init__(
        self,
        *,
        classifier: ErrorClassifier | None = None,
        policy: RepairPolicy | None = None,
        executor: RepairExecutor | None = None,
        revalidator: Revalidator | None = None,
    ) -> None:
        self.classifier = classifier or ErrorClassifier()
        self.policy = policy or RepairPolicy()
        self.executor = executor or RepairExecutor()
        self.revalidator = revalidator or Revalidator(classifier=self.classifier)

    def classify(self, request: RepairRequest) -> ErrorClassificationResult:
        return self.classifier.classify(
            task_id=request.task_id,
            records=request.records,
        )

    def run(self, request: RepairRequest) -> RepairLoopResult:
        classification = self.classify(request)
        decisions = self.policy.decide(classification.findings)
        initial_states = [
            RepairRecordState(
                record_id=item.record_id,
                source_authority=item.source_authority,
                disposition=RecordDisposition.PUBLISHABLE,
                record=item.record,
            )
            for item in request.records
        ]
        quality_before = self.revalidator.validate(
            task_id=request.task_id,
            states=initial_states,
            phase=ValidationPhase.BEFORE_REPAIR,
        )
        execution = self.executor.execute(
            task_id=request.task_id,
            records=request.records,
            findings=classification.findings,
            decisions=decisions,
        )
        first_after = self.revalidator.validate(
            task_id=request.task_id,
            states=execution.states,
            phase=ValidationPhase.AFTER_REPAIR,
        )
        validation_history = [quality_before, first_after]
        quality_after = first_after
        if not first_after.passed:
            execution = self.executor.rollback_failed(
                task_id=request.task_id,
                records=request.records,
                execution=execution,
                findings=classification.findings,
                decisions=decisions,
                failed_record_ids=set(first_after.failed_record_ids),
            )
            execution = self._exclude_unresolved_failures(
                execution,
                failed_record_ids=set(first_after.failed_record_ids),
            )
            quality_after = self.revalidator.validate(
                task_id=request.task_id,
                states=execution.states,
                phase=ValidationPhase.AFTER_ROLLBACK,
            )
            validation_history.append(quality_after)
        execution = self.executor.finalize_logs(
            task_id=request.task_id,
            execution=execution,
            findings=classification.findings,
            decisions=decisions,
            validation_passed=quality_after.passed,
        )

        by_disposition = {
            disposition: [
                RepairRecordInput(
                    record_id=state.record_id,
                    source_authority=state.source_authority,
                    record=state.record,
                )
                for state in execution.states
                if state.disposition == disposition
            ]
            for disposition in RecordDisposition
        }
        blocked_count = len(by_disposition[RecordDisposition.BLOCKED])
        review_count = len(by_disposition[RecordDisposition.REVIEW])
        rolled_back_count = sum(
            log.execution_status == RepairExecutionStatus.ROLLED_BACK
            for log in execution.logs
        )
        if blocked_count or not quality_after.passed:
            safety_gate = SafetyGate.FAIL
        elif review_count or rolled_back_count:
            safety_gate = SafetyGate.REVIEW
        else:
            safety_gate = SafetyGate.PASS
        applied_count = sum(
            log.execution_status == RepairExecutionStatus.APPLIED
            for log in execution.logs
        )
        return RepairLoopResult(
            task_id=request.task_id,
            classification=classification,
            policy_decisions=decisions,
            record_states=execution.states,
            publishable_records=by_disposition[RecordDisposition.PUBLISHABLE],
            review_records=by_disposition[RecordDisposition.REVIEW],
            blocked_records=by_disposition[RecordDisposition.BLOCKED],
            quarantined_records=by_disposition[RecordDisposition.QUARANTINED],
            repair_log=execution.logs,
            quality_before=quality_before,
            quality_after=quality_after,
            validation_history=validation_history,
            safety_gate=safety_gate,
            summary={
                "input_record_count": len(request.records),
                "finding_count": len(classification.findings),
                "automatic_repair_count": applied_count,
                "rolled_back_repair_count": rolled_back_count,
                "publishable_record_count": len(
                    by_disposition[RecordDisposition.PUBLISHABLE]
                ),
                "review_record_count": review_count,
                "blocked_record_count": blocked_count,
                "quarantined_record_count": len(
                    by_disposition[RecordDisposition.QUARANTINED]
                ),
                "post_repair_validation_passed": quality_after.passed,
                "repair_accuracy_evaluation_status": "NOT_EVALUATED",
                "repair_accuracy": None,
            },
            completed_at=datetime.now(timezone.utc),
            notice=(
                "Only exact aliases, casing, and exact duplicates on otherwise safe "
                "records were auto-repaired. Original raw_field/raw_value and source_id "
                "were retained; every mutation has before/after snapshots and was "
                "revalidated. High-risk semantics remain unchanged in review, and missing "
                "evidence is blocked. Repair Accuracy is NOT_EVALUATED until a frozen real "
                "Gold Set is supplied."
            ),
        )

    @staticmethod
    def _exclude_unresolved_failures(
        execution: RepairExecutionResult,
        *,
        failed_record_ids: set[str],
    ) -> RepairExecutionResult:
        states: list[RepairRecordState] = []
        for state in execution.states:
            updated = state.model_copy(deep=True)
            if (
                updated.record_id in failed_record_ids
                and updated.disposition == RecordDisposition.PUBLISHABLE
            ):
                updated.disposition = RecordDisposition.REVIEW
                if "post_repair_revalidation_failed" not in updated.disposition_reasons:
                    updated.disposition_reasons.append(
                        "post_repair_revalidation_failed"
                    )
            states.append(updated)
        return RepairExecutionResult(states=states, logs=execution.logs)
