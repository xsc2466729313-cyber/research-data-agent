from __future__ import annotations

import httpx

from backend.app.agent.models import AgentTaskRequest
from backend.app.agent.service import ResearchAgentService
from backend.app.models import ResearchSpec
from backend.app.sources.discovery import DiscoveryAdapter


def test_deterministic_planning_can_expand_to_discovery_sources() -> None:
    service = ResearchAgentService()
    spec = ResearchSpec(
        task_id="task-discovery",
        research_goal="研究乳腺癌中 PIK3CA 突变与治疗响应的关系，并整理可审计证据",
        disease="Breast Cancer",
        genes=["PIK3CA"],
        drugs=["Alpelisib"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response", "evidence"],
        target_fields=["patient_id", "sample_id", "response"],
    )
    request = AgentTaskRequest(
        question="研究乳腺癌中 PIK3CA 突变与治疗响应的关系，并整理可审计证据",
        use_qwen=False,
        data_mode="plan_only",
        max_sources=20,
    )

    names = {call["name"] for call in service._deterministic_tool_calls(spec, request)}

    assert "search_biosample" in names
    assert "search_europe_pmc" in names
    assert "search_geo_catalog" in names


def test_discovery_adapter_returns_official_source_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {"count": "1", "idlist": ["12345"]},
                },
                request=request,
            )
        if request.url.path.endswith("/esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "uids": ["12345"],
                        "12345": {
                            "accession": "SAMN00000001",
                            "title": "Breast cancer sample",
                            "organism": "Homo sapiens",
                            "attributes": {"tissue": "breast"},
                        },
                    }
                },
                request=request,
            )
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(
                200,
                json={
                    "hitCount": 1,
                    "resultList": {
                        "result": [
                            {
                                "id": "PMC123",
                                "pmid": "12345678",
                                "title": "Breast cancer response study",
                                "journalTitle": "Nature",
                                "pubYear": "2024",
                                "abstractText": "Study abstract",
                            }
                        ]
                    },
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = DiscoveryAdapter(client=client)

    biosample = adapter.search_biosample(task_id="task-a", query="breast cancer", max_records=5)
    europe_pmc = adapter.search_europe_pmc(task_id="task-b", query="breast cancer", max_records=5)

    assert biosample.source_items[0].source_id == "ncbi-biosample:SAMN00000001"
    assert biosample.source_items[0].url.startswith("https://www.ncbi.nlm.nih.gov/biosample/")
    assert europe_pmc.source_items[0].source_id == "europepmc:PMC123"
    assert europe_pmc.source_items[0].url.startswith("https://europepmc.org/article/MED/")

    service = ResearchAgentService()
    biosample_candidates = service._candidates("search_biosample", biosample)
    europe_pmc_candidates = service._candidates("search_europe_pmc", europe_pmc)

    assert biosample_candidates[0].source_database == "NCBI BioSample"
    assert biosample_candidates[0].dataset_id == "SAMN00000001"
    assert biosample_candidates[0].has_response is False
    assert europe_pmc_candidates[0].source_database == "Europe PMC"
    assert europe_pmc_candidates[0].dataset_id == "12345678"
    assert europe_pmc_candidates[0].has_response is False
    assert service._record_count(biosample) == 1
    assert service._record_count(europe_pmc) == 1
    client.close()


def test_geo_catalog_search_returns_gse_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            assert request.url.params.get("db") == "gds"
            return httpx.Response(
                200,
                json={"esearchresult": {"count": "1", "idlist": ["200050948"]}},
                request=request,
            )
        if request.url.path.endswith("/esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "uids": ["200050948"],
                        "200050948": {
                            "accession": "GSE50948",
                            "title": "HER2 breast cancer response",
                            "summary": "Neoadjuvant trastuzumab",
                            "n_samples": 50,
                            "gdsType": "Expression profiling by array",
                        },
                    }
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = DiscoveryAdapter(client=client)
    result = adapter.search_geo_catalog(task_id="task-geo", query="HER2 PIK3CA response", max_records=5)
    client.close()

    assert result.records[0].accession == "GSE50948"
    assert result.source_items[0].source_id == "ncbi-geo-catalog:GSE50948"
    candidates = ResearchAgentService._candidates("search_geo_catalog", result)
    assert candidates[0].dataset_id == "GSE50948"
    assert candidates[0].source_database == "NCBI GEO"


def test_unknown_tool_does_not_reuse_civic_candidate_builder() -> None:
    class FakeDiscoveryResult:
        records = []

    candidates = ResearchAgentService._candidates("search_unknown", FakeDiscoveryResult())
    assert candidates == []


def test_civic_candidate_builder_tolerates_missing_evidence_items() -> None:
    class FakeDiscoveryResult:
        records = []

    candidates = ResearchAgentService._candidates("search_civic", FakeDiscoveryResult())
    assert candidates[0].source_database == "CIViC"
    assert candidates[0].url == "https://civicdb.org/"
