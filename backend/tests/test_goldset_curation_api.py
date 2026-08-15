from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.goldset import GoldSetCurationService
from backend.app.goldset.models import RetrievalSecondReviewRequest
from backend.app.main import app, get_goldset_curation_service
from backend.tests.goldset_curation_fixtures import (
    StubSourceVerifier,
    gdc_source,
    retrieval_request,
)
from backend.tests.test_goldset_curation import error_seed


client = TestClient(app)


def fixture_service() -> GoldSetCurationService:
    return GoldSetCurationService(verifier=StubSourceVerifier())


def test_goldset_source_and_retrieval_endpoints_return_verified_draft() -> None:
    curator = fixture_service()
    app.dependency_overrides[get_goldset_curation_service] = lambda: curator
    try:
        verification = client.post(
            "/api/goldset/sources/verify",
            json=gdc_source().model_dump(mode="json"),
        )
        response = client.post(
            "/api/goldset/retrieval/initial-label",
            json=retrieval_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_goldset_curation_service, None)

    assert verification.status_code == 200
    assert verification.json()["status"] == "verified"
    assert response.status_code == 200
    payload = response.json()
    assert payload["drafts"][0]["dataset_id"] == "TCGA-BRCA"
    assert payload["drafts"][0]["source_verification"]["status"] == "verified"
    assert payload["drafts"][0]["status"] == "initial_labeled"


def test_goldset_api_chains_independent_review_and_rule_validation() -> None:
    curator = fixture_service()
    app.dependency_overrides[get_goldset_curation_service] = lambda: curator
    try:
        initial = client.post(
            "/api/goldset/retrieval/initial-label",
            json=retrieval_request().model_dump(mode="json"),
        )
        draft = initial.json()["drafts"][0]
        review_request = {
            "draft": draft,
            "reviewer_model_id": "model-b",
            "reviewed_label": "relevant",
            "confidence": 0.98,
            "rationale": "Independent API fixture review.",
        }
        reviewed = client.post(
            "/api/goldset/reviews/retrieval",
            json=review_request,
        )
        validation = client.post(
            "/api/goldset/validate",
            json={"retrieval": [reviewed.json()]},
        )
    finally:
        app.dependency_overrides.pop(get_goldset_curation_service, None)

    assert reviewed.status_code == 200
    assert reviewed.json()["agreement"] is True
    assert validation.status_code == 200
    payload = validation.json()
    assert payload["retrieval_gold"][0]["review_status"] == "approved"
    assert payload["summary"]["approved_count"] == 1
    assert payload["freeze_eligible"] is False


def test_goldset_api_rejects_same_model_review_with_structured_error() -> None:
    curator = fixture_service()
    draft = curator.initial_label_retrieval(retrieval_request()).drafts[0]
    request = RetrievalSecondReviewRequest(
        draft=draft,
        reviewer_model_id="model-a",
        reviewed_label="relevant",
        confidence=1.0,
        rationale="Not independent.",
    )
    app.dependency_overrides[get_goldset_curation_service] = lambda: curator
    try:
        response = client.post(
            "/api/goldset/reviews/retrieval",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_goldset_curation_service, None)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_reviewer"


def test_error_construction_api_returns_clean_control_and_high_risk_queue() -> None:
    curator = fixture_service()
    app.dependency_overrides[get_goldset_curation_service] = lambda: curator
    try:
        response = client.post(
            "/api/goldset/errors/construct",
            json={"seeds": [error_seed().model_dump(mode="json")]},
        )
    finally:
        app.dependency_overrides.pop(get_goldset_curation_service, None)

    assert response.status_code == 200
    payload = response.json()
    types = {item["error_type"] for item in payload["drafts"]}
    assert "clean_control" in types
    assert "her2_assay_error" in types
    assert any(item["priority"] == "high" for item in payload["review_queue"])
