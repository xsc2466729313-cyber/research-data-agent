from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

import backend.app.main as main_module
from backend.app.agent.research_brief import ResearchBriefBuilder
from backend.app.literature import (
    EuropePMCProvider,
    LiteratureAgent,
    LiteratureProviderTrace,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.literature.providers import GiiispProvider
from backend.app.literature.providers.base import LiteratureProviderConfigurationError
from backend.app.research_planning import (
    ResearchPlanningService,
    TopicCreateRequest,
)
from backend.app.sources.discovery import DiscoveryAdapter


def _paper() -> PaperRecord:
    return PaperRecord(
        paper_id="europepmc:PMC-TEST",
        source_id="europepmc:PMC-TEST",
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
                "Pathological complete response (pCR) was the primary outcome. "
                "Logistic regression reported odds ratio and 95% confidence interval."
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


def _planning_service() -> ResearchPlanningService:
    return ResearchPlanningService(
        literature_agent=LiteratureAgent(providers=[_StubLiteratureProvider()])
    )


def test_broad_topic_becomes_three_evidence_linked_questions_and_contract() -> None:
    service = _planning_service()
    topic = service.create_topic(TopicCreateRequest(topic="乳腺癌新辅助治疗"))

    assert topic.domain == "oncology"
    assert topic.disease == "breast cancer"
    assert topic.ambiguity_level == "high"

    scan = service.scan_literature(
        topic.topic_id,
        main_module.LiteratureScanRequest(max_records=10),
    )
    candidates = service.question_candidates(topic.topic_id)

    assert scan.candidate_count == 3
    assert len(scan.scan.papers) == 1
    assert len(candidates.candidates) == 3
    assert all(candidate.score_status == "provisional" for candidate in candidates.candidates)
    assert all(candidate.score_basis for candidate in candidates.candidates)
    selected = next(candidate for candidate in candidates.candidates if "PIK3CA" in candidate.question)
    assert selected.literature_evidence
    assert selected.literature_evidence[0].source_url.startswith("https://europepmc.org/")

    contract = service.select_question(
        selected.candidate_id,
        main_module.QuestionSelectionRequest(),
    )
    required = {field.field_id: field for field in contract.required_fields}
    recommended = {field.field_id for field in contract.recommended_fields}

    assert contract.validation_status == "READY_FOR_SOURCE_PLANNING"
    assert required["pik3ca_mutation"].evidence_status == "supported"
    assert required["pcr"].literature_evidence
    assert required["response_domain"].evidence_status == "operational_rule"
    assert required["her2_status"].reason.startswith("HER2 IHC 2+")
    assert {"age", "stage", "er_status", "pr_status", "treatment"} <= recommended
    assert {metric.metric_id for metric in contract.metric_requirements} >= {
        "odds_ratio",
        "confidence_interval_95",
        "p_value",
    }
    assert all("patient" not in paper.model_dump() for paper in scan.scan.papers)

    brief = ResearchBriefBuilder().build_from_contract(contract)
    brief_fields = {field.field_id: field.priority for field in brief.fields}
    assert brief.primary_question == contract.research_question
    assert brief_fields["pik3ca_mutation"] == "primary"
    assert brief_fields["age"] == "important"
    assert brief.needs_clinical_outcome is True


def test_missing_literature_keeps_questions_provisional_and_blocks_ready_status() -> None:
    service = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    # An empty list means use defaults, so replace explicitly for an offline deterministic scan.
    service.literature_agent.providers = []
    topic = service.create_topic(TopicCreateRequest(topic="乳腺癌新辅助治疗"))
    response = service.scan_literature(
        topic.topic_id,
        main_module.LiteratureScanRequest(max_records=5),
    )
    candidate = service.question_candidates(topic.topic_id).candidates[0]
    contract = service.select_question(candidate.candidate_id, main_module.QuestionSelectionRequest())

    assert response.scan.papers == []
    assert response.scan.warnings
    assert candidate.literature_evidence == []
    assert contract.validation_status == "NEEDS_EVIDENCE"
    assert any(field.review_required for field in contract.required_fields)
    assert contract.validation_warnings


def test_non_medical_topic_does_not_receive_patient_or_breast_cancer_fields() -> None:
    service = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    topic = service.create_topic(TopicCreateRequest(topic="黑洞与暗物质"))
    service.scan_literature(topic.topic_id, main_module.LiteratureScanRequest(max_records=5))
    candidate = service.question_candidates(topic.topic_id).candidates[0]
    contract = service.select_question(candidate.candidate_id, main_module.QuestionSelectionRequest())
    field_ids = {field.field_id for field in contract.required_fields}

    assert topic.domain == "astronomy"
    assert "observation_id" in field_ids
    assert "patient_id" not in field_ids
    assert "sample_id" not in field_ids
    assert "her2_status" not in field_ids


def test_non_breast_oncology_topic_uses_generic_clinical_fields() -> None:
    service = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    topic = service.create_topic(TopicCreateRequest(topic="肺癌免疫治疗"))
    service.scan_literature(topic.topic_id, main_module.LiteratureScanRequest(max_records=5))
    candidate = service.question_candidates(topic.topic_id).candidates[0]
    contract = service.select_question(candidate.candidate_id, main_module.QuestionSelectionRequest())
    field_ids = {field.field_id for field in contract.required_fields}

    assert topic.domain == "oncology"
    assert "patient_id" in field_ids
    assert "primary_exposure" in field_ids
    assert "her2_status" not in field_ids
    assert "er_status" not in field_ids


def test_europe_pmc_provider_reuses_official_adapter_and_records_trace() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.ebi.ac.uk"
        return httpx.Response(
            200,
            json={
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": "PMC123",
                            "pmid": "12345678",
                            "doi": "10.1000/test",
                            "title": "Breast cancer pCR dataset GSE12345",
                            "abstractText": "Neoadjuvant response study.",
                            "pubYear": "2024",
                            "inEPMC": True,
                        }
                    ]
                },
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = EuropePMCProvider(DiscoveryAdapter(client=client))
    result = provider.search(LiteratureSearchRequest(query="breast cancer pCR", max_records=5))
    client.close()

    assert result.trace.status == "success"
    assert result.trace.result_count == 1
    assert result.papers[0].paper_id == "europepmc:PMC123"
    assert result.papers[0].dataset_accessions == ["GSE12345"]
    assert result.papers[0].source_url.startswith("https://europepmc.org/")


def test_giiisp_skeleton_never_exposes_key_or_guesses_endpoint() -> None:
    provider = GiiispProvider(api_key=SecretStr("secret-value-123"), base_url="https://example.org")

    assert "secret-value-123" not in repr(provider)
    try:
        provider.search(LiteratureSearchRequest(query="breast cancer", max_records=5))
    except LiteratureProviderConfigurationError as exc:
        assert "Schema" in str(exc)
        assert "secret-value-123" not in str(exc)
    else:
        raise AssertionError("Giiisp skeleton must not call an undocumented API")


def test_research_planning_api_runs_topic_to_contract_without_patient_data(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "research_planning_service", _planning_service())
    client = TestClient(main_module.app)

    topic_response = client.post("/api/research/topics", json={"topic": "乳腺癌新辅助治疗"})
    assert topic_response.status_code == 200
    topic_id = topic_response.json()["topic_id"]

    scan_response = client.post(
        f"/api/research/topics/{topic_id}/literature-scan",
        json={"max_records": 10},
    )
    assert scan_response.status_code == 200
    assert scan_response.json()["candidate_count"] == 3
    assert "patient_data" not in scan_response.json()

    candidates_response = client.get(f"/api/research/topics/{topic_id}/question-candidates")
    assert candidates_response.status_code == 200
    candidates = candidates_response.json()["candidates"]
    selected = next(candidate for candidate in candidates if "PIK3CA" in candidate["question"])

    contract_response = client.post(
        f"/api/research/questions/{selected['candidate_id']}/select",
        json={},
    )
    assert contract_response.status_code == 200
    contract = contract_response.json()
    assert contract["required_fields"]
    assert contract["recommended_fields"]
    assert contract["literature_evidence"]

    get_response = client.get(f"/api/research/contracts/{contract['contract_id']}")
    assert get_response.status_code == 200
    assert get_response.json() == contract
