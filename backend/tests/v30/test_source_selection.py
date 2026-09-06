from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agent.service import ResearchAgentService
from backend.app.main import app
from backend.app.source_broker.dataset_discovery import DatasetDiscovery
from backend.app.source_broker.service import SourceBroker
from backend.app.v30.discovery.service import DiscoveryFacade
from backend.app.v30.models import (
    DiscoverRequest,
    DiscoveryCandidate,
    DiscoveryLocator,
    FieldHypothesis,
    SelectionContract,
    SourceSelectionRequest,
)
from backend.app.v30.source_selection.service import SourceSelectionService

SELECTION_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "source_selection"


def _oncology_candidates() -> list[DiscoveryCandidate]:
    return DiscoveryFacade().discover(
        DiscoverRequest(
            domain="oncology",
            topic="HER2阳性乳腺癌耐药",
            required_modalities=["expression", "clinical_table"],
            field_gaps=["gene_expression", "treatment_response"],
        )
    ).candidates


def _metabric_candidate() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id="disc-oncology-metabric",
        source_key="metabric",
        resource_kind="official_api",
        locator=DiscoveryLocator(locator_type="study_id", value="brca_metabric", note="user mentioned METABRIC"),
        source_id="registry:metabric",
        discovered_from="user",
        field_hypotheses=[
            FieldHypothesis(field="gene_expression", hypothesis="假说", coverage_claimed=False)
        ],
        verification_status="unverified",
        next_action="fetch_via_adapter",
        registry_status="active",
        integrate_eligible=False,
    )


def test_discovery_candidates_can_be_ranked() -> None:
    result = SourceSelectionService().select(
        SourceSelectionRequest(
            candidates=_oncology_candidates(),
            contract=SelectionContract(
                research_goal="HER2阳性乳腺癌耐药疗效预测",
                required_fields=["gene_expression"],
                domain="oncology",
                response_domain="clinical",
            ),
            constraints={},
        )
    )
    assert result.selected_candidates
    assert result.fetched is False
    assert result.integrated is False
    selected_keys = [item.source_key for item in result.selected_candidates]
    assert "geo" in selected_keys or "gdc" in selected_keys
    geo = next((item for item in result.selected_candidates if item.source_key == "geo"), None)
    if geo is not None:
        assert "gene_expression" in geo.reason or "gene_expression" in geo.hypothesized_fields
    assert all(item.verification_status != "verified" for item in result.selected_candidates)
    assert result.response_domain == "clinical"


def test_user_exclusion_rejects_metabric() -> None:
    candidates = [*_oncology_candidates(), _metabric_candidate()]
    result = SourceSelectionService().select(
        SourceSelectionRequest(
            candidates=candidates,
            contract=SelectionContract(
                research_goal="HER2阳性乳腺癌",
                required_fields=["gene_expression"],
                domain="oncology",
            ),
            constraints={"exclude": ["METABRIC"]},
        )
    )
    rejected = next(item for item in result.rejected_candidates if item.source_key == "metabric")
    assert rejected.reason_code == "user_constraint"
    assert "METABRIC" in rejected.reason or "metabric" in rejected.reason.casefold()
    assert all(item.source_key != "metabric" for item in result.selected_candidates)


def test_catalog_only_cannot_become_verified() -> None:
    discovered = DiscoveryFacade().discover(
        DiscoverRequest(domain="astronomy", topic="超新星光变曲线", required_modalities=["light_curve"])
    )
    result = SourceSelectionService().select(
        SourceSelectionRequest(
            candidates=discovered.candidates,
            contract=SelectionContract(
                research_goal="超新星光变曲线",
                required_fields=["light_curve"],
                domain="astronomy",
                response_domain="none",
            ),
            constraints={},
        )
    )
    everyone = result.selected_candidates + result.rejected_candidates
    assert everyone
    assert all(item.verification_status in {"unverified", "catalog_only", "planned"} for item in everyone)
    assert all(item.verification_status != "verified" for item in everyone)
    assert all(item.registry_status != "active" for item in everyone)
    assert result.response_domain == "none"


def test_source_selection_does_not_call_adapter_or_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        ResearchAgentService,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call ResearchAgentService")),
    )
    monkeypatch.setattr(
        SourceBroker,
        "plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call SourceBroker.plan")),
    )
    monkeypatch.setattr(
        DatasetDiscovery,
        "discover",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not rediscover datasets")),
    )
    SourceSelectionService().select(
        SourceSelectionRequest(
            candidates=_oncology_candidates(),
            contract=SelectionContract(research_goal="乳腺癌", required_fields=["gene_expression"], domain="oncology"),
            constraints=["不要METABRIC"],
        )
    )
    hits: list[str] = []
    forbidden_modules = ("backend.app.sources", "backend.app.agent.service")
    forbidden_names = {"ResearchAgentService", "GDCAdapter", "GEOAdapter"}
    for path in SELECTION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == item or node.module.startswith(item + ".") for item in forbidden_modules):
                    hits.append(node.module)
                for alias in node.names:
                    if alias.name in forbidden_names:
                        hits.append(alias.name)
    assert hits == []


def test_legacy_apis_remain_and_selection_route_exists() -> None:
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/agent/tasks" in paths
    assert "/api/v3/research/clarify" in paths
    assert "/api/v30/source-selection" in paths
    response = client.post(
        "/api/v30/source-selection",
        json={
            "candidates": [item.model_dump(mode="json") for item in _oncology_candidates()],
            "contract": {
                "research_goal": "HER2阳性乳腺癌",
                "required_fields": ["gene_expression"],
                "domain": "oncology",
                "response_domain": "clinical",
            },
            "constraints": {"exclude": ["METABRIC"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["fetched"] is False
    assert payload["integrated"] is False
    assert payload["response_domain"] == "clinical"
    assert "join_risk" in payload
    assert client.get("/health").status_code == 200
