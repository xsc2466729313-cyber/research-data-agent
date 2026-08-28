from __future__ import annotations

from backend.app.integration import SchemaMatcherV3
from fastapi.testclient import TestClient
from backend.app.main import app


def test_schema_matcher_v3_exposes_all_auditable_features() -> None:
    result = SchemaMatcherV3().match(
        ["age_at_diagnosis"],
        ["patient_age", "her2_status"],
        source_types={"age_at_diagnosis": "numeric"},
        target_types={"patient_age": "numeric", "her2_status": "categorical"},
        source_values={"age_at_diagnosis": [60, 61]},
        target_values={"patient_age": [60, 61]},
        source_table="clinical",
        target_table="clinical",
    )[0]
    assert result.target_field == "patient_age"
    assert set(("lexical", "alias", "value_profile", "type", "cardinality", "embedding", "table_context", "ontology")).issubset(result.evidence)
    assert result.decision in {"AUTO", "REVIEW", "REJECT"}
    assert result.decision_source == "ALGORITHM"


def test_schema_matcher_v3_calls_judge_only_for_ambiguous_review_cases() -> None:
    calls: list[dict[str, object]] = []

    def judge(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {"best_candidate": "patient_age", "confidence": 0.93, "reason": "field and values agree"}

    matcher = SchemaMatcherV3(judge=judge)
    result = matcher.match(
        ["age"], ["patient_age", "age_at_diagnosis"],
        source_types={"age": "numeric"},
        target_types={"patient_age": "numeric", "age_at_diagnosis": "numeric"},
    )[0]
    assert calls
    assert matcher.qwen_invocation_count == 1
    assert result.target_field == "patient_age"
    assert result.decision_source == "QWEN_JUDGE"
    assert result.judge_reason == "field and values agree"


def test_schema_matcher_v3_judge_failure_fails_closed_to_review() -> None:
    def broken(_payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("unavailable")

    result = SchemaMatcherV3(judge=broken).match(["age"], ["patient_age"])[0]
    assert result.decision == "REVIEW"
    assert result.evidence["judge_failed"] is True
    assert result.decision_source == "ALGORITHM"


def test_schema_matcher_v3_api_returns_audited_matches() -> None:
    response = TestClient(app).post(
        "/api/v2/schema/match",
        json={
            "source_fields": ["age_at_diagnosis"],
            "target_fields": ["patient_age"],
            "source_types": {"age_at_diagnosis": "numeric"},
            "target_types": {"patient_age": "numeric"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matcher_version"] == "schema-matcher-v3.0"
    assert payload["matches"][0]["decision"] in {"AUTO", "REVIEW", "REJECT"}
    assert "semantic_contradiction" in payload["matches"][0]["evidence"]
