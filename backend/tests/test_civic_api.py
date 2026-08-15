from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app, get_civic_adapter
from backend.app.sources.civic import CIViCAdapter
from backend.tests.test_civic_adapter import civic_request, standard_handler


client = TestClient(app)


def test_civic_adapter_api_returns_knowledge_evidence_tables(tmp_path: Path) -> None:
    transport_client = httpx.Client(transport=httpx.MockTransport(standard_handler))
    adapter = CIViCAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_civic_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/civic",
            json=civic_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_civic_adapter, None)
        transport_client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "civic"
    assert payload["response_domain"] == "knowledge_evidence"
    assert payload["status_filter"] == "ACCEPTED"
    assert payload["evidence_items"][0]["evidence_id"] == "CIViC:EID7316"
    assert payload["evidence_items"][0]["publication_id"] == "31091374"
    assert {table["table_name"] for table in payload["tables"]} == {
        "evidence_items",
        "molecular_profiles",
        "diseases",
        "genes",
        "variants",
        "therapies",
        "sources",
        "evidence_relations",
    }


def test_civic_adapter_api_exposes_structured_failure_code(tmp_path: Path) -> None:
    request = civic_request(therapy_name="Alpelisib\u0000")

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid query must not call CIViC")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = CIViCAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_civic_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/civic",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_civic_adapter, None)
        transport_client.close()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_query"
    assert detail["retryable"] is False
