from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.tests.test_repair_loop import canonical_record


client = TestClient(app)


def payload(record: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": "repair-api-fixture",
        "records": [{"record_id": "record-api-1", "record": record}],
    }


def test_repair_classifier_api_returns_business_error_type() -> None:
    response = client.post(
        "/api/repair/classify",
        json=payload(canonical_record(drug="Herceptin", raw_value="Herceptin")),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["classifier_version"] == "error-classifier-v1"
    assert body["findings"][0]["error_type"] == "drug_alias"
    assert body["findings"][0]["candidate_repair"]["value"] == "Trastuzumab"


def test_repair_loop_api_returns_repaired_value_audit_and_revalidation() -> None:
    response = client.post(
        "/api/repair/run",
        json=payload(canonical_record(drug="Herceptin", raw_value="Herceptin")),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["publishable_records"][0]["record"]["drug"] == "Trastuzumab"
    assert body["publishable_records"][0]["record"]["raw_value"] == "Herceptin"
    assert body["repair_log"][0]["before"][0]["record"]["drug"] == "Herceptin"
    assert body["repair_log"][0]["after"][0]["record"]["drug"] == "Trastuzumab"
    assert body["repair_log"][0]["revalidated"] is True
    assert body["quality_after"]["passed"] is True
    assert body["summary"]["repair_accuracy"] is None


def test_repair_loop_api_routes_unsafe_her2_to_review_without_mutation() -> None:
    response = client.post(
        "/api/repair/run",
        json=payload(
            canonical_record(
                her2_status="Positive",
                her2_assay="IHC",
                her2_raw_value="2+",
                raw_field="HER2_IHC",
                raw_value="2+",
            )
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["safety_gate"] == "REVIEW"
    assert body["review_records"][0]["record"]["her2_status"] == "Positive"
    assert body["summary"]["automatic_repair_count"] == 0


def test_repair_api_rejects_duplicate_record_ids() -> None:
    record = canonical_record()
    response = client.post(
        "/api/repair/run",
        json={
            "task_id": "duplicate-id-fixture",
            "records": [
                {"record_id": "same", "record": record},
                {"record_id": "same", "record": record},
            ],
        },
    )

    assert response.status_code == 422
    assert "record_id values must be unique" in response.text
