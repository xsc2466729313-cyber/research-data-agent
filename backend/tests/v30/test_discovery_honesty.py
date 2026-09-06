from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.discovery.service import DiscoveryFacade
from backend.app.v30.models import DiscoverRequest

DISCOVERY_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "discovery"
FORBIDDEN_MODULES = (
    "backend.app.sources",
    "backend.app.agent.service",
    "backend.app.source_broker",
    "backend.app.quality",
    "backend.app.quality_v2",
)
FORBIDDEN_NAMES = {
    "ResearchAgentService",
    "GDCAdapter",
    "GEOAdapter",
    "CBioPortalAdapter",
    "WeightedSetCoverOptimizer",
    "SourceBroker",
    "SchemaMatcher",
}


def test_geo_candidate_is_generated_but_not_fetched() -> None:
    result = DiscoveryFacade().discover(
        DiscoverRequest(
            domain="oncology",
            topic="HER2阳性乳腺癌耐药机制",
            required_modalities=["expression", "clinical_table"],
            field_gaps=["gene_expression", "treatment_response"],
        )
    )
    geo = next(item for item in result.candidates if item.source_key == "geo")
    assert geo.resource_kind
    assert geo.locator.locator_type
    assert geo.source_id == "registry:geo"
    assert geo.discovered_from == "registry"
    assert geo.verification_status == "unverified"
    assert geo.verification_status != "verified"
    assert geo.next_action == "fetch_via_adapter"
    assert geo.integrate_eligible is False
    assert result.fetched is False
    assert result.integrated is False
    dump = result.model_dump_json()
    assert "GSE25066" not in dump
    assert "已覆盖" not in dump
    assert "已找到" not in dump
    keys = {item.source_key for item in result.candidates}
    assert {"geo", "gdc", "cbioportal", "europe_pmc"} <= keys


def test_planned_sources_cannot_become_active() -> None:
    result = DiscoveryFacade().discover(
        DiscoverRequest(domain="astronomy", topic="超新星光变曲线", required_modalities=["light_curve"])
    )
    assert result.candidates
    assert all(item.registry_status in {"catalog_only", "planned"} for item in result.candidates)
    assert all(item.registry_status != "active" for item in result.candidates)
    assert all(item.verification_status in {"catalog_only", "planned"} for item in result.candidates)
    assert all(item.verification_status != "verified" for item in result.candidates)
    planned = [item for item in result.candidates if item.registry_status == "planned"]
    assert planned
    assert all(item.next_action == "reject" for item in planned)
    assert all(item.integrate_eligible is False for item in result.candidates)


def test_catalog_only_does_not_claim_field_coverage() -> None:
    result = DiscoveryFacade().discover(
        DiscoverRequest(
            domain="materials",
            topic="钙钛矿结构数据",
            required_modalities=["structure"],
            field_gaps=["band_gap"],
        )
    )
    assert result.candidates
    for item in result.candidates:
        assert item.verification_status in {"catalog_only", "planned"}
        assert all(hyp.coverage_claimed is False for hyp in item.field_hypotheses)
        assert all(hyp.coverage_status == "unknown" for hyp in item.field_hypotheses)
        assert all("已覆盖" not in hyp.hypothesis for hyp in item.field_hypotheses)
        assert item.integrate_eligible is False
    dump = result.model_dump_json()
    assert "已覆盖" not in dump
    assert "CanonicalRecord" not in dump


def test_discovery_does_not_import_adapters_or_broker() -> None:
    hits: list[str] = []
    for path in DISCOVERY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == item or alias.name.startswith(item + ".") for item in FORBIDDEN_MODULES):
                        hits.append(f"{path.name}:import {alias.name}")
                    if alias.name.split(".")[-1] in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == item or node.module.startswith(item + ".") for item in FORBIDDEN_MODULES):
                    hits.append(f"{path.name}:from {node.module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_NAMES:
                        hits.append(f"{path.name}:from {node.module} import {alias.name}")
    assert hits == []


def test_discover_api_is_candidate_only() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v30/discover",
        json={
            "domain": "oncology",
            "topic": "HER2阳性乳腺癌",
            "required_modalities": ["expression"],
            "field_gaps": ["gene_expression"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["fetched"] is False
    assert payload["integrated"] is False
    assert any(item["source_key"] == "geo" for item in payload["candidates"])
    assert all(item["verification_status"] in {"unverified", "catalog_only", "verified"} for item in payload["candidates"])
    assert all(item["verification_status"] != "verified" for item in payload["candidates"])
    select = client.post("/api/v30/discover/set-1/select", json={"candidate_ids": ["x"]})
    assert select.status_code in {404, 405}
