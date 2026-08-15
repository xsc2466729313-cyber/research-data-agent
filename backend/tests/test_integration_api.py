from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.test_integration_pipeline import standard_request


client = TestClient(app)


def test_normalization_integration_api_returns_traceable_result() -> None:
    response = client.post(
        "/api/integration/normalize",
        json=standard_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline"] == "normalization_integration"
    assert payload["canonical_records"]
    assert payload["evidence"]
    assert payload["summary"]["merged_entity_count"] == 1
    assert payload["summary"]["conflict_count"] >= 1
    assert all(item["raw_field"] for item in payload["canonical_records"])


def test_normalization_integration_api_exposes_source_registration_error() -> None:
    request = standard_request()
    request.records[0].source_id = "fixture:not-registered"
    response = client.post(
        "/api/integration/normalize",
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "unregistered_source"
    assert detail["retryable"] is False
