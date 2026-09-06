from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.integration.schema_matcher_v3 import SchemaMatcherV3
from backend.app.main import app
from backend.app.v30.matcher_bridge.service import SchemaMatcherBridge
from backend.app.v30.models import SchemaMatchRequest, SchemaPackRequest
from backend.app.v30.schema_generator.service import ONCOLOGY_PACK_ID, SchemaPackGenerator

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "configs" / "canonical_schema.yaml"
MATCHER_FILES = (
    ROOT / "backend" / "app" / "integration" / "schema_matcher_v2.py",
    ROOT / "backend" / "app" / "integration" / "schema_matcher_v3.py",
    ROOT / "backend" / "app" / "integration" / "schema_matcher_v2plus.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_oncology_pack_calls_existing_matcher(monkeypatch) -> None:
    before = {path.name: _digest(path) for path in MATCHER_FILES}
    canonical_before = _digest(CANONICAL)
    captured: list[list[str]] = []
    original = SchemaMatcherV3.match

    def wrapped(self, source_fields, target_fields, **kwargs):
        captured.append(list(target_fields))
        return original(self, source_fields, target_fields, **kwargs)

    monkeypatch.setattr(SchemaMatcherV3, "match", wrapped)
    generator = SchemaPackGenerator()
    pack = generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌"))
    result = SchemaMatcherBridge(generator=generator).map_fields(
        SchemaMatchRequest(
            schema_pack_id=pack.schema_pack_id,
            source_fields=["her2", "patient_id", "response_domain", "source_id"],
        )
    )
    assert captured
    assert "her2_status" in captured[0]
    assert "response_domain" in captured[0]
    assert "patient_id" in captured[0]
    by_source = {item.source_field: item for item in result.mappings}
    assert by_source["her2"].target_field == "her2_status"
    assert by_source["response_domain"].target_field == "response_domain"
    assert by_source["her2"].risk_level == "high"
    assert result.row_count == 0
    assert result.generates_data is False
    assert result.schema_pack_id == ONCOLOGY_PACK_ID
    assert _digest(CANONICAL) == canonical_before
    assert {path.name: _digest(path) for path in MATCHER_FILES} == before


def test_astronomy_pack_can_map_task_fields() -> None:
    generator = SchemaPackGenerator()
    pack = generator.generate(SchemaPackRequest(domain="astronomy", research_goal="Ia型超新星"))
    result = SchemaMatcherBridge(generator=generator).map_fields(
        SchemaMatchRequest(
            schema_pack_id=pack.schema_pack_id,
            source_fields=["MJD", "band", "mag", "redshift", "source_id", "raw_field", "raw_value"],
        )
    )
    mapped = {item.source_field: item.target_field for item in result.mappings}
    assert mapped["MJD"] == "observation_time"
    assert mapped["band"] == "band"
    assert mapped["mag"] == "flux"
    assert mapped["redshift"] == "redshift"
    assert mapped["source_id"] == "source_id"
    assert mapped["raw_field"] == "raw_field"
    assert mapped["raw_value"] == "raw_value"
    assert result.row_count == 0
    assert result.generates_data is False
    assert "canonical_dataset" not in result.model_dump()


def test_matcher_bridge_api_does_not_write_rows() -> None:
    before = _digest(CANONICAL)
    client = TestClient(app)
    pack = client.post(
        "/api/v30/schema-packs/generate",
        json={"domain": "oncology", "research_goal": "HER2阳性乳腺癌"},
    ).json()
    matched = client.post(
        "/api/v30/schema-packs/match",
        json={"schema_pack_id": pack["schema_pack_id"], "source_fields": ["her2", "response_domain"]},
    )
    assert matched.status_code == 200
    payload = matched.json()
    assert payload["row_count"] == 0
    assert payload["generates_data"] is False
    assert payload["mappings"]
    assert "/api/v2/schema/match" in client.get("/openapi.json").json()["paths"]
    assert _digest(CANONICAL) == before
