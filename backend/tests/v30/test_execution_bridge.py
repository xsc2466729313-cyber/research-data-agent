from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.bridges.execution import ExecutionBridge
from backend.app.v30.integration.service import IntegrationPreviewService
from backend.app.v30.models import FieldMapping, IntegrationPreviewRequest, SchemaPackRequest
from backend.app.v30.schema_generator.service import ONCOLOGY_PACK_ID, SchemaPackGenerator

ROOT = Path(__file__).resolve().parents[3]
BRIDGE_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "bridges"
FROZEN_FILES = (
    ROOT / "configs" / "canonical_schema.yaml",
    ROOT / "configs" / "medical_rules.yaml",
    ROOT / "backend" / "app" / "evidence" / "evidence_builder.py",
    ROOT / "backend" / "app" / "agent" / "service.py",
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


def _her2_plan():
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌耐药疗效预测"))
    plan = IntegrationPreviewService(generator=generator).preview(
        IntegrationPreviewRequest(
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
    )
    plan.field_mappings = [
        FieldMapping(
            source_field="her2",
            target_field="her2_status",
            confidence=0.62,
            status="REVIEW",
            risk_level="high",
        )
    ]
    return plan, generator


def test_plan_converts_to_execution_request_preview() -> None:
    plan, generator = _her2_plan()
    preview = ExecutionBridge(generator=generator).prepare(plan)
    assert preview.plan_id == plan.plan_id
    assert preview.contract_id == "contract-her2-demo"
    assert preview.schema_pack_id == ONCOLOGY_PACK_ID
    assert preview.selected_sources == ["geo", "gdc"]
    assert preview.required_fields


def test_tool_candidates_include_existing_bindings() -> None:
    plan, generator = _her2_plan()
    preview = ExecutionBridge(generator=generator).prepare(plan)
    assert "search_geo" in preview.tool_candidates
    assert "search_gdc" in preview.tool_candidates


def test_execution_ready_true_but_not_executed() -> None:
    plan, generator = _her2_plan()
    preview = ExecutionBridge(generator=generator).prepare(plan)
    assert preview.execution_ready is True
    assert preview.executed is False
    client = TestClient(app)
    created = client.post(
        "/api/v30/integration/preview",
        json={
            "selected_sources": ["geo", "gdc"],
            "schema_pack_id": ONCOLOGY_PACK_ID,
            "contract_id": "contract-her2-demo",
            "domain": "oncology",
            "research_goal": "HER2阳性乳腺癌",
        },
    )
    assert created.status_code == 200
    prepared = client.post("/api/v30/integration/prepare", json=created.json())
    assert prepared.status_code == 200
    body = prepared.json()
    assert body["execution_ready"] is True
    assert body["executed"] is False
    assert "/api/v30/integration/prepare" in client.get("/openapi.json").json()["paths"]


def test_bridge_does_not_call_agent_or_adapters() -> None:
    hits: list[str] = []
    for path in BRIDGE_ROOT.glob("*.py"):
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


def test_bridge_does_not_generate_csv() -> None:
    plan, generator = _her2_plan()
    preview = ExecutionBridge(generator=generator).prepare(plan)
    payload = preview.model_dump()
    assert preview.generates_data is False
    assert preview.row_count == 0
    assert preview.fetched is False
    assert preview.integrated is False
    assert "csv" not in payload
    assert "canonical_dataset" not in payload
    assert "records" not in payload


def test_medical_constraints_survive_prepare() -> None:
    plan, generator = _her2_plan()
    before = {path.name: _digest(path) for path in FROZEN_FILES}
    preview = ExecutionBridge(generator=generator).prepare(plan)
    assert "response_domain" in preview.required_fields
    assert "patient_id" in preview.required_fields
    assert "sample_id" in preview.required_fields
    assert preview.join_policy == "forbid_cross_entity"
    joined = " ".join(preview.medical_constraints)
    assert "response_domain" in joined
    assert "Join" in joined or "join" in joined.lower()
    assert "IHC 2+" in joined or "Positive" in joined
    assert "AUC" in joined or "IC50" in joined
    assert {path.name: _digest(path) for path in FROZEN_FILES} == before
    assert "ResearchAgentService" not in (BRIDGE_ROOT / "execution.py").read_text(encoding="utf-8")
