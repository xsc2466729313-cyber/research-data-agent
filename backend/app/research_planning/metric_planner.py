from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.evidence import evidence_references
from backend.app.research_planning.models import EvidenceReference, MetricRequirement, QuestionCandidate


class MetricPlanningAgent:
    _METRICS: dict[str, tuple[tuple[str, str, str, tuple[str, ...]], ...]] = {
        "association": (
            ("odds_ratio", "Odds Ratio", "primary", ("odds ratio", "logistic regression")),
            ("confidence_interval_95", "95% Confidence Interval", "supporting", ("confidence interval", "95% CI")),
            ("p_value", "p-value", "supporting", ("p-value", "p value")),
        ),
        "subgroup_association": (
            ("effect_estimate", "分层效应量", "primary", ("subgroup", "interaction")),
            ("interaction_p_value", "交互检验 p-value", "supporting", ("interaction", "p-value")),
            ("confidence_interval_95", "95% Confidence Interval", "supporting", ("confidence interval", "95% CI")),
        ),
        "classification_prediction": (
            ("auroc", "AUROC", "primary", ("AUROC", "ROC curve", "area under the curve")),
            ("auprc", "AUPRC", "supporting", ("AUPRC", "precision-recall")),
            ("calibration", "Calibration", "diagnostic", ("calibration",)),
            ("sensitivity", "Sensitivity", "supporting", ("sensitivity",)),
            ("specificity", "Specificity", "supporting", ("specificity",)),
        ),
        "survival_analysis": (
            ("hazard_ratio", "Hazard Ratio", "primary", ("hazard ratio", "Cox")),
            ("confidence_interval_95", "95% Confidence Interval", "supporting", ("confidence interval", "95% CI")),
            ("log_rank", "Log-rank", "supporting", ("log-rank", "Kaplan-Meier")),
            ("c_index", "C-index", "diagnostic", ("C-index", "concordance index")),
        ),
    }

    def plan(self, candidate: QuestionCandidate, papers: list[PaperRecord]) -> list[MetricRequirement]:
        specs = self._METRICS.get(candidate.research_type, self._METRICS["association"])
        output: list[MetricRequirement] = []
        for metric_id, label, role, terms in specs:
            evidence: list[EvidenceReference] = evidence_references(
                papers,
                terms=list(terms),
                evidence_type=f"metric_definition:{metric_id}",
                limit=2,
            )
            output.append(
                MetricRequirement(
                    metric_id=metric_id,
                    label=label,
                    role=role,
                    reason=f"根据研究范式 {candidate.research_type} 的确定性指标映射选择；若论文 Methods 有定义则附在证据中。",
                    literature_evidence=evidence,
                )
            )
        return output
