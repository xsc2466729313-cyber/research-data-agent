from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.quality_v2 import QualityReviewRequest, QualityV2Service
from backend.app.quality_v2.models import DetectionRisk, QualityRecord, RepairCandidate


def record(**updates):
    value = {
        "study_id": "study-1",
        "disease": "breast cancer",
        "source_id": "fixture:source-1",
        "raw_field": "drug",
        "raw_value": "Herceptin",
        "confidence": 0.98,
        "drug": "Herceptin",
    }
    value.update(updates)
    return value


def test_quality_v2_separates_detection_from_safe_apply_and_preserves_raw_value():
    result = QualityV2Service().review(
        QualityReviewRequest(
            task_id="quality-v2-safe",
            records=[QualityRecord(record_id="r1", record=record())],
            recommended_fields=["drug"],
        )
    )
    assert result.detection.findings[0].error_type == "drug_alias"
    assert result.candidates.summary["safe_candidate_count"] == 1
    assert result.applied.applied_count == 1
    assert result.applied.records[0].record["drug"] == "Trastuzumab"
    assert result.applied.records[0].record["raw_value"] == "Herceptin"
    assert result.readiness.status == "READY"
    assert result.safety_gate.value == "PASS"


def test_quality_v2_high_risk_is_never_auto_applied_and_is_not_ready():
    result = QualityV2Service().review(
        QualityReviewRequest(
            task_id="quality-v2-her2",
            records=[QualityRecord(record_id="r1", record=record(her2_assay="IHC", her2_raw_value="2+", her2_status="Positive", raw_field="HER2_IHC", raw_value="2+"))],
        )
    )
    assert result.applied.applied_count == 0
    assert result.applied.records[0].record["her2_status"] == "Positive"
    assert result.readiness.status == "NOT_READY"
    assert result.safety_gate.value == "FAIL"
    assert any(item.priority == "HIGH" for item in result.review_queue)


def test_quality_v2_missing_provenance_fails_closed_without_invention():
    bad = record()
    del bad["source_id"]
    result = QualityV2Service().review(
        QualityReviewRequest(task_id="quality-v2-provenance", records=[QualityRecord(record_id="r1", record=bad)])
    )
    assert result.readiness.status == "NOT_READY"
    assert result.readiness.publish_allowed is False
    assert "source_id" not in result.applied.records[0].record
    assert result.applied.applied_count == 0


def test_quality_v2_api_returns_business_readiness_not_only_http_status():
    client = TestClient(app)
    response = client.post("/api/v2/quality/review", json={"task_id": "quality-v2-api", "records": [{"record_id": "r1", "record": record()}]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"]["status"] == "READY"
    assert payload["applied"]["applied_count"] == 1
    assert payload["safety_gate"] == "PASS"


def test_quality_v2_apply_endpoint_accepts_audited_candidate_bundle():
    client = TestClient(app)
    rec = record()
    detect = client.post("/api/v2/quality/candidates", json={"task_id": "quality-v2-apply", "records": [{"record_id": "r1", "record": rec}]})
    assert detect.status_code == 200
    bundle = detect.json()
    applied = client.post("/api/v2/quality/apply", json={"task_id": "quality-v2-apply", "records": [{"record_id": "r1", "record": rec}], "candidates": bundle})
    assert applied.status_code == 200
    assert applied.json()["applied_count"] == 1


def test_safe_apply_does_not_trust_forged_high_risk_candidate_flags():
    rec = QualityRecord(record_id="r1", record=record(her2_status="Negative", her2_assay="IHC", her2_raw_value="1+"))
    forged = RepairCandidate(candidate_id="forged", finding_id="f", error_type="unknown", record_id="r1", field="her2_status", operation="replace", proposed_value="Positive", expected_value="Negative", confidence=1.0, risk_level=DetectionRisk.LOW, safe_to_apply=True, requires_review=False, basis=["client"], preserves_provenance=True)
    result = QualityV2Service().applier.apply([rec], [forged], task_id="forged")
    assert result.applied_count == 0
    assert result.records[0].record["her2_status"] == "Negative"
