from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from backend.app.models import CanonicalRecord, EvidenceCell, ResearchSpec, SourceItem


ROOT = Path(__file__).resolve().parents[2]


def test_canonical_model_matches_frozen_yaml_fields_and_required_flags() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "canonical_schema.yaml").read_text(encoding="utf-8")
    )
    configured_fields = config["fields"]

    assert config["frozen"] is True
    assert list(CanonicalRecord.model_fields) == list(configured_fields)

    required_by_model = {
        name for name, field in CanonicalRecord.model_fields.items() if field.is_required()
    }
    required_by_config = {
        name for name, spec in configured_fields.items() if spec["required"]
    }
    assert required_by_model == required_by_config


def test_supplied_json_assets_validate_against_pydantic_models() -> None:
    research_payload = json.loads(
        (ROOT / "mock" / "research_spec.json").read_text(encoding="utf-8")
    )
    assert ResearchSpec.model_validate(research_payload).disease == "Breast Cancer"

    source_lines = (ROOT / "mock" / "source_items.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    evidence_lines = (ROOT / "mock" / "evidence.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert SourceItem.model_validate_json(source_lines[0]).status == "mock"
    assert EvidenceCell.model_validate_json(evidence_lines[1]).raw_value == "2+"


def test_her2_ihc_2plus_cannot_be_positive() -> None:
    with pytest.raises(ValidationError, match="cannot be automatically mapped"):
        CanonicalRecord(
            study_id="mock-study",
            disease="Breast Cancer",
            her2_status="Positive",
            her2_assay="IHC",
            her2_raw_value="2+",
            source_id="mock-source",
            raw_field="HER2_IHC",
            raw_value="2+",
            confidence=0.9,
        )


def test_her2_ihc_2plus_equivocal_preserves_raw_values() -> None:
    record = CanonicalRecord(
        study_id="mock-study",
        disease="Breast Cancer",
        her2_status="Equivocal",
        her2_assay="IHC",
        her2_raw_value="2+",
        source_id="mock-source",
        raw_field="HER2_IHC",
        raw_value="2+",
        confidence=0.9,
    )
    assert record.her2_status.value == "Equivocal"
    assert record.raw_field == "HER2_IHC"
    assert record.raw_value == "2+"


def test_response_domain_rejects_cross_domain_free_text() -> None:
    with pytest.raises(ValidationError):
        CanonicalRecord(
            study_id="mock-study",
            disease="Breast Cancer",
            response_domain="patient_and_cell_line",
            source_id="mock-source",
            raw_field="response",
            raw_value="0.4",
            confidence=0.8,
        )

