from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.literature.models import PaperRecord
from backend.app.main import app
from backend.app.research_planning_v2 import (
    EvidenceExtractorV2,
    ResearchPlanningV2Request,
    ResearchPlanningV2Service,
)


def _paper() -> PaperRecord:
    return PaperRecord(
        paper_id="pmid:1",
        source_id="europepmc:pmid:1",
        provider="europe_pmc",
        title="PIK3CA HER2 neoadjuvant breast cancer response",
        source_url="https://europepmc.org/article/MED/1",
        abstract="PIK3CA and HER2 were evaluated for pathological complete response after neoadjuvant treatment.",
        sections={"methods": "PIK3CA HER2 pathological complete response neoadjuvant treatment"},
        dataset_accessions=["GSE76360"],
    )


def test_research_planning_v2_labels_evidence_driven_output_and_variable_reasons() -> None:
    result = ResearchPlanningV2Service().plan(
        ResearchPlanningV2Request(
            topic="HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应",
            retrieved_papers=[_paper()],
            known_data_sources=["GEO"],
        )
    )
    assert result.candidate_questions
    assert result.question_generation_source == "EVIDENCE_AGENT"
    assert result.selected_question is not None
    assert result.required_fields
    assert all(item.role and item.reason and item.priority for item in result.required_fields)
    assert result.evidence_refs


def test_research_planning_v2_without_papers_is_explicit_fallback_and_unresolved() -> None:
    result = ResearchPlanningV2Service().plan(ResearchPlanningV2Request(topic="乳腺癌新辅助治疗"))
    assert result.question_generation_source == "GENERIC_FALLBACK"
    assert result.unresolved_questions
    assert "正式 Research Contract" in result.unresolved_questions[0]


def test_research_planning_v2_api_returns_structured_contract_slots() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v2/research/plan",
        json={"topic": "HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应", "retrieved_papers": [_paper().model_dump(mode="json")]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_question"]["question"]
    assert payload["required_fields"][0]["reason"]
    assert payload["question_generation_source"] == "EVIDENCE_AGENT"
    assert payload["structured_extraction"]["research_type"] == "association"
    assert payload["evidence_pack"][0]["source_id"] == "europepmc:pmid:1"
    assert payload["evidence_pack"][0]["raw_field"] == "paper.section"
    assert payload["audit"]["qwen_invocation_count"] == 0


def test_evidence_extractor_keeps_real_source_and_deterministic_evidence_id() -> None:
    extractor = EvidenceExtractorV2()
    first, pack = extractor.extract("乳腺癌 PIK3CA pCR", [_paper()])
    second, pack_again = extractor.extract("乳腺癌 PIK3CA pCR", [_paper()])
    assert first.extraction_source == "EVIDENCE_AGENT"
    assert first.outcome
    assert pack and pack[0].source_url.startswith("https://europepmc.org/")
    assert pack[0].raw_value == pack[0].text
    assert pack[0].evidence_id == pack_again[0].evidence_id
    assert first.evidence_refs == second.evidence_refs


def test_evidence_extractor_empty_input_is_explicit_generic_fallback() -> None:
    extraction, pack = EvidenceExtractorV2().extract("乳腺癌新辅助治疗", [])
    assert pack == []
    assert extraction.extraction_source == "GENERIC_FALLBACK"
    assert extraction.confidence < 0.5
