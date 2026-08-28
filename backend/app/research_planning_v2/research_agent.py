from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.research_planning.models import ResearchTopic

from .contract_builder import ContractBuilderV2
from .evidence_extractor import EvidenceExtractorV2
from .models import ResearchPlanningV2Request, ResearchPlanningV2Response, ResearchQuestionCandidateV2, VariableSpecV2
from .question_generator import QuestionGeneratorV2
from .study_design_planner import StudyDesignPlannerV2
from .variable_designer import VariableDesignerV2


class ResearchAgentV2:
    """Single orchestration point for the Phase C research-planning contract."""

    VERSION = "research-agent-v2.1"

    def __init__(self) -> None:
        self.evidence_extractor = EvidenceExtractorV2()
        self.question_generator = QuestionGeneratorV2()
        self.variable_designer = VariableDesignerV2()
        self.study_design_planner = StudyDesignPlannerV2()
        self.contract_builder = ContractBuilderV2()

    def plan(self, request: ResearchPlanningV2Request) -> ResearchPlanningV2Response:
        topic = ResearchTopic(
            topic_id="v2-topic",
            topic=request.topic,
            domain="oncology",
            disease="breast cancer" if any(token in request.topic.casefold() for token in ("breast", "乳腺")) else None,
            ambiguity_level="high",
            created_at=datetime.now(timezone.utc),
        )
        extraction, pack = self.evidence_extractor.extract(request.topic, request.retrieved_papers, user_constraints=request.user_constraints)
        candidates, source = self.question_generator.generate(topic, request.retrieved_papers, extraction)
        if not candidates:
            return ResearchPlanningV2Response(
                candidate_questions=[],
                study_design={},
                structured_extraction=extraction,
                evidence_pack=pack,
                question_generation_source=source,
                unresolved_questions=["未生成候选科研问题；需要补充问题约束或 Evidence。"],
                audit=self._audit(request, source, pack),
                notice="未生成候选科研问题；需要补充问题约束或 Evidence。",
            )
        selected = candidates[0]
        required, recommended, optional = self.variable_designer.design(selected, request.retrieved_papers, topic)
        design, metrics = self.study_design_planner.plan(selected, request.retrieved_papers)
        candidate_rows = [self._candidate(item, source) for item in candidates]
        unresolved = [item.label for item in required if item.evidence_status == "missing"]
        if not pack:
            unresolved.insert(0, "需要至少一个可核验论文 Evidence 后再进入正式 Research Contract。")
        return ResearchPlanningV2Response(
            candidate_questions=candidate_rows,
            selected_question=candidate_rows[0],
            required_fields=[self._variable(item) for item in required],
            recommended_fields=[self._variable(item) for item in recommended],
            optional_fields=[self._variable(item) for item in optional],
            study_design={**design, "data_sources": request.known_data_sources, "constraints": request.user_constraints},
            metrics=[{"metric_id": item.metric_id, "role": item.role, "reason": item.reason, "evidence_refs": [f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence]} for item in metrics],
            # Keep the public ref compatible with the existing planning API;
            # the immutable Evidence Pack item carries the stronger hash ID.
            evidence_refs=list(dict.fromkeys(f"{item.source_id}:{item.paper_id}" for item in pack)),
            unresolved_questions=unresolved,
            question_generation_source=source,
            structured_extraction=extraction,
            evidence_pack=pack,
            fallback_template_only=source != "EVIDENCE_AGENT",
            agent_version=self.VERSION,
            audit=self._audit(request, source, pack),
            notice=("输出来自真实论文 Evidence 的结构化规划；变量仍需 Data Agent 做 runtime verification。" if pack else "候选问题和变量仅为 GENERIC_FALLBACK；没有论文 Evidence 时不进入正式数据获取。"),
        )

    @staticmethod
    def _candidate(item: Any, source: str) -> ResearchQuestionCandidateV2:
        candidate_source = source if item.literature_evidence else "GENERIC_FALLBACK"
        return ResearchQuestionCandidateV2(
            candidate_id=item.candidate_id,
            question=item.question,
            research_type=item.research_type,
            population=item.population,
            exposure=item.exposure,
            outcome=item.outcome,
            rank=item.rank,
            feasibility_score=item.feasibility_score,
            evidence_refs=[f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence],
            generation_source=candidate_source,
        )

    @staticmethod
    def _variable(item: Any) -> VariableSpecV2:
        return VariableSpecV2(
            field_id=item.field_id,
            role=item.role,
            reason=item.reason,
            evidence_refs=[f"{ref.source_id}:{ref.paper_id}" for ref in item.literature_evidence],
            availability=item.evidence_status,
            priority=item.priority.value,
        )

    @staticmethod
    def _audit(request: ResearchPlanningV2Request, source: str, pack: list[Any]) -> dict[str, object]:
        return {
            "input_paper_count": len(request.retrieved_papers),
            "evidence_item_count": len(pack),
            "question_generation_source": source,
            "qwen_invocation_count": 0,
            "runtime_data_verification": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
