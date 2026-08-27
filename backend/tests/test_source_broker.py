from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.literature import (
    LiteratureAgent,
    LiteratureProviderTrace,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.research_planning import ResearchPlanningService, TopicCreateRequest
from backend.app.source_broker.models import SourcePlanRequest
from backend.app.source_broker.source_catalog import SeedSourceCatalog


def _paper() -> PaperRecord:
    return PaperRecord(
        paper_id="europepmc:PMC-SOURCE-TEST",
        source_id="europepmc:PMC-SOURCE-TEST",
        provider="europe_pmc",
        title="PIK3CA and HER2 in neoadjuvant breast cancer",
        abstract=(
            "PIK3CA mutation and HER2 status were evaluated against pathological complete "
            "response after neoadjuvant treatment. Public data are available as GSE25066."
        ),
        source_url="https://europepmc.org/article/PMC/PMC-SOURCE-TEST",
        sections={
            "methods": (
                "Patients were assessed for PIK3CA mutation, HER2 status and pathological "
                "complete response (pCR)."
            ),
            "data_availability": "Expression data are available from GEO accession GSE25066.",
        },
        dataset_accessions=["GSE25066"],
    )


class _StubProvider:
    name = "stub"
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
                source_url="https://example.org/literature-search",
                result_count=1,
            ),
        )


def _planned_service() -> tuple[ResearchPlanningService, str]:
    service = ResearchPlanningService(
        literature_agent=LiteratureAgent(providers=[_StubProvider()])
    )
    topic = service.create_topic(TopicCreateRequest(topic="乳腺癌新辅助治疗"))
    service.scan_literature(
        topic.topic_id,
        main_module.LiteratureScanRequest(max_records=10),
    )
    candidate = next(
        item
        for item in service.question_candidates(topic.topic_id).candidates
        if "PIK3CA" in item.question
    )
    contract = service.select_question(candidate.candidate_id, main_module.QuestionSelectionRequest())
    return service, contract.contract_id


def test_seed_catalog_separates_source_dataset_resource_and_preserves_legacy_profiles() -> None:
    catalog = SeedSourceCatalog()

    source = catalog.source("ncbi_geo")
    dataset = catalog.dataset("geo:GSE25066")
    profiles = catalog.legacy_study_profiles()

    assert source is not None
    assert source.source_url == "https://www.ncbi.nlm.nih.gov/geo/"
    assert dataset is not None
    assert dataset.source_id == source.source_id
    assert dataset.source_url.endswith("acc=GSE25066")
    assert dataset.resources[0].dataset_id == dataset.dataset_id
    assert dataset.resources[0].source_id == source.source_id
    assert dataset.capability_status == "seed_requires_runtime_verification"
    assert any(profile["arg_value"] == "GSE25066" for profile in profiles)


def test_source_plan_exposes_coverage_fallback_and_forbidden_cross_cohort_join() -> None:
    service, contract_id = _planned_service()
    result = service.plan_sources(
        contract_id,
        SourcePlanRequest(max_selected_datasets=3),
    )
    plan = result.source_plan
    cells = {
        (cell.field_id, cell.dataset_id): cell
        for cell in result.coverage_matrix.cells
    }

    assert {source.source_id for source in result.sources} == {"cbioportal", "ncbi_geo", "gdc"}
    assert cells[("pcr", "geo:GSE25066")].coverage == 1.0
    assert cells[("pik3ca_mutation", "geo:GSE25066")].coverage == 0.0
    assert cells[("pik3ca_mutation", "cbioportal:brca_metabric")].coverage == 0.75
    assert cells[("pcr", "cbioportal:breast_alpelisib_2020")].coverage == 0.0
    assert cells[("pcr", "geo:GSE25066")].runtime_verified is False
    geo = next(item for item in result.dataset_candidates if item.dataset_id == "geo:GSE25066")
    assert geo.discovery_evidence_ids == ["europepmc:PMC-SOURCE-TEST"]
    assert plan.status == "PARTIAL"
    assert plan.selected_dataset_ids
    assert plan.selected_resource_ids
    assert plan.required_field_coverage < plan.portfolio_required_field_coverage
    assert plan.fallback_dataset_ids
    assert plan.join_policies
    assert all(policy.decision == "FORBIDDEN_PATIENT_JOIN" for policy in plan.join_policies)
    assert all(not policy.identity_evidence_ids for policy in plan.join_policies)
    assert any("不得因此横向拼接患者" in warning for warning in plan.warnings)


def test_non_breast_contract_does_not_receive_breast_dataset_seeds() -> None:
    service = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[]))
    service.literature_agent.providers = []
    topic = service.create_topic(TopicCreateRequest(topic="原初黑洞与暗物质"))
    service.scan_literature(topic.topic_id, main_module.LiteratureScanRequest(max_records=5))
    candidate = service.question_candidates(topic.topic_id).candidates[0]
    contract = service.select_question(candidate.candidate_id, main_module.QuestionSelectionRequest())

    result = service.plan_sources(contract.contract_id, SourcePlanRequest())

    assert result.sources == []
    assert result.dataset_candidates == []
    assert result.source_plan.status == "PARTIAL"
    assert result.source_plan.selected_dataset_ids == []
    assert set(result.source_plan.uncovered_required_fields) == {
        field.field_id for field in contract.required_fields
    }
    assert any("Evidence 门控" in warning for warning in result.source_plan.warnings)


def test_source_plan_api_returns_business_objects_and_can_be_read_back(monkeypatch) -> None:
    service, contract_id = _planned_service()
    monkeypatch.setattr(main_module, "research_planning_service", service)
    client = TestClient(main_module.app)

    response = client.post(
        f"/api/research/contracts/{contract_id}/source-plan",
        json={"max_selected_datasets": 3, "public_data_only": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == contract_id
    assert body["dataset_candidates"]
    assert body["coverage_matrix"]["cells"]
    assert body["source_plan"]["join_policies"]
    assert all(
        item["decision"] == "FORBIDDEN_PATIENT_JOIN"
        for item in body["source_plan"]["join_policies"]
    )
    source_plan_id = body["source_plan"]["source_plan_id"]

    read_back = client.get(f"/api/research/source-plans/{source_plan_id}")
    assert read_back.status_code == 200
    assert read_back.json() == body

    missing = client.get("/api/research/source-plans/source-plan-missing")
    assert missing.status_code == 404
