from __future__ import annotations

from backend.app.models import SafetyGate
from backend.app.quality_v2.error_detector import ErrorDetectionEngine
from backend.app.quality_v2.models import QualityApplyRequest, QualityRecord, QualityReviewRequest, QualityReviewResponse
from backend.app.quality_v2.readiness import ReadinessEvaluator
from backend.app.quality_v2.repair_candidate import RepairCandidateGenerator
from backend.app.quality_v2.review_queue import ReviewQueueBuilder
from backend.app.quality_v2.safe_apply import SafeRepairApplier


class QualityV2Service:
    """Three-stage quality pipeline with a non-mutating detection boundary."""

    def __init__(self) -> None:
        self.detector = ErrorDetectionEngine()
        self.generator = RepairCandidateGenerator()
        self.applier = SafeRepairApplier()
        self.readiness_evaluator = ReadinessEvaluator()
        self.queue_builder = ReviewQueueBuilder()

    def detect(self, request: QualityReviewRequest):
        return self.detector.detect(request.records, task_id=request.task_id)

    def candidates(self, request: QualityReviewRequest):
        detection = self.detect(request)
        return self.generator.generate(detection, request.records, task_id=request.task_id)

    def apply(self, request: QualityApplyRequest):
        return self.applier.apply(request.records, request.candidates, task_id=request.task_id)

    def review(self, request: QualityReviewRequest) -> QualityReviewResponse:
        detection = self.detect(request)
        candidates = self.generator.generate(detection, request.records, task_id=request.task_id)
        applied = self.applier.apply(request.records, candidates, task_id=request.task_id)
        applied_records = [item for item in applied.records if item.record_id not in set(applied.quarantined_record_ids)]
        post_detection = self.detector.detect(applied_records, task_id=f"{request.task_id}:final")
        readiness = self.readiness_evaluator.evaluate(applied_records, post_detection, task_id=request.task_id, required_fields=request.required_fields, recommended_fields=request.recommended_fields, granularity=request.granularity)
        queue = self.queue_builder.build(post_detection.findings, candidates.candidates, readiness)
        safety = SafetyGate.FAIL if readiness.status == "NOT_READY" else SafetyGate.REVIEW if readiness.status == "READY_WITH_REVIEW" or queue else SafetyGate.PASS
        return QualityReviewResponse(task_id=request.task_id, detection=detection, candidates=candidates, applied=applied, readiness=readiness, review_queue=queue, safety_gate=safety, notice="检测、修复候选与安全应用已拆分；仅低风险、确定性且来源可追溯的候选会自动执行。HER2/ER/PR、response、患者/样本身份、survival 与关键 provenance 永不自动修改；无冻结 Gold Set 时不生成 Repair Accuracy 成绩。")
