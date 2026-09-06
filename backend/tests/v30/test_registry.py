from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.registry.service import KNOWN_FETCH_BINDINGS, SourceRegistryService

ONCOLOGY_KEYS = {"gdc", "geo", "cbioportal", "aact", "civic", "europe_pmc"}
EXPECTED_BINDINGS = {
    "gdc": "search_gdc",
    "geo": "search_geo",
    "cbioportal": "search_cbioportal",
    "aact": "search_trials",
    "civic": "search_civic",
    "europe_pmc": "search_europe_pmc",
}
REGISTRY_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "registry"
SOURCES_ROOT = Path(__file__).resolve().parents[2] / "app" / "sources"


def test_oncology_sources_are_queryable() -> None:
    registry = SourceRegistryService()
    payload = registry.list_sources(domain="oncology")
    keys = {item.source_key for item in payload.sources}
    assert ONCOLOGY_KEYS <= keys
    by_key = {item.source_key: item for item in payload.sources}
    for key, binding in EXPECTED_BINDINGS.items():
        assert by_key[key].fetch_binding == binding
        assert by_key[key].status == "active"
        assert by_key[key].integrate_eligible is True
        assert binding in KNOWN_FETCH_BINDINGS


def test_planned_and_catalog_sources_cannot_integrate() -> None:
    registry = SourceRegistryService()
    blocked = [
        item
        for item in registry.list_sources().sources
        if item.status in {"planned", "catalog_only"}
    ]
    assert blocked
    assert all(item.integrate_eligible is False for item in blocked)
    assert all(not item.fetch_binding for item in blocked)
    assert registry.integrate_eligible_keys() == ONCOLOGY_KEYS
    astro = registry.list_sources(domain="astronomy").sources
    materials = registry.list_sources(domain="materials").sources
    assert astro and materials
    assert all(item.status in {"catalog_only", "planned"} for item in astro + materials)
    assert all(item.integrate_eligible is False for item in astro + materials)


def test_registry_api_filters_and_does_not_discover() -> None:
    client = TestClient(app)
    oncology = client.get("/api/v30/registry/sources", params={"domain": "oncology"})
    assert oncology.status_code == 200
    keys = {item["source_key"] for item in oncology.json()["sources"]}
    assert ONCOLOGY_KEYS <= keys
    eligible = client.get("/api/v30/registry/sources", params={"integrate_eligible": True})
    assert {item["source_key"] for item in eligible.json()["sources"]} == ONCOLOGY_KEYS
    planned = client.get("/api/v30/registry/sources", params={"status": "planned"})
    assert planned.status_code == 200
    assert planned.json()["sources"]
    assert all(item["integrate_eligible"] is False for item in planned.json()["sources"])
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v30/registry/sources" in paths
    assert "/api/v30/discover" in paths
    assert "/api/v30/discover/{set_id}/select" not in paths


def test_registry_does_not_import_or_change_adapters() -> None:
    forbidden_modules = (
        "backend.app.sources",
        "backend.app.agent.service",
        "backend.app.quality",
        "backend.app.quality_v2",
    )
    forbidden_names = {"ResearchAgentService", "GDCAdapter", "GEOAdapter", "SchemaMatcher"}
    hits: list[str] = []
    for path in REGISTRY_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == item or alias.name.startswith(item + ".") for item in forbidden_modules):
                        hits.append(f"{path.name}:import {alias.name}")
                    if alias.name.split(".")[-1] in forbidden_names:
                        hits.append(f"{path.name}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == item or node.module.startswith(item + ".") for item in forbidden_modules):
                    hits.append(f"{path.name}:from {node.module}")
                for alias in node.names:
                    if alias.name in forbidden_names:
                        hits.append(f"{path.name}:from {node.module} import {alias.name}")
    assert hits == []
    assert SOURCES_ROOT.is_dir()
