from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agent.service import ResearchAgentService
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
from backend.app.research_planning_v2 import ResearchPlanningV2Service
from backend.app.research_planning_v2.models import ResearchPlanningV2Request


PLANNER_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "planner"


class _StubLiteratureProvider:
    name = "stub_literature"
    configured = True

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
        now = datetime.now(timezone.utc)
        paper = PaperRecord(
            paper_id="europepmc:v30-plan",
            source_id="europepmc:v30-plan",
            provider="europe_pmc",
            title="PIK3CA HER2 neoadjuvant pCR",
            abstract="PIK3CA mutation HER2 pathological complete response neoadjuvant GSE12345",
            source_url="https://europepmc.org/article/MED/1",
            sections={"methods": "PIK3CA HER2 pCR neoadjuvant"},
            dataset_accessions=["GSE12345"],
        )
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


class _RecordingRequirementAgent(RequirementAgentService):
    def __init__(self, inner: RequirementAgentService) -> None:
        self._inner = inner
        self.clarify_topics: list[str] = []
        self.create_contract_ids: list[str] = []

    @property
    def planning(self):
        return self._inner.planning

    def clarify(self, request):
        self.clarify_topics.append(request.topic)
        return self._inner.clarify(request)

    def create_contract(self, request):
        self.create_contract_ids.append(request.candidate_id)
        return self._inner.create_contract(request)

    def freeze(self, contract_id: str):
        raise AssertionError("Planner facade must not auto-freeze a Research Contract.")

    def get(self, contract_id: str):
        return self._inner.get(contract_id)


class _RecordingPlanningV2(ResearchPlanningV2Service):
    def __init__(self, inner: ResearchPlanningV2Service) -> None:
        self._inner = inner
        self.topics: list[str] = []

    def plan(self, request: ResearchPlanningV2Request):
        self.topics.append(request.topic)
        return self._inner.plan(request)


def _install_recording_planner():
    inner = RequirementAgentService(
        planning=ResearchPlanningService(literature_agent=LiteratureAgent(providers=[_StubLiteratureProvider()]))
    )
    requirement = _RecordingRequirementAgent(inner)
    planning_v2 = _RecordingPlanningV2(ResearchPlanningV2Service())
    previous_agent = app.state.requirement_agent
    previous_v2 = getattr(app.state, "research_planning_v2", None)
    app.state.requirement_agent = requirement
    app.state.research_planning_v2 = planning_v2
    return requirement, planning_v2, previous_agent, previous_v2


def _restore_planner(previous_agent, previous_v2) -> None:
    app.state.requirement_agent = previous_agent
    if previous_v2 is None:
        delattr(app.state, "research_planning_v2")
    else:
        app.state.research_planning_v2 = previous_v2


def test_chat_session_plan_is_rejected() -> None:
    client = TestClient(app)
    turn = client.post("/api/v30/copilot/turn", json={"message": "你好"})
    assert turn.status_code == 200
    assert turn.json()["route"]["route"] == "CHAT"
    assert turn.json()["ready_for_planner"] is False
    planned = client.post("/api/v30/plan", json={"session_id": turn.json()["session_id"]})
    assert planned.status_code == 422
    assert planned.json() == {"error": "research_goal_not_ready"}


def test_first_research_turn_plan_is_rejected() -> None:
    client = TestClient(app)
    turn = client.post(
        "/api/v30/copilot/turn",
        json={"message": "我想研究HER2阳性乳腺癌耐药机制"},
    )
    assert turn.status_code == 200
    assert turn.json()["ready_for_planner"] is False
    planned = client.post("/api/v30/plan", json={"session_id": turn.json()["session_id"]})
    assert planned.status_code == 422
    assert planned.json()["error"] == "research_goal_not_ready"


def test_ready_session_plans_through_existing_services(monkeypatch) -> None:
    monkeypatch.setattr(
        ResearchAgentService,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call ResearchAgentService")),
    )
    requirement, planning_v2, previous_agent, previous_v2 = _install_recording_planner()
    client = TestClient(app)
    try:
        first = client.post(
            "/api/v30/copilot/turn",
            json={"message": "我想研究HER2阳性乳腺癌耐药机制"},
        )
        session_id = first.json()["session_id"]
        second = client.post(
            "/api/v30/copilot/turn",
            json={"session_id": session_id, "message": "疗效预测"},
        )
        assert second.json()["ready_for_planner"] is True
        planned = client.post("/api/v30/plan", json={"session_id": session_id})
        assert planned.status_code == 200
        payload = planned.json()
        assert payload["compiled_from_session"] is True
        assert payload["ready_for_planner"] is True
        assert payload["contract_id"]
        assert payload["contract"]["contract_id"] == payload["contract_id"]
        assert payload["contract"]["status"] != "FROZEN"
        assert "map_her2_ihc_2plus_to_positive" in payload["contract"]["prohibited_operations"]
        assert requirement.clarify_topics
        assert requirement.create_contract_ids
        assert planning_v2.topics
        assert "RequirementAgentService" in payload["used_existing_services"]
        assert "ResearchPlanningService" in payload["used_existing_services"]
        assert "ResearchPlanningV2Service" in payload["used_existing_services"]
        assert payload["memory"]["goal"]["object"] == "HER2阳性乳腺癌"
        assert any(item["answer"] == "疗效预测" for item in payload["memory"]["clarifications"])
    finally:
        _restore_planner(previous_agent, previous_v2)


def test_planner_source_does_not_import_adapter_or_agent() -> None:
    forbidden_modules = (
        "backend.app.sources",
        "backend.app.agent.service",
        "backend.app.quality",
        "backend.app.quality_v2",
    )
    forbidden_names = {"ResearchAgentService", "GDCAdapter", "GEOAdapter", "SchemaMatcher"}
    hits: list[str] = []
    for path in PLANNER_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == item or alias.name.startswith(item + ".") for item in forbidden_modules):
                        hits.append(f"{path.name}:import {alias.name}")
                    if alias.name.split(".")[-1] in forbidden_names:
                        hits.append(f"{path.name}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == item or node.module.startswith(item + ".") for item in forbidden_modules):
                    hits.append(f"{path.name}:from {node.module}")
                for alias in node.names:
                    if alias.name in forbidden_names:
                        hits.append(f"{path.name}:from {node.module} import {alias.name}")
    assert hits == []


def test_legacy_v3_clarify_still_works() -> None:
    requirement, _, previous_agent, previous_v2 = _install_recording_planner()
    client = TestClient(app)
    try:
        response = client.post("/api/v3/research/clarify", json={"topic": "乳腺癌新辅助治疗", "max_papers": 5})
        assert response.status_code == 200
        payload = response.json()
        assert payload["candidates"]
        assert payload["topic_id"]
        assert requirement.clarify_topics
    finally:
        _restore_planner(previous_agent, previous_v2)
