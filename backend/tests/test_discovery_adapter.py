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
    client.close()
