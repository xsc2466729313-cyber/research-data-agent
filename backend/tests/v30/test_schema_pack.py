from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.models import SchemaPackRequest
from backend.app.v30.schema_generator.service import ONCOLOGY_PACK_ID, SchemaPackGenerator, index_points_to_frozen_schema

ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "configs" / "canonical_schema.yaml"
SN_FIELDS = {
    "sn_id",
    "observation_time",
    "band",
    "flux",
    "redshift",
    "source_id",
    "raw_field",
    "raw_value",
}


def _canonical_digest() -> str:
    return hashlib.sha256(CANONICAL.read_bytes()).hexdigest()


def test_oncology_binds_frozen_schema() -> None:
    before = _canonical_digest()
    frozen_names = set((yaml.safe_load(CANONICAL.read_text(encoding="utf-8")) or {})["fields"])
    pack = SchemaPackGenerator().generate(
        SchemaPackRequest(
            domain="oncology",
            research_goal="HER2阳性乳腺癌耐药疗效预测",
            selected_sources=["geo", "gdc"],
        )
    )
    assert pack.schema_pack_id == ONCOLOGY_PACK_ID
    assert pack.binding == "frozen_canonical"
    assert pack.entity_type == "patient"
    assert pack.row_count == 0
    assert pack.generates_data is False
    names = [item.name for item in pack.fields]
    assert set(names) == frozen_names
    assert {"patient_id", "her2_status", "her2_assay", "response", "response_domain", "source_id"} <= set(names)
    assert all(item.frozen is True for item in pack.fields)
    assert next(item for item in pack.fields if item.name == "her2_status").risk_level == "high"
    assert _canonical_digest() == before
    assert index_points_to_frozen_schema()


def test_astronomy_generates_task_schema() -> None:
    before = _canonical_digest()
    pack = SchemaPackGenerator().generate(
        SchemaPackRequest(
            domain="astronomy",
            research_goal="Ia型超新星光变与红移",
            selected_sources=["nasa_mast"],
        )
    )
    assert pack.binding == "generated_task"
    assert pack.status == "DRAFT"
    assert pack.domain == "astronomy"
    assert pack.row_count == 0
    assert pack.generates_data is False
    names = [item.name for item in pack.fields]
    assert names == [
        "sn_id",
        "observation_time",
        "band",
        "flux",
        "redshift",
        "source_id",
        "raw_field",
        "raw_value",
    ]
    assert set(names) == SN_FIELDS
    assert "her2_status" not in names
    assert "patient_id" not in names
    assert "response_domain" not in names
    assert _canonical_digest() == before


def test_schema_generator_does_not_emit_data_rows() -> None:
    generator = SchemaPackGenerator()
    oncology = generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2乳腺癌"))
    astronomy = generator.generate(SchemaPackRequest(domain="astronomy", research_goal="Ia型超新星"))
    for pack in (oncology, astronomy):
        assert pack.row_count == 0
        assert pack.generates_data is False
        dumped = pack.model_dump()
        assert "canonical_dataset" not in dumped
        assert "records" not in dumped
        assert dumped.get("fields")


def test_schema_pack_api_roundtrip_does_not_touch_matcher() -> None:
    before = _canonical_digest()
    client = TestClient(app)
    created = client.post(
        "/api/v30/schema-packs/generate",
        json={"domain": "oncology", "research_goal": "HER2阳性乳腺癌"},
    )
    assert created.status_code == 200
    pack_id = created.json()["schema_pack_id"]
    fetched = client.get(f"/api/v30/schema-packs/{pack_id}")
    assert fetched.status_code == 200
    assert fetched.json()["binding"] == "frozen_canonical"
    sn = client.post(
        "/api/v30/schema-packs/generate",
        json={"domain": "astronomy", "research_goal": "Ia型超新星"},
    )
    assert sn.status_code == 200
    assert {item["name"] for item in sn.json()["fields"]} == SN_FIELDS
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v30/schema-packs/generate" in paths
    assert "/api/v2/schema/match" in paths
    assert _canonical_digest() == before
