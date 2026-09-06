from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import httpx

from backend.app.agent import AgentDatasetExportService, AgentExportFormat, QwenClient, QwenSettings, ResearchAgentService
from backend.app.agent.models import AgentToolCall
from backend.app.main import app
from backend.app.sources.cbioportal import CBioPortalAdapter
from backend.app.sources.discovery import DiscoveryAdapter
from backend.app.v30.bridges.execution import ExecutionBridge
from backend.app.v30.integration.executor import OncologyIntegrateNotAllowedError
from backend.app.v30.integration.service import IntegrationPreviewService
from backend.app.v30.models import (
    ExecutionRequestPreview,
    FieldMapping,
    IntegrationPreviewRequest,
    SchemaPackRequest,
)
from backend.app.v30.schema_generator.service import ONCOLOGY_PACK_ID, SchemaPackGenerator
from backend.tests.test_cbioportal_adapter import CNA_ROWS, GENES, MUTATIONS, json_response, standard_handler
from backend.tests.test_research_agent import QUESTION, discovery_handler, qwen_handler

ROOT = Path(__file__).resolve().parents[3]
EXECUTOR = Path(__file__).resolve().parents[2] / "app" / "v30" / "integration" / "executor.py"
FROZEN_FILES = (
    ROOT / "configs" / "canonical_schema.yaml",
    ROOT / "configs" / "medical_rules.yaml",
    ROOT / "backend" / "app" / "agent" / "service.py",
    ROOT / "backend" / "app" / "evidence" / "evidence_builder.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _her2_preview() -> ExecutionRequestPreview:
    generator = SchemaPackGenerator()
    generator.generate(SchemaPackRequest(domain="oncology", research_goal="HER2阳性乳腺癌耐药疗效预测"))
    plan = IntegrationPreviewService(generator=generator).preview(
        IntegrationPreviewRequest(
            selected_sources=["geo", "gdc", "cbioportal"],
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
            research_goal="HER2阳性乳腺癌耐药疗效预测",
        )
    )
    preview = ExecutionBridge(generator=generator).prepare(plan)
    preview.question = QUESTION
    preview.selected_sources = ["cbioportal"]
    preview.tool_candidates = ["search_cbioportal"]
    return preview


def _loose_cbioportal_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/genes/fetch":
        return json_response(request, GENES)
    if path.endswith("/brca_metabric_mutations/mutations/fetch"):
        return json_response(request, MUTATIONS)
    if path.endswith("/brca_metabric_cna/discrete-copy-number/fetch"):
        return json_response(request, CNA_ROWS)
    return standard_handler(request)


def _build_agent(tmp_path: Path) -> ResearchAgentService:
    qwen = QwenClient(
        settings=QwenSettings(
            api_key="test-key",
            base_url="https://ws-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            workspace_id="ws-test",
        ),
        client=httpx.Client(transport=httpx.MockTransport(qwen_handler)),
    )
    cbio = CBioPortalAdapter(
        cache_dir=tmp_path / "cbio",
        client=httpx.Client(transport=httpx.MockTransport(_loose_cbioportal_handler)),
    )
    discovery = DiscoveryAdapter(client=httpx.Client(transport=httpx.MockTransport(discovery_handler)))
    return ResearchAgentService(qwen_client=qwen, cbioportal_adapter=cbio, discovery_adapter=discovery)


def _isolate_cbioportal(service: ResearchAgentService) -> None:
    original = service._execute_tool

    def gated(call, spec, max_records):
        name = str(call.get("name") or "")
        if name != "search_cbioportal":
            now = datetime.now(timezone.utc)
            return (
                AgentToolCall(
                    call_id=str(call.get("id") or "skip"),
                    tool_name=name,
                    tool_label=name,
                    arguments=dict(call.get("arguments") or {}),
                    status="跳过",
                    message="test isolation: only the existing cBioPortal adapter is exercised",
                    started_at=now,
                    completed_at=now,
                ),
                None,
            )
        return original(call, spec, max_records)

    service._execute_tool = gated  # type: ignore[method-assign]


def test_her2_case_enters_real_execution(tmp_path: Path) -> None:
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    called: list[object] = []
    original_run = service.run

    def tracked(request, **kwargs):
        called.append(request)
        return original_run(request, **kwargs)

    service.run = tracked  # type: ignore[method-assign]
    result = ExecutionBridge().execute(preview, runner=service)
    assert called
    assert result.task_id
    assert result.executed is True
    assert result.domain == "oncology"
    assert result.status
    assert result.join_policy == "forbid_cross_entity"


def test_execution_bridge_calls_old_runner(tmp_path: Path) -> None:
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    result = ExecutionBridge().execute(preview, runner=service)
    assert result.executed is True
    text = EXECUTOR.read_text(encoding="utf-8")
    assert "backend.app.agent.models" in text
    assert "backend.app.sources" not in text
    assert "GEOAdapter" not in text
    assert "GDCAdapter" not in text
    hits: list[str] = []
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "backend.app.agent.service":
            hits.append(node.module)
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "ResearchAgentService":
                    hits.append(alias.name)
    assert hits == []


def test_adapter_returns_through_old_chain(tmp_path: Path) -> None:
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    raw = []

    def runner(request):
        result = service.run(request)
        raw.append(result)
        return result

    result = ExecutionBridge().execute(preview, runner=runner)
    assert raw
    assert any(call.tool_name == "search_cbioportal" and call.status == "完成" for call in raw[0].tool_calls)
    assert raw[0].modeling_dataset.row_count >= 1
    assert result.evidence_summary["row_count"] >= 1


def test_quality_gate_still_applies(tmp_path: Path) -> None:
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    captured = []

    def runner(request):
        result = service.run(request)
        captured.append(result)
        return result

    summary = ExecutionBridge().execute(preview, runner=runner)
    assert captured[0].quality_gate_report is not None
    assert captured[0].quality_gate_report.overall in {"PASS", "REVIEW", "REJECT"}
    assert summary.quality_status in {"PASS", "REVIEW", "REJECT"}


def test_evidence_and_export_are_produced(tmp_path: Path) -> None:
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    captured = []

    def runner(request):
        result = service.run(request)
        captured.append(result)
        return result

    summary = ExecutionBridge().execute(preview, runner=runner)
    raw = captured[0]
    names = {column.name for column in raw.modeling_dataset.columns}
    row = raw.modeling_dataset.rows[0]
    assert "source_id" in names or row.get("source_id") or raw.source_items
    assert summary.evidence_summary["has_source_id"] is True
    assert summary.evidence_summary["has_evidence"] is True
    assert "response_domain" in preview.required_fields
    assert "patient_id" in preview.required_fields
    assert "sample_id" in preview.required_fields
    exporter = AgentDatasetExportService()
    metadata = exporter.export(raw, AgentExportFormat.METADATA)
    quality = exporter.export(raw, AgentExportFormat.QUALITY_REPORT)
    assert metadata.filename.endswith(".json")
    assert quality.filename.endswith(".json")
    if raw.modeling_dataset.rows:
        csv_file = exporter.export(raw, AgentExportFormat.CSV)
        assert csv_file.filename.endswith(".csv")
        assert csv_file.content
    assert summary.export_available is True
    assert "metadata" in summary.export_formats
    joined = " ".join(summary.medical_constraints)
    assert "response_domain" in joined
    assert "Join" in joined or "forbid_cross_entity" in summary.join_policy


def test_astronomy_is_rejected() -> None:
    preview = ExecutionRequestPreview(
        plan_id="intplan-astro",
        schema_pack_id="task-astronomy-sn-ia",
        selected_sources=["nasa_mast"],
        tool_candidates=[],
        required_fields=["sn_id", "flux"],
        execution_ready=True,
        join_policy="file_only",
        domain="astronomy",
    )

    def boom(_request):
        raise AssertionError("astronomy must not enter the old runner")

    try:
        ExecutionBridge().execute(preview, runner=boom)
        raise AssertionError("astronomy integrate must be rejected")
    except OncologyIntegrateNotAllowedError:
        pass
    client = TestClient(app)
    response = client.post("/api/v30/integration/execute", json=preview.model_dump())
    assert response.status_code == 422
    assert response.json() == {"error": "only_oncology_integrate_supported"}


def test_frozen_kernels_unchanged(tmp_path: Path) -> None:
    before = {path.name: _digest(path) for path in FROZEN_FILES}
    preview = _her2_preview()
    service = _build_agent(tmp_path)
    _isolate_cbioportal(service)
    ExecutionBridge().execute(preview, runner=service)
    assert {path.name: _digest(path) for path in FROZEN_FILES} == before
    assert "/api/v30/integration/execute" in TestClient(app).get("/openapi.json").json()["paths"]
