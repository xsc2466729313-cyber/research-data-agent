"""Phase F quality pipeline: detection, candidate generation, safe apply and readiness."""

from backend.app.quality_v2.models import (
    QualityRecord,
    ErrorDetectionResult,
    RepairCandidate,
    RepairCandidateResult,
    SafeApplyResult,
    ReadinessReport,
    QualityReviewRequest,
    QualityReviewResponse,
    QualityApplyRequest,
)
from backend.app.quality_v2.error_detector import ErrorDetectionEngine, detect_errors
from backend.app.quality_v2.repair_candidate import (
    RepairCandidateGenerator,
    generate_repair_candidates,
)
from backend.app.quality_v2.safe_apply import SafeRepairApplier, apply_safe_repairs
from backend.app.quality_v2.readiness import ReadinessEvaluator, evaluate_readiness
from backend.app.quality_v2.review_queue import ReviewQueueBuilder
from backend.app.quality_v2.service import QualityV2Service

__all__ = [
    "QualityRecord",
    "ErrorDetectionResult",
    "RepairCandidate",
    "RepairCandidateResult",
    "SafeApplyResult",
    "ReadinessReport",
    "QualityReviewRequest",
    "QualityReviewResponse",
    "QualityApplyRequest",
    "ErrorDetectionEngine",
    "detect_errors",
    "RepairCandidateGenerator",
    "generate_repair_candidates",
    "SafeRepairApplier",
    "apply_safe_repairs",
    "ReadinessEvaluator",
    "evaluate_readiness",
    "ReviewQueueBuilder",
    "QualityV2Service",
]
