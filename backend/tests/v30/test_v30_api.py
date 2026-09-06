from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


FORBIDDEN_IMPORT_PREFIXES = (
    "backend.app.sources",
    "backend.app.quality",
    "backend.app.quality_v2",
    "backend.app.agent.service",
    "backend.app.schema_matcher",
)

FORBIDDEN_NAMES = {
    "ResearchAgentService",
    "SchemaMatcher",
    "GDCAdapter",
    "GEOAdapter",
}

V30_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30"


def test_health_still_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_legacy_openapi_paths_remain() -> None:
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/agent/tasks" in paths
    assert "/api/v3/research/clarify" in paths
    assert "/api/v30/route" in paths
    assert "/api/v30/copilot/turn" in paths
    assert "/api/v30/sessions" in paths
    assert "/api/v30/plan" in paths


def test_plan_requires_ready_session() -> None:
    client = TestClient(app)
    created = client.post("/api/v30/sessions")
    session_id = created.json()["session_id"]
    response = client.post("/api/v30/plan", json={"session_id": session_id})
    assert response.status_code == 422
    assert response.json() == {"error": "research_goal_not_ready"}


def test_copilot_turn_and_memory_roundtrip() -> None:
    client = TestClient(app)
    created = client.post("/api/v30/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    empty = client.get(f"/api/v30/sessions/{session_id}/memory")
    assert empty.status_code == 200
    assert empty.json()["goal"] is None

    routed = client.post("/api/v30/route", json={"message": "什么是HER2", "session_id": session_id})
    assert routed.status_code == 200
    assert routed.json()["route"] == "CONCEPT_QA"

    first = client.post(
        "/api/v30/copilot/turn",
        json={"session_id": session_id, "message": "我想研究HER2阳性乳腺癌耐药机制"},
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["route"]["route"] == "CLARIFY"
    assert payload["ready_for_planner"] is False
    assert payload["memory"]["goal"]["object"] == "HER2阳性乳腺癌"

    second = client.post(
        "/api/v30/copilot/turn",
        json={"session_id": session_id, "message": "疗效预测"},
    )
    assert second.status_code == 200
    answers = [item["answer"] for item in second.json()["memory"]["clarifications"]]
    assert "疗效预测" in answers


def test_v30_source_does_not_call_medical_pipeline() -> None:
    hits: list[str] = []
    for path in V30_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == prefix or alias.name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                        hits.append(f"{path.name}:import {alias.name}")
                    if alias.name.split(".")[-1] in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == prefix or node.module.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                    hits.append(f"{path.name}:from {node.module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:from {node.module} import {alias.name}")
    assert hits == []
