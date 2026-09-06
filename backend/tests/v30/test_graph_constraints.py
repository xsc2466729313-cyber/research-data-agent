from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v30.graph.service import (
    FORBIDDEN_EDGE_TYPES,
    FORBIDDEN_PAYLOAD_KEYS,
    ForbiddenGraphEdgeError,
    GraphService,
)
from backend.app.v30.models import (
    DiscoveryCandidate,
    DiscoveryLocator,
    FieldHypothesis,
    FieldMapping,
    FieldMappingResult,
    GraphProjectRequest,
    RankedSourceCandidate,
    ResearchGoal,
    SchemaPack,
    SelectedSourcePlan,
    SelectionContract,
)

ROOT = Path(__file__).resolve().parents[3]
GRAPH_ROOT = Path(__file__).resolve().parents[2] / "app" / "v30" / "graph"
FROZEN_FILES = (
    ROOT / "configs" / "canonical_schema.yaml",
    ROOT / "configs" / "medical_rules.yaml",
    ROOT / "backend" / "app" / "evidence" / "evidence_builder.py",
    ROOT / "backend" / "app" / "integration" / "schema_matcher_v3.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _geo_candidate() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id="disc-oncology-geo",
        source_key="geo",
        resource_kind="official_api",
        locator=DiscoveryLocator(locator_type="geo_query", value="HER2 breast cancer", note="catalog"),
        source_id="registry:geo",
        discovered_from="source_registry",
        field_hypotheses=[
            FieldHypothesis(field="gene_expression", hypothesis="GEO 可能提供表达矩阵", coverage_claimed=False)
        ],
        verification_status="unverified",
        next_action="fetch_via_adapter",
        registry_status="active",
        integrate_eligible=True,
    )


def _metabric_candidate() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id="disc-oncology-metabric",
        source_key="metabric",
        resource_kind="official_api",
        locator=DiscoveryLocator(locator_type="study_id", value="brca_metabric", note="user mentioned"),
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


def _project_request() -> GraphProjectRequest:
    geo = _geo_candidate()
    metabric = _metabric_candidate()
    return GraphProjectRequest(
        goal=ResearchGoal(
            object="HER2阳性乳腺癌",
            target="疗效预测",
            domain="oncology",
            raw_text="HER2阳性乳腺癌耐药疗效预测，排除 METABRIC",
        ),
        contract=SelectionContract(
            research_goal="HER2阳性乳腺癌耐药疗效预测",
            required_fields=["her2_status", "gene_expression"],
            domain="oncology",
            contract_id="contract-her2-demo",
            response_domain="clinical",
        ),
        candidates=[geo, metabric],
        selection=SelectedSourcePlan(
            selected_candidates=[
                RankedSourceCandidate(
                    candidate_id=geo.candidate_id,
                    source_key="geo",
                    verification_status="unverified",
                    registry_status="active",
                    reason="GEO 覆盖 gene_expression 假说，由 SourceBroker selector 排序选中。",
                    reason_code="matched_coverage",
                    hypothesized_fields=["gene_expression"],
                    candidate=geo,
                )
            ],
            rejected_candidates=[
                RankedSourceCandidate(
                    candidate_id=metabric.candidate_id,
                    source_key="metabric",
                    verification_status="unverified",
                    registry_status="active",
                    reason="用户约束排除 METABRIC",
                    reason_code="user_constraint",
                    hypothesized_fields=["gene_expression"],
                    candidate=metabric,
                )
            ],
            selection_reason=["选择结果由现有 SourceBroker matcher/selector 计算，v30 不复制集合覆盖算法。"],
            join_risk=["不自动做患者级 Join。独立来源必须分开分析。"],
            fetched=False,
            integrated=False,
        ),
        schema_pack=SchemaPack(
            schema_pack_id="oncology_canonical_v0.1",
            domain="oncology",
            entity_type="patient_sample",
            binding="frozen_canonical",
            status="bound",
            selected_sources=["geo"],
            row_count=0,
            generates_data=False,
        ),
        mappings=FieldMappingResult(
            schema_pack_id="oncology_canonical_v0.1",
            domain="oncology",
            mappings=[
                FieldMapping(
                    source_field="her2",
                    target_field="her2_status",
                    confidence=0.62,
                    status="REVIEW",
                    risk_level="high",
                )
            ],
            matcher_version="schema_matcher_v3",
            row_count=0,
            generates_data=False,
        ),
        constraints=["排除 METABRIC"],
    )


def _by_type(graph, node_type: str):
    return [node for node in graph.nodes if node.node_type == node_type]


def _by_id(graph):
    return {node.node_id: node for node in graph.nodes}


def _ancestors(graph, node_id: str) -> set[str]:
    incoming = [edge for edge in graph.edges if edge.to_id == node_id]
    seen = {node_id}
    stack = [edge.from_id for edge in incoming]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edge.from_id for edge in graph.edges if edge.to_id == current)
    return seen


def test_field_source_chain_is_queryable() -> None:
    graph = GraphService().project(_project_request())
    mapping = next(node for node in _by_type(graph, "FieldMapping") if node.refs["target_field"] == "her2_status")
    ancestor_ids = _ancestors(graph, mapping.node_id)
    types = {node.node_type for node in graph.nodes if node.node_id in ancestor_ids}
    assert "UserGoal" in types
    assert "ResearchContract" in types
    assert "SourceCandidate" in types
    assert "SelectedSource" in types
    assert "SchemaPack" in types
    geo = next(node for node in _by_type(graph, "SelectedSource") if node.refs["source_key"] == "geo")
    assert geo.node_id in ancestor_ids
    assert mapping.refs["source_field"] == "her2"
    assert "canonical_value" not in mapping.refs
    assert "raw_value" not in mapping.refs


