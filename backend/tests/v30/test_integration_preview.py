from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.integration.service import IntegrationPreviewService
from backend.app.v30.models import FieldMapping, IntegrationPreviewRequest, SchemaPackRequest
from backend.app.v30.schema_generator.service import ONCOLOGY_PACK_ID, SchemaPackGenerator

ROOT = Path(__file__).resolve().parents[3]
PREVIEW_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "integration"
FROZEN_FILES = (
    ROOT / "configs" / "canonical_schema.yaml",
    ROOT / "configs" / "medical_rules.yaml",
    ROOT / "backend" / "app" / "evidence" / "evidence_builder.py",
)
FORBIDDEN_MODULES = (
    "backend.app.sources",
    "backend.app.evidence",
    "backend.app.quality",
    "backend.app.quality_v2",
    "backend.app.agent.service",
    "backend.app.integration.schema_matcher_v3",
)
FORBIDDEN_NAMES = {
    "GEOAdapter",
    "GDCAdapter",
    "EvidenceBuilder",
    "ResearchAgentService",
    "CanonicalRecord",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _her2_request() -> IntegrationPreviewRequest:
    return IntegrationPreviewRequest(
        selected_sources=["geo", "gdc"],
        schema_pack_id=ONCOLOGY_PACK_ID,
        field_mappings=[
            FieldMapping(
                source_field="her2",
                target_field="her2_status",
                confidence=0.62,
                status="REVIEW",
                risk_level="high",
            )
        ],
        contract_id="contract-her2-demo",
        domain="oncology",
        response_domain="clinical",
        research_goal="HER2阳性乳腺癌耐药疗效预测",
    )


def test_preview_builds_execution_plan() -> None:
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌"))
    plan = IntegrationPreviewService(generator=generator).preview(_her2_request())
    assert plan.plan_id.startswith("intplan-")
    assert plan.schema_pack_id == ONCOLOGY_PACK_ID
    assert plan.sources == ["geo", "gdc"]
    by_key = {item.source_key: item for item in plan.adapter_candidates}
    assert by_key["geo"].fetch_binding == "search_geo"
    assert by_key["gdc"].fetch_binding == "search_gdc"
    assert all(item.would_invoke is False for item in plan.adapter_candidates)
    assert "her2_status" in plan.field_requirements
    assert plan.expected_outputs
    assert any("canonical_records: not written" in item for item in plan.expected_outputs)


def test_preview_does_not_call_adapters() -> None:
    hits: list[str] = []
    for path in PREVIEW_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == name or node.module.startswith(name + ".") for name in FORBIDDEN_MODULES):
                    hits.append(f"{path.name}:from {node.module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:import {alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == name or alias.name.startswith(name + ".") for name in FORBIDDEN_MODULES):
                        hits.append(f"{path.name}:import {alias.name}")
                    if alias.name.split(".")[-1] in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:import {alias.name}")
    assert hits == []
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌"))
    plan = IntegrationPreviewService(generator=generator).preview(_her2_request())
    assert plan.fetched is False
    assert plan.integrated is False


def test_execution_allowed_is_false() -> None:
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌"))
    plan = IntegrationPreviewService(generator=generator).preview(_her2_request())
    assert plan.execution_allowed is False
    client = TestClient(app)
    response = client.post("/api/v30/integration/preview", json=_her2_request().model_dump())
    assert response.status_code == 200
    body = response.json()
    assert body["execution_allowed"] is False
    assert "/api/v30/integration/preview" in client.get("/openapi.json").json()["paths"]


def test_preview_does_not_generate_csv() -> None:
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌"))
    plan = IntegrationPreviewService(generator=generator).preview(_her2_request())
    payload = plan.model_dump()
    assert plan.generates_data is False
    assert plan.row_count == 0
    assert "csv" not in payload
    assert any("csv_export: not created" in item for item in plan.expected_outputs)
    assert "canonical_dataset" not in payload
    assert "records" not in payload


def test_medical_constraints_are_preserved() -> None:
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌耐药"))
    plan = IntegrationPreviewService(generator=generator).preview(_her2_request())
    assert "response_domain" in plan.field_requirements
    assert "patient_id" in plan.field_requirements
    assert "sample_id" in plan.field_requirements
    assert plan.join_policy == "forbid_cross_entity"
    joined = " ".join(plan.medical_constraints)
    assert "response_domain" in joined
    assert "patient_id" in joined
    assert "Join" in joined or "join" in joined.lower()
    before = {path.name: _digest(path) for path in FROZEN_FILES}
    IntegrationPreviewService(generator=generator).preview(_her2_request())
    assert {path.name: _digest(path) for path in FROZEN_FILES} == before
