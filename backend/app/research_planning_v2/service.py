from __future__ import annotations

from datetime import datetime, timezone

from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.models import ResearchTopic
from backend.app.research_planning.research_agent import ResearchAgent
from backend.app.research_planning.research_contract import ResearchContractBuilder

from .models import (
    ResearchPlanningV2Request,
    ResearchPlanningV2Response,
    ResearchQuestionCandidateV2,
    VariableSpecV2,
)
from .research_agent import ResearchAgentV2


class ResearchPlanningV2Service:
    """API facade for the composable Phase C Research Agent V2."""

    VERSION = "research-agent-v2.1"

    def __init__(self) -> None:
        self.v2_agent = ResearchAgentV2()
        self.formulation = ResearchFormulationAgent()
        self.agent = ResearchAgent(formulation=self.formulation)
        self.contract_builder = ResearchContractBuilder()

    def plan(self, request: ResearchPlanningV2Request) -> ResearchPlanningV2Response:
        return self.v2_agent.plan(request)

    def plan_legacy(self, request: ResearchPlanningV2Request) -> ResearchPlanningV2Response:
        """Retained baseline implementation for ablation and rollback."""
        topic = ResearchTopic(
            topic_id="v2-topic",
            topic=request.topic,
            domain="oncology",
            disease="breast cancer" if any(token in request.topic.casefold() for token in ("breast", "乳腺")) else None,
            ambiguity_level="high",
            created_at=datetime.now(timezone.utc),
        )
        papers = request.retrieved_papers
        candidates = self.formulation.formulate(topic, papers)
        if not candidates:
            return self._empty_response("未生成候选科研问题；需要补充问题约束或 Evidence。")
        evidence_count = sum(len(candidate.literature_evidence) for candidate in candidates)
        generation_source = "EVIDENCE_AGENT" if evidence_count else "GENERIC_FALLBACK"
        candidate_rows = [
            ResearchQuestionCandidateV2(
                candidate_id=item.candidate_id,
                question=item.question,
                research_type=item.research_type,
                population=item.population,
                exposure=item.exposure,
                outcome=item.outcome,
                rank=item.rank,
                feasibility_score=item.feasibility_score,
                evidence_refs=[ref.evidence_id if hasattr(ref, "evidence_id") else f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence],
                generation_source=generation_source,
            )
            for item in candidates
        ]
        selected = candidates[0]
        required, recommended, optional = self.contract_builder.field_planner.plan(selected, papers, topic)
        metrics = self.contract_builder.metric_planner.plan(selected, papers)
        design = {
            "research_type": selected.research_type,
            "population": selected.population,
            "exposure": selected.exposure,
            "outcome": selected.outcome,
            "analysis_unit": "patient_or_sample",
            "data_sources": request.known_data_sources,
            "constraints": request.user_constraints,
        }
        unresolved = []
        if not papers:
            unresolved.append("需要至少一个可核验论文 Evidence 后再进入正式 Research Contract。")
        unresolved.extend(item.label for item in required if item.evidence_status == "missing")
        return ResearchPlanningV2Response(
            candidate_questions=candidate_rows,
            selected_question=candidate_rows[0],
            required_fields=[self._variable(item) for item in required],
            recommended_fields=[self._variable(item) for item in recommended],
            optional_fields=[self._variable(item) for item in optional],
            study_design=design,
            metrics=[
                {
                    "metric_id": item.metric_id,
                    "role": item.role,
                    "reason": item.reason,
                    "evidence_refs": [f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence],
                }
                for item in metrics
            ],
            evidence_refs=[f"{ref.source_id}:{ref.paper_id}" for item in candidates for ref in item.literature_evidence],
            unresolved_questions=unresolved,
            question_generation_source=generation_source,
            notice=(
                "候选问题和变量已通过结构化模型；没有论文 Evidence 时仅作为 GENERIC_FALLBACK，"
                "不进入正式数据获取，也不把模板输出当作事实。"
            ),
        )

    @staticmethod
    def _variable(item: object) -> VariableSpecV2:
        return VariableSpecV2(
            field_id=item.field_id,
            role=item.role,
            reason=item.reason,
            evidence_refs=[f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence],
            availability=item.evidence_status,
            priority=item.priority.value,
        )

    @staticmethod
    def _empty_response(notice: str) -> ResearchPlanningV2Response:
        return ResearchPlanningV2Response(
            candidate_questions=[],
            study_design={},
            question_generation_source="GENERIC_FALLBACK",
            unresolved_questions=[notice],
            notice=notice,
        )
