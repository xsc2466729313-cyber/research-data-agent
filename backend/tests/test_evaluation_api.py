from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.evaluation import EvaluationService
from backend.app.main import app, get_evaluation_service
from backend.tests.evaluation_fixtures import validated_evaluation_request


client = TestClient(app)


def test_goldset_template_endpoint_reports_official_rows_still_unevaluated() -> None:
    response = client.get("/api/evaluation/goldset/templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "NOT_EVALUATED"
    assert payload["row_counts"]["retrieval_gold.csv"] == 50
    assert payload["row_counts"]["field_gold.csv"] == 26
    assert payload["row_counts"]["error_gold.csv"] == 18
    assert payload["required_headers"]["field_gold.csv"][0] == "case_id"
    assert "66.94" not in json.dumps(payload)


def test_evaluation_api_preserves_not_evaluated_state_and_artifacts(
    tmp_path: Path,
) -> None:
    service = EvaluationService(output_dir=tmp_path)
    app.dependency_overrides[get_evaluation_service] = lambda: service
    try:
        response = client.post(
            "/api/evaluation/run",
            json={"evaluation_id": "api-no-gold"},
        )
        payload = response.json()
        metrics_artifact = next(
            item for item in payload["artifacts"] if item["name"] == "metrics.json"
        )
        download = client.get(metrics_artifact["url"])
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 200
    assert payload["evaluation_status"] == "NOT_EVALUATED"
    assert payload["metrics"]["sdti"]["value"] is None
    assert payload["safety"]["publish_allowed"] is False
    assert {item["name"] for item in payload["artifacts"]} == {
        "metrics.json",
        "report.md",
    }
    assert download.status_code == 200
    assert download.json()["metrics"]["sdti"]["value"] is None


def test_evaluation_artifact_endpoint_rejects_unknown_files(tmp_path: Path) -> None:
    service = EvaluationService(output_dir=tmp_path)
    app.dependency_overrides[get_evaluation_service] = lambda: service
    try:
        response = client.get(
            "/api/evaluation/artifacts/not-present/secrets.txt"
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "artifact_not_found"


def test_evaluation_api_returns_derived_fixture_values_not_only_http_200(
    tmp_path: Path,
) -> None:
    request = validated_evaluation_request("api-validated-fixture")
    app.dependency_overrides[get_evaluation_service] = lambda: EvaluationService(
        output_dir=tmp_path
    )
    try:
        response = client.post(
            "/api/evaluation/run",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["retrieval"] == {"tp": 1, "fp": 0, "fn": 0}
    assert payload["metrics"]["sdti"]["value"] == 100.0
    assert payload["safety"]["gate"] == "PASS"


def test_evaluation_api_exposes_observation_mismatch(tmp_path: Path) -> None:
    request = validated_evaluation_request("api-mismatch")
    assert request.observations is not None
    request.observations.errors.pop()
    app.dependency_overrides[get_evaluation_service] = lambda: EvaluationService(
        output_dir=tmp_path
    )
    try:
        response = client.post(
            "/api/evaluation/run",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_evaluation_service, None)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "observation_mismatch"
