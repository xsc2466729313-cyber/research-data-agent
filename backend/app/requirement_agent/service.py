from __future__ import annotations

from backend.app.contracts.builder import FrozenContractBuilder
from backend.app.contracts.models import (
    ClarifyRequest,
    ClarifyResponse,
    ContractCreateRequest,
    FrozenResearchContract,
    RequirementCandidate,
)
from backend.app.contracts.validator import ContractValidationError, ContractValidator
from backend.app.literature import LiteratureScanRequest
from backend.app.requirement_agent.perspectives import expand_perspectives
from backend.app.research_planning.models import QuestionSelectionRequest, TopicCreateRequest
from backend.app.research_planning.service import ResearchPlanningNotFoundError, ResearchPlanningService


class RequirementAgentService:
    """Turn a broad topic into selectable, evidence-linked data requirements."""

    def __init__(
        self,
        *,
        planning: ResearchPlanningService | None = None,
        builder: FrozenContractBuilder | None = None,
        validator: ContractValidator | None = None,
    ) -> None:
        self.planning = planning or ResearchPlanningService()
        self.builder = builder or FrozenContractBuilder()
        self.validator = validator or ContractValidator()

    def clarify(self, request: ClarifyRequest) -> ClarifyResponse:
        topic = self.planning.create_topic(TopicCreateRequest(topic=request.topic))
        scan = self.planning.scan_literature(
            topic.topic_id,
            LiteratureScanRequest(max_records=request.max_papers),
        )
        payload = self.planning.question_candidates(topic.topic_id)
        generation = "EVIDENCE_AGENT"
        if not scan.scan.papers:
            generation = "GENERIC_FALLBACK"
        elif payload.candidates and all(
            getattr(item, "generation_source", "GENERIC_FALLBACK") != "EVIDENCE_AGENT" for item in payload.candidates
        ):
            generation = "GENERIC_FALLBACK"
        elif payload.candidates and any(
            getattr(item, "generation_source", "") == "LEGACY_TEMPLATE" for item in payload.candidates
        ) and not scan.scan.papers:
            generation = "LEGACY_TEMPLATE"
        candidates = [self._candidate(item) for item in payload.candidates]
        if candidates and any(item.generation_source == "EVIDENCE_AGENT" for item in candidates):
            generation = "EVIDENCE_AGENT"
        elif candidates and all(item.generation_source == "LEGACY_TEMPLATE" for item in candidates):
            generation = "LEGACY_TEMPLATE"
        warning = payload.literature_warning
        notice = (
            "候选需求来自论文 Evidence，请选择一项后冻结 Research Contract。"
            if generation == "EVIDENCE_AGENT"
            else "没有足够论文 Evidence；下列候选仅为 GENERIC_FALLBACK，不能当作已证实的科研事实。"
        )
        return ClarifyResponse(
            topic_id=topic.topic_id,
            topic=topic.topic,
            perspectives=expand_perspectives(topic.topic),
            candidates=candidates,
            literature_warning=warning,
            paper_count=len(scan.scan.papers),
            generation_source=generation,
            notice=notice,
        )

    def create_contract(self, request: ContractCreateRequest) -> FrozenResearchContract:
        planning = self.planning.select_question(
            request.candidate_id,
            QuestionSelectionRequest(question_override=request.question_override),
        )
        topic = self.planning._topic(planning.topic_id)
        with self.planning._lock:
            candidates = list(self.planning._candidates.get(planning.topic_id, []))
        candidate = next((item for item in candidates if item.candidate_id == planning.candidate_id), None)
        return self.builder.from_planning(planning, topic=topic, candidate=candidate)

    def freeze(self, contract_id: str) -> FrozenResearchContract:
        planning = self.planning.freeze_contract(contract_id)
        topic = self.planning._topic(planning.topic_id)
        return self.builder.from_planning(planning, topic=topic)

    def get(self, contract_id: str) -> FrozenResearchContract:
        planning = self.planning.get_contract(contract_id)
        topic = self.planning._topic(planning.topic_id)
        return self.builder.from_planning(planning, topic=topic)

    @staticmethod
    def _candidate(item: object) -> RequirementCandidate:
        return RequirementCandidate(
            candidate_id=item.candidate_id,
            question=item.question,
            research_type=item.research_type,
            population=item.population,
            exposure=item.exposure,
            outcome=item.outcome,
            required_field_hints=list(getattr(item, "field_hints", []) or []),
            perspectives=list(getattr(item, "perspectives", []) or []),
            evidence_count=len(getattr(item, "literature_evidence", []) or []),
            data_availability=(
                "论文提到公开 accession" if any(getattr(item, "literature_evidence", [])) else "待核验公开数据"
            ),
            unresolved_questions=list(getattr(item, "unresolved_questions", []) or []),
            generation_source=getattr(item, "generation_source", "GENERIC_FALLBACK"),
            feasibility_score=float(item.feasibility_score),
            rank=int(item.rank),
        )


__all__ = ["RequirementAgentService", "ResearchPlanningNotFoundError", "ContractValidationError"]
