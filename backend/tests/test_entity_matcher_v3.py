from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.integration import EntityMatcherV3
from backend.app.main import app
from backend.app.integration.patient_sample_linker import PatientSampleLinker
from backend.app.evaluation.public_entity import fit_entity_v3_threshold


def _left() -> list[dict[str, object]]:
    return [{"id": "l1", "study_id": "s1", "patient_id": "p1", "name": "Alice Smith", "age": 60}]


def _right() -> list[dict[str, object]]:
    return [{"id": "r1", "study_id": "s1", "patient_id": "p1", "name": "Alice Smith", "age": 60}]


def test_entity_matcher_v3_requires_linker_for_automatic_link() -> None:
    matcher = EntityMatcherV3()
    review = matcher.match(_left(), _right())[0]
    assert review.model_confidence >= 0.9
    assert review.decision == "REVIEW"
    assert "PATIENT_SAMPLE_LINKER_REQUIRED" in review.safety_rule_hits
    linked = matcher.match(_left(), _right(), patient_sample_linker=PatientSampleLinker())[0]
    assert linked.decision == "LINK"


def test_entity_matcher_v3_rejects_identity_and_study_conflicts() -> None:
    matcher = EntityMatcherV3()
    patient_conflict = matcher.match(_left(), [{**_right()[0], "patient_id": "p9"}])[0]
    assert patient_conflict.decision == "REJECT"
    assert "PATIENT_ID_CONTRADICTION" in patient_conflict.safety_rule_hits
    cross_study = matcher.match(_left(), [{**_right()[0], "study_id": "s2"}])[0]
    assert cross_study.decision == "REJECT"
    assert "CROSS_STUDY_JOIN_FORBIDDEN" in cross_study.safety_rule_hits


def test_entity_matcher_v3_api_exposes_safety_audit() -> None:
    response = TestClient(app).post("/api/v2/entity/match", json={"left": _left(), "right": _right()})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matcher_version"] == "entity-matcher-v3.0"
    assert payload["matches"][0]["decision"] == "REVIEW"
    assert payload["matches"][0]["safety_rule_hits"]


def test_entity_v3_threshold_calibration_uses_development_pairs_only() -> None:
    positive = ({"id": "a", "name": "Alice Smith"}, {"id": "b", "name": "Alice Smith"}, 1)
    negative = ({"id": "c", "name": "Alice Smith"}, {"id": "d", "name": "Bob Jones"}, 0)
    config = fit_entity_v3_threshold([positive, negative], [positive, negative])
    assert config.fit_split == "train_valid"
    assert 0.2 <= config.review_threshold <= 0.9
    assert config.auto_threshold == 0.9
