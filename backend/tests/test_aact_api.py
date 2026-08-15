from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app, get_aact_adapter
from backend.app.sources.aact import AACTClinicalTrialsAdapter
from backend.tests.test_aact_adapter import aact_request, standard_handler


client = TestClient(app)


def test_aact_adapter_api_returns_unified_trial_tables(tmp_path: Path) -> None:
    transport_client = httpx.Client(transport=httpx.MockTransport(standard_handler))
    adapter = AACTClinicalTrialsAdapter(
        cache_dir=tmp_path, client=transport_client
    )
    app.dependency_overrides[get_aact_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/aact",
            json=aact_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_aact_adapter, None)
        transport_client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "aact"
    assert payload["condition"] == "Breast Cancer"
    assert payload["trials"][0]["nct_id"] == "NCT01104584"
    assert payload["trials"][0]["trial_id"] == "NCT01104584"
    assert payload["trials"][0]["results_status"] == "available"
    assert payload["trials"][1]["results_status"] == "not_reported"
    assert {table["table_name"] for table in payload["tables"]} == {
        "studies",
        "conditions",
        "interventions",
        "eligibilities",
        "outcomes",
        "outcome_measurements",
    }


def test_aact_adapter_api_exposes_structured_failure_code(tmp_path: Path) -> None:
    request = aact_request(query_terms="breast\u0000cancer")

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid query must not call ClinicalTrials.gov")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AACTClinicalTrialsAdapter(
        cache_dir=tmp_path, client=transport_client
    )
    app.dependency_overrides[get_aact_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/aact",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_aact_adapter, None)
        transport_client.close()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_query"
    assert detail["retryable"] is False