def test_source_selection_reason_is_explained() -> None:
    graph = GraphService().project(_project_request())
    selected = next(node for node in _by_type(graph, "SelectedSource") if node.refs["source_key"] == "geo")
    assert any("GEO" in reason or "SourceBroker" in reason for reason in selected.reasons)
    selected_edge = next(
        edge for edge in graph.edges if edge.edge_type == "SELECTED" and edge.to_id == selected.node_id
    )
    assert "GEO" in selected_edge.reason or "gene_expression" in selected_edge.reason
    rejected = next(node for node in _by_type(graph, "QualityFinding") if node.refs.get("source_key") == "metabric")
    assert rejected.refs["reason_code"] == "user_constraint"
    assert any("METABRIC" in reason for reason in rejected.reasons)


def test_review_reason_is_explained_via_why() -> None:
    service = GraphService()
    graph = service.project(_project_request())
    finding = next(node for node in _by_type(graph, "QualityFinding") if node.refs.get("kind") == "mapping_review")
    explained = service.why(graph.graph_id, finding.node_id)
    assert "REVIEW" in explained.statement
    joined = " ".join(explained.why)
    assert "her2" in joined
    assert "her2_status" in joined
    assert "0.62" in joined
    assert "high" in joined
    assert explained.forbidden_edges_present is False
    path_types = {node.node_type for node in explained.path}
    assert "FieldMapping" in path_types
    assert "QualityFinding" in path_types


def test_patient_cross_study_edges_are_forbidden() -> None:
    service = GraphService()
    graph = service.project(_project_request())
    edge_types = {edge.edge_type for edge in graph.edges}
    assert edge_types <= {"FORMULATES", "DISCOVERED", "SELECTED", "MAPPED_TO", "FLAGGED_BY"}
    assert not (edge_types & FORBIDDEN_EDGE_TYPES)
    join_finding = next(node for node in _by_type(graph, "QualityFinding") if node.refs.get("kind") == "join_risk")
    assert any("患者" in reason or "Join" in reason for reason in join_finding.reasons)
    goal = _by_type(graph, "UserGoal")[0]
    contract = _by_type(graph, "ResearchContract")[0]
    with pytest.raises(ForbiddenGraphEdgeError, match="SAME_PATIENT"):
        service.add_edge(graph.graph_id, edge_type="SAME_PATIENT", from_id=goal.node_id, to_id=contract.node_id)
    with pytest.raises(ForbiddenGraphEdgeError, match="JOINED_ACROSS_STUDY"):
        service.add_edge(
            graph.graph_id,
            edge_type="JOINED_ACROSS_STUDY",
            from_id=goal.node_id,
            to_id=contract.node_id,
        )
    unchanged = service.get(graph.graph_id)
    assert all(edge.edge_type not in FORBIDDEN_EDGE_TYPES for edge in unchanged.edges)


def test_graph_does_not_copy_patient_or_fact_values() -> None:
    graph = GraphService().project(_project_request())
    for node in graph.nodes:
        leaked = {str(key).lower() for key in node.refs} & FORBIDDEN_PAYLOAD_KEYS
        assert leaked == set()
    assert graph.replaces_evidence_builder is False
    assert graph.contains_patient_edges is False
    assert graph.copies_fact_values is False
    assert "EvidenceBuilder" in graph.notice or "不替代" in graph.notice


def test_graph_api_get_and_why() -> None:
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v30/graphs/{graph_id}" in paths
    assert "/api/v30/graphs/{graph_id}/why/{finding_id}" in paths
    created = client.post("/api/v30/graphs/project", json=_project_request().model_dump())
    assert created.status_code == 200
    graph_id = created.json()["graph_id"]
    fetched = client.get(f"/api/v30/graphs/{graph_id}")
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["replaces_evidence_builder"] is False
    mapping = next(node for node in payload["nodes"] if node["node_type"] == "FieldMapping")
    assert mapping["refs"]["target_field"] == "her2_status"
    finding = next(node for node in payload["nodes"] if node["refs"].get("kind") == "mapping_review")
    why = client.get(f"/api/v30/graphs/{graph_id}/why/{finding['node_id']}")
    assert why.status_code == 200
    body = why.json()
    assert "REVIEW" in body["statement"]
    assert body["forbidden_edges_present"] is False
    missing = client.get("/api/v30/graphs/graph-missing")
    assert missing.status_code == 404


def test_graph_module_does_not_touch_frozen_kernels() -> None:
    before = {path.name: _digest(path) for path in FROZEN_FILES}
    GraphService().project(_project_request())
    hits: list[str] = []
    forbidden_modules = (
        "backend.app.evidence",
        "backend.app.quality",
        "backend.app.quality_v2",
        "backend.app.sources",
        "backend.app.integration.schema_matcher_v3",
        "backend.app.agent.service",
    )
    for path in GRAPH_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == name or node.module.startswith(name + ".") for name in forbidden_modules):
                    hits.append(f"{path.name}:from {node.module}")
    assert hits == []
    assert {path.name: _digest(path) for path in FROZEN_FILES} == before
