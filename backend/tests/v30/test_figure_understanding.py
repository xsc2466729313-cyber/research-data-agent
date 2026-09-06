from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.figures.service import FigureUnderstandingService, SourceIdRequiredError
from backend.app.v30.models import FigureUnderstandRequest

ROOT = Path(__file__).resolve().parents[3]
FIGURES_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "figures"
EVIDENCE_BUILDER = ROOT / "backend" / "app" / "evidence" / "evidence_builder.py"
FROZEN_FILES = (
    ROOT / "configs" / "canonical_schema.yaml",
    ROOT / "configs" / "medical_rules.yaml",
    EVIDENCE_BUILDER,
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


def test_source_id_allows_understanding() -> None:
    result = FigureUnderstandingService().understand(
        FigureUnderstandRequest(
            source_id="paper:sn-ia-demo",
            figure_id="Figure 3",
            caption="Ia型超新星论文 Figure 3 光变曲线",
        )
    )
    assert result.figure_type == "light_curve"
    assert result.x_axis == "phase_day"
    assert result.y_axis == "magnitude"
    assert result.digitization_possible is True
    assert result.extractability == "digitization_possible"
    assert result.confidence == 0.85
    assert result.status == "UNDERSTOOD"
    assert result.enters_primary_table is False
    assert result.source_id == "paper:sn-ia-demo"
    assert result.row_count == 0
    assert result.generates_data is False
    assert result.graph_id


def test_missing_source_id_is_rejected() -> None:
    service = FigureUnderstandingService()
    try:
        service.understand(FigureUnderstandRequest(figure_id="Figure 3", caption="Ia型超新星"))
        raise AssertionError("missing source_id must be rejected")
    except SourceIdRequiredError:
        pass
    try:
        service.understand(FigureUnderstandRequest(source_id="  ", figure_id="Figure 3"))
        raise AssertionError("blank source_id must be rejected")
    except SourceIdRequiredError:
        pass
    client = TestClient(app)
    response = client.post(
        "/api/v30/figures/understand",
        json={"figure_id": "Figure 3", "caption": "Ia型超新星光变曲线"},
    )
    assert response.status_code == 422
    assert response.json() == {"error": "source_id_required"}


def test_result_never_enters_primary_table() -> None:
    result = FigureUnderstandingService().understand(
        FigureUnderstandRequest(
            source_id="paper:sn-ia-demo",
            figure_id="Figure 3",
            caption="Ia型超新星论文 Figure 3",
            optional_image_reference="file://figures/fig3.png",
        )
    )
    payload = result.model_dump()
    assert result.enters_primary_table is False
    assert result.digitization_possible is True
    assert "observations" not in payload
    assert "canonical_record" not in payload
    assert "canonical_dataset" not in payload
    assert result.row_count == 0
    client = TestClient(app)
    response = client.post(
        "/api/v30/figures/understand",
        json={
            "source_id": "paper:sn-ia-demo",
            "figure_id": "Figure 3",
            "caption": "Ia型超新星论文 Figure 3 光变曲线",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enters_primary_table"] is False
    assert body["figure_type"] == "light_curve"
    graph = client.get(f"/api/v30/graphs/{body['graph_id']}")
    assert graph.status_code == 200
    nodes = graph.json()["nodes"]
    figure = next(node for node in nodes if node["node_type"] == "FigureUnderstanding")
    paper = next(node for node in nodes if node["node_type"] in {"Paper", "File"})
    edge = next(item for item in graph.json()["edges"] if item["edge_type"] == "EXTRACTED_FROM")
    assert edge["from_id"] == figure["node_id"]
    assert edge["to_id"] == paper["node_id"]
    assert figure["refs"]["enters_primary_table"] is False
    assert "raw_value" not in figure["refs"]
    assert "canonical_value" not in figure["refs"]


def test_figure_understanding_does_not_call_adapters() -> None:
    hits: list[str] = []
    for path in FIGURES_ROOT.glob("*.py"):
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
    client = TestClient(app)
    assert "/api/v30/figures/understand" in client.get("/openapi.json").json()["paths"]


def test_evidence_builder_is_unchanged() -> None:
    before = {path.name: _digest(path) for path in FROZEN_FILES}
    FigureUnderstandingService().understand(
        FigureUnderstandRequest(
            source_id="paper:sn-ia-demo",
            figure_id="Figure 3",
            caption="Ia型超新星论文 Figure 3 光变曲线",
        )
    )
    assert {path.name: _digest(path) for path in FROZEN_FILES} == before
    text = EVIDENCE_BUILDER.read_text(encoding="utf-8")
    assert "FigureUnderstanding" not in text
    assert "/api/v30/figures/understand" not in text
