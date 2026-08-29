from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.literature import (
    LiteratureAgent,
    LiteratureProviderTrace,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.main import app
from backend.app.requirement_agent import RequirementAgentService
from backend.app.research_planning import ResearchPlanningService


def test_v3_clarify_and_freeze_roundtrip() -> None:
    paper = PaperRecord(
        paper_id="europepmc:1",
        source_id="europepmc:1",
        provider="europe_pmc",
        title="PIK3CA HER2 neoadjuvant pCR",
        abstract="PIK3CA mutation HER2 pathological complete response neoadjuvant GSE12345",
        source_url="https://europepmc.org/article/MED/1",
        sections={"methods": "PIK3CA HER2 pCR neoadjuvant"},
        dataset_accessions=["GSE12345"],
    )

    class Stub:
        name = "stub"
        configured = True

        def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
            now = datetime.now(timezone.utc)
            return LiteratureSearchResult(
                provider=self.name,
                query=request.query,
                papers=[paper],
                trace=LiteratureProviderTrace(
                    provider=self.name,
                    query=request.query,
                    requested_at=now,
                    completed_at=now,
                    status="success",
                    source_url="https://example.org",
                    result_count=1,
                ),
            )

    planning = ResearchPlanningService(literature_agent=LiteratureAgent(providers=[Stub()]))
    agent = RequirementAgentService(planning=planning)
    previous = app.state.requirement_agent
    app.state.requirement_agent = agent
    try:
        client = TestClient(app)
        clarified = client.post("/api/v3/research/clarify", json={"topic": "乳腺癌新辅助治疗", "max_papers": 5})
        assert clarified.status_code == 200
        payload = clarified.json()
        assert payload["candidates"]
        candidate_id = next(item["candidate_id"] for item in payload["candidates"] if "PIK3CA" in item["question"])
        created = client.post(
            "/api/v3/research/contracts",
            json={"topic_id": payload["topic_id"], "candidate_id": candidate_id},
        )
        assert created.status_code == 200
        contract_id = created.json()["contract_id"]
        frozen = client.post(f"/api/v3/research/contracts/{contract_id}/freeze", json={"confirmed": True})
        assert frozen.status_code == 200
        assert frozen.json()["status"] == "FROZEN"
    finally:
        app.state.requirement_agent = previous


def test_v3_parsing_csv() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v3/parsing/run",
        json={"source_id": "file:1", "filename": "a.csv", "text": "id,status\n1,Positive\n"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PARSED"
