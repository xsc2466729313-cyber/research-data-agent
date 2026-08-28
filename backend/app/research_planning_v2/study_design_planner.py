from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.metric_planner import MetricPlanningAgent
from backend.app.research_planning.models import MetricRequirement, QuestionCandidate


class StudyDesignPlannerV2:
    """Map a research type to a conservative, leakage-aware analysis plan."""

    def __init__(self, metrics: MetricPlanningAgent | None = None) -> None:
        self.metrics = metrics or MetricPlanningAgent()

    def plan(self, candidate: QuestionCandidate, papers: list[PaperRecord]) -> tuple[dict[str, object], list[MetricRequirement]]:
        if candidate.research_type == "classification_prediction":
            design = "observational_prediction"
            split = "patient_or_study_grouped_split"
            leakage = ["同一患者样本不得跨训练/验证集合", "治疗后变量不得作为治疗前预测特征"]
        elif candidate.research_type == "survival_analysis":
            design = "observational_survival"
            split = "within_cohort_temporal_or_bootstrap_validation"
            leakage = ["事件状态和随访时间必须来自同一患者队列"]
        else:
            design = "observational_association"
            split = "cohort_preserving_analysis"
            leakage = ["不同研究保留 study_id 边界，不按同名 patient_id 横向拼接"]
        return {
            "design": design,
            "analysis_unit": "patient_or_sample",
            "split_strategy": split,
            "population": candidate.population,
            "exposure": candidate.exposure,
            "outcome": candidate.outcome,
            "response_domain": "clinical",
            "leakage_controls": leakage,
            "evidence_required": True,
        }, self.metrics.plan(candidate, papers)
