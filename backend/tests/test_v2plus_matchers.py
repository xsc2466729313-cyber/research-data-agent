from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.integration import EntityMatcherV2Plus, SchemaMatcherV2Plus
from backend.app.main import app


def test_schema_v2plus_keeps_v2_target_but_blocks_erbb2_cna_as_her2_status() -> None:
    result = SchemaMatcherV2Plus().match(
        ["ERBB2 CNA"], ["her2_status"],
        source_values={"ERBB2 CNA": ["Amplified"]},
    )[0]
    assert result.target_field == "her2_status"
    assert result.decision == "REJECT"
    assert "ERBB2_CNA_NOT_IHC" in result.safety_rule_hits
    assert "v2" in result.evidence and "v3_audit" in result.evidence


def test_schema_v2plus_downgrades_her2_ihc_2plus_auto_proposal_to_review() -> None:
    result = SchemaMatcherV2Plus().match(
        ["HER2 IHC"], ["her2_status"],
        source_values={"HER2 IHC": ["2+"]},
    )[0]
    assert result.decision != "AUTO"
    assert "HER2_IHC_2PLUS" in result.safety_rule_hits


def test_entity_v2plus_requires_explicit_linker_authorization_for_auto() -> None:
    left = [{"id": "l1", "study_id": "s1", "patient_id": "p1", "name": "Alice Smith", "age": 60}]
    right = [{"id": "r1", "study_id": "s1", "patient_id": "p1", "name": "Alice Smith", "age": 60}]
    assert EntityMatcherV2Plus().match(left, right)[0].decision == "REVIEW"
    assert EntityMatcherV2Plus().match(left, right, linker_authorized=True)[0].decision == "AUTO"


def test_entity_v2plus_blocks_sample_conflict_and_api_returns_audit() -> None:
    left = [{"id": "l1", "study_id": "s1", "patient_id": "p1", "sample_id": "a", "name": "Alice Smith"}]
    right = [{"id": "r1", "study_id": "s1", "patient_id": "p1", "sample_id": "b", "name": "Alice Smith"}]
    response = TestClient(app).post("/api/v2/entity/match-v2plus", json={"left": left, "right": right, "linker_authorized": True})
    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert match["decision"] == "REJECT"
    assert "SAMPLE_ID_CONTRADICTION" in match["safety_rule_hits"]
