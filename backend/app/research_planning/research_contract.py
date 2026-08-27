from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.field_planner import FieldPlanningAgent
from backend.app.research_planning.metric_planner import MetricPlanningAgent
from backend.app.research_planning.models import (
    QuestionCandidate,
    ResearchContract,
    ResearchTopic,
)


class ResearchContractBuilder:
    def __init__(
        self,
        *,
        field_planner: FieldPlanningAgent | None = None,
        metric_planner: MetricPlanningAgent | None = None,
    ) -> None:
        self.field_planner = field_planner or FieldPlanningAgent()
        self.metric_planner = metric_planner or MetricPlanningAgent()

    def build(
        self,
        topic: ResearchTopic,
        candidate: QuestionCandidate,
        papers: list[PaperRecord],
    ) -> ResearchContract:
        required, recommended, optional = self.field_planner.plan(candidate, papers, topic)
        metrics = self.metric_planner.plan(candidate, papers)
        missing_required = [field.label for field in required if field.evidence_status == "missing"]
        warnings: list[str] = []
        if missing_required:
            warnings.append("Required 字段缺少论文 Evidence：" + "、".join(missing_required))
        if not candidate.literature_evidence:
            warnings.append("候选问题本身尚无可核验论文 Evidence。")
        status = "NEEDS_EVIDENCE" if warnings else "READY_FOR_SOURCE_PLANNING"
        return ResearchContract(
            contract_id=f"contract-{uuid4().hex[:12]}",
            topic_id=topic.topic_id,
            candidate_id=candidate.candidate_id,
            topic=topic.topic,
            research_question=candidate.question,
            research_type=candidate.research_type,
            population=candidate.population,
            exposure=candidate.exposure,
            outcome=candidate.outcome,
            required_fields=required,
            recommended_fields=recommended,
            optional_fields=optional,
            analysis_plan=self._analysis_plan(candidate),
            metric_requirements=metrics,
            literature_evidence=candidate.literature_evidence,
            validation_status=status,
            validation_warnings=warnings,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _analysis_plan(candidate: QuestionCandidate) -> list[str]:
        if candidate.research_type == "classification_prediction":
            return [
                "按患者或独立队列划分训练/验证数据，防止同一患者样本跨集合泄漏。",
                "报告 AUROC/AUPRC 与校准，不用单一准确率替代完整评估。",
                "不同独立队列只做外部验证或纵向汇总，不按患者编号横向拼接。",
            ]
        if candidate.research_type == "survival_analysis":
            return [
                "在同一队列内核验事件状态和随访时间。",
                "估计 Hazard Ratio、95% CI，并报告 Kaplan-Meier/Log-rank。",
                "跨队列分别分析并比较方向，不把同名 patient_id 视为同一人。",
            ]
        return [
            "在同一患者/样本队列内估计主要暴露与主要结局的关系。",
            "先报告未调整效应，再按可用 Recommended 协变量进行调整。",
            "不同独立队列分别分析或纵向追加，禁止无主键的跨库患者横向合并。",
        ]
