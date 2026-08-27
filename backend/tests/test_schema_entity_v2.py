from backend.app.integration import EntityMatcherV2, SchemaMatcherV2


def test_schema_matcher_exposes_safety_decision():
    match = SchemaMatcherV2().match(["age_at_diagnosis"], ["patient_age"], source_types={"age_at_diagnosis": "numeric"}, target_types={"patient_age": "numeric"})[0]
    assert match.decision in {"AUTO", "REVIEW", "REJECT"}
    assert "lexical" in match.evidence


def test_entity_matcher_rejects_study_conflict():
    result = EntityMatcherV2().match([{"id": "a", "study_id": "s1", "name": "x"}], [{"id": "b", "study_id": "s2", "name": "x"}])[0]
    assert result.status == "REJECT"
