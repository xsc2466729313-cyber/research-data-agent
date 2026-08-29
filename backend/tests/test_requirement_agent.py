from __future__ import annotations

from datetime import datetime, timezone

from backend.app.contracts.builder import FrozenContractBuilder
from backend.app.contracts.models import ClarifyRequest, ContractCreateRequest
from backend.app.literature import (
    LiteratureAgent,
    LiteratureProviderTrace,
    LiteratureScanRequest,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.requirement_agent import RequirementAgentService, expand_perspectives
from backend.app.research_planning import ResearchPlanningService, TopicCreateRequest
from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.models import QuestionSelectionRequest


def _paper() -> PaperRecord:
    return PaperRecord(
        paper_id="europepmc:PMC-REQ",
        source_id="europepmc:PMC-REQ",
        provider="europe_pmc",
        title="PIK3CA and HER2 in neoadjuvant breast cancer",
        abstract=(
            "This breast cancer cohort evaluated PIK3CA mutation, HER2 status and "
            "pathological complete response after neoadjuvant treatment. Data are available as GSE12345."
        ),
        source_url="https://europepmc.org/article/MED/12345678",
        pmid="12345678",
        sections={
            "methods": (
                "PIK3CA mutation and HER2 status were measured before neoadjuvant treatment. "
                "Pathological complete response (pCR) was the primary outcome."
            )
        },
        dataset_accessions=["GSE12345"],
    )


class _StubLiteratureProvider:
    name = "stub_literature"
    configured = True

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
        now = datetime.now(timezone.utc)
        return LiteratureSearchResult(
            provider=self.name,
            query=request.query,
            papers=[_paper()],
            trace=LiteratureProviderTrace(
                provider=self.name,
                query=request.query,
                requested_at=now,
                completed_at=now,
                status="success",
                source_url="https://example.org/search",
                result_count=1,
            ),
        )


def _agent() -> RequirementAgentService:
    planning = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[_StubLiteratureProvider()]))
    return RequirementAgentService(planning=planning)


def test_perspectives_cover_six_fixed_views() -> None:
    prompts = expand_perspectives("HER2-positive breast cancer neoadjuvant therapy")
    assert [item.perspective for item in prompts] == [
        "clinical",
        "molecular",
        "treatment",
        "outcome",
        "data",
        "methodology",
    ]


def test_evidence_path_does_not_require_hardcoded_three_templates() -> None:
    topic_agent = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[_StubLiteratureProvider()]))
    topic = topic_agent.create_topic(TopicCreateRequest(topic="HER2阳性乳腺癌免疫治疗与生存"))
    papers = [_paper()]
    candidates = ResearchFormulationAgent().formulate(topic, papers)
    assert 3 <= len(candidates) <= 5
    assert any("PIK3CA" in item.question for item in candidates)
    assert any(item.generation_source == "EVIDENCE_AGENT" for item in candidates)
    assert all(item.question != "治疗前基因表达特征能否预测乳腺癌新辅助治疗后的 pCR？" or item.generation_source == "EVIDENCE_AGENT" for item in candidates)


def test_no_papers_uses_generic_fallback_not_as_fact() -> None:
    topic_agent = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    topic = topic_agent.create_topic(TopicCreateRequest(topic="乳腺癌新辅助治疗"))
    candidates = ResearchFormulationAgent().formulate(topic, [])
    assert candidates
    assert all(item.generation_source == "GENERIC_FALLBACK" for item in candidates)
    assert all(item.unresolved_questions for item in candidates)


def test_clarify_select_freeze_contract() -> None:
    agent = _agent()
    clarified = agent.clarify(ClarifyRequest(topic="乳腺癌新辅助治疗"))
    assert clarified.paper_count == 1
    assert clarified.candidates
    selected = next(item for item in clarified.candidates if "PIK3CA" in item.question)
    contract = agent.create_contract(
        ContractCreateRequest(
            topic_id=clarified.topic_id,
            candidate_id=selected.candidate_id,
        )
    )
    assert contract.status == "USER_CONFIRMED"
    assert contract.required_fields
    assert "cross_cohort_patient_join_without_crosswalk" in contract.prohibited_operations
    frozen = agent.freeze(contract.contract_id)
    assert frozen.status == "FROZEN"
    assert frozen.frozen_at is not None


def test_conflict_and_missing_outcome_are_visible() -> None:
    planning = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    topic = planning.create_topic(TopicCreateRequest(topic="肝癌靶向治疗"))
    planning.scan_literature(topic.topic_id, LiteratureScanRequest(max_records=3))
    candidate = planning.question_candidates(topic.topic_id).candidates[0]
    contract = planning.select_question(candidate.candidate_id, QuestionSelectionRequest())
    frozen = FrozenContractBuilder().from_planning(contract, topic=topic, candidate=candidate)
    assert frozen.generation_source == "GENERIC_FALLBACK"
    assert frozen.unresolved_questions
