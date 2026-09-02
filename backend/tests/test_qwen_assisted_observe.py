from __future__ import annotations

from types import SimpleNamespace

from backend.app.evaluation.observe import observe_error, observe_field


class StubQwen:
    def __init__(self, field_payload=None, error_payload=None):
        self.field_payload = field_payload or {}
        self.error_payload = error_payload or {}

    def normalize_research_field(self, **_kwargs):
        return self.field_payload

    def diagnose_research_error(self, **_kwargs):
        return self.error_payload


def field_row(canonical_field: str, canonical_value: str = ""):
    return SimpleNamespace(
        case_id=f"field-{canonical_field}",
        source_dataset="GSE50948",
        raw_field="HER2 IHC",
        raw_value="3+",
        canonical_field=canonical_field,
        canonical_value=canonical_value,
    )


def test_qwen_field_mapping_emits_all_supported_companion_fields() -> None:
    qwen = StubQwen(
        field_payload={
            "canonical_values": {
                "her2_status": "Positive",
                "her2_assay": "IHC",
                "her2_raw_value": "3+",
            },
            "confidence": 0.99,
            "needs_review": False,
        }
    )

    for field, value in (
        ("her2_status", "Positive"),
        ("her2_assay", "IHC"),
        ("her2_raw_value", "3+"),
    ):
        observation, trace = observe_field(field_row(field), qwen_client=qwen)
        assert observation.canonical_field == field
        assert observation.canonical_value == value
        assert trace["qwen"]["proposed_target"] is True
        assert trace["qwen"]["rule_fallback"] is False


def test_qwen_field_mapping_uses_rules_for_omitted_target() -> None:
    qwen = StubQwen(field_payload={"canonical_values": {"her2_status": "Positive"}})

    observation, trace = observe_field(field_row("her2_assay"), qwen_client=qwen)

    assert observation.canonical_value == "IHC"
    assert trace["qwen"]["proposed_target"] is False
    assert trace["qwen"]["rule_fallback"] is True


def test_deterministic_validator_overrides_qwen_id_rewriting() -> None:
    row = SimpleNamespace(
        case_id="patient-id",
        source_dataset="GSE25066",
        raw_field="subject",
        raw_value="PT001",
        canonical_field="patient_id",
        canonical_value="PT001",
    )
    qwen = StubQwen(field_payload={"canonical_values": {"patient_id": "geo:PT001"}})

    observation, trace = observe_field(row, qwen_client=qwen)

    assert observation.canonical_value == "PT001"
    assert trace["qwen"]["rule_override"] is True


def test_qwen_cannot_override_frozen_ihc_2plus_rule() -> None:
    row = field_row("her2_status")
    row.raw_value = "2+"
    qwen = StubQwen(field_payload={"canonical_values": {"her2_status": "Positive"}})

    observation, _ = observe_field(row, qwen_client=qwen)

    assert observation.canonical_value == "Equivocal"


def test_qwen_error_detection_is_combined_with_safe_rule_detection() -> None:
    row = SimpleNamespace(
        case_id="error-qwen",
        original_record='{"stage":"Stge II","source_id":"geo:GSE1","raw_field":"stage","raw_value":"Stge II"}',
        error_type="typo",
        auto_repair_allowed=False,
    )
    qwen = StubQwen(
        error_payload={
            "detected": True,
            "error_type": "typo",
            "candidate_repair": {"field": "stage", "value": "Stage II"},
            "needs_review": True,
        }
    )

    observation, trace = observe_error(row, qwen_client=qwen)

    assert observation.detected is True
    assert observation.auto_repair_executed is False
    assert trace["qwen_matched_expected_type"] is True
