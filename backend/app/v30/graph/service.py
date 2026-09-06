from __future__ import annotations

from uuid import uuid4
import re

from backend.app.v30.graph.store import GraphNotFoundError, InMemoryGraphStore
from backend.app.v30.models import (
    DiscoveryCandidate,
    EvidenceGraph,
    FieldMapping,
    FieldMappingResult,
    FigureUnderstandingResult,
    GraphEdge,
    GraphNode,
    GraphProjectRequest,
    GraphWhyResponse,
    RankedSourceCandidate,
    ResearchGoal,
    SchemaPack,
    SelectedSourcePlan,
    SelectionContract,
)

ALLOWED_NODE_TYPES = frozenset(
    {
        "UserGoal",
        "ResearchContract",
        "SourceCandidate",
        "SelectedSource",
        "SchemaPack",
        "FieldMapping",
        "QualityFinding",
        "FigureUnderstanding",
        "Paper",
        "File",
    }
)
ALLOWED_EDGE_TYPES = frozenset(
    {"FORMULATES", "DISCOVERED", "SELECTED", "MAPPED_TO", "FLAGGED_BY", "EXTRACTED_FROM"}
)
FORBIDDEN_EDGE_TYPES = frozenset({"SAME_PATIENT", "JOINED_ACROSS_STUDY"})
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "canonical_value",
        "raw_value",
        "evidence_cell",
        "evidence_cells",
        "patient_record",
        "patient_records",
        "pcr",
        "pcr_status",
        "auc",
        "ic50",
        "same_patient",
        "joined_across_study",
    }
)
GRAPH_NOTICE = "投影层只记录来源选择、字段映射与质量标记原因，不替代 EvidenceBuilder，不含患者关系或事实值。"


class ForbiddenGraphEdgeError(ValueError):
    pass


class GraphService:
    """Project v30 artifacts into a queryable reason graph. Does not build facts or patient joins."""

    def __init__(self, store: InMemoryGraphStore | None = None) -> None:
        self.store = store or InMemoryGraphStore()

    def project(self, request: GraphProjectRequest, *, graph_id: str | None = None) -> EvidenceGraph:
        builder = _GraphBuilder(graph_id or f"graph-{uuid4().hex[:12]}")
        if request.goal is not None:
            builder.add_goal(request.goal)
        if request.contract is not None:
            builder.add_contract(request.contract)
        candidates = list(request.candidates)
        if request.selection is not None:
            seen = {item.candidate_id for item in candidates}
            for ranked in [*request.selection.selected_candidates, *request.selection.rejected_candidates]:
                if ranked.candidate_id not in seen:
                    candidates.append(ranked.candidate)
                    seen.add(ranked.candidate_id)
        for candidate in candidates:
            builder.add_candidate(candidate)
        if request.selection is not None:
            builder.add_selection(request.selection)
        if request.schema_pack is not None:
            builder.add_schema_pack(request.schema_pack)
        if request.mappings is not None:
            builder.add_mappings(request.mappings)
        for constraint in request.constraints:
            builder.note_constraint(constraint)
        return self.store.put(builder.build())

    def record_figure(
        self,
        result: FigureUnderstandingResult,
        *,
        graph_id: str | None = None,
    ) -> EvidenceGraph:
        if graph_id:
            try:
                builder = _GraphBuilder.from_graph(self.store.get(graph_id))
            except GraphNotFoundError:
                builder = _GraphBuilder(graph_id)
        else:
            builder = _GraphBuilder(f"graph-{uuid4().hex[:12]}")
        builder.add_figure_understanding(result)
        return self.store.put(builder.build())

    def get(self, graph_id: str) -> EvidenceGraph:
        return self.store.get(graph_id)

    def why(self, graph_id: str, finding_id: str) -> GraphWhyResponse:
        graph = self.store.get(graph_id)
        by_id = {node.node_id: node for node in graph.nodes}
        finding = by_id.get(finding_id)
        if finding is None or finding.node_type != "QualityFinding":
            raise GraphNotFoundError(f"{graph_id}/{finding_id}")
        inbound = [edge for edge in graph.edges if edge.to_id == finding_id]
        path_ids: list[str] = []
        why: list[str] = []
        seen: set[str] = set()
        stack = [finding_id]
        while stack:
            current_id = stack.pop()
            if current_id in seen:
                continue
            seen.add(current_id)
            path_ids.append(current_id)
            current = by_id.get(current_id)
            if current is not None:
                why.extend(current.reasons)
            for edge in graph.edges:
                if edge.to_id != current_id or edge.from_id in seen:
                    continue
                if edge.reason:
                    why.append(edge.reason)
                stack.append(edge.from_id)
        path = [by_id[node_id] for node_id in reversed(path_ids) if node_id in by_id]
        forbidden = any(edge.edge_type in FORBIDDEN_EDGE_TYPES for edge in graph.edges)
        return GraphWhyResponse(
            graph_id=graph_id,
            finding_id=finding_id,
            statement=finding.label,
            why=why,
            path=path,
            edges=inbound,
            forbidden_edges_present=forbidden,
        )

    def add_edge(
        self,
        graph_id: str,
        *,
        edge_type: str,
        from_id: str,
        to_id: str,
        reason: str = "",
    ) -> EvidenceGraph:
        graph = self.store.get(graph_id)
        builder = _GraphBuilder.from_graph(graph)
        builder.add_edge(edge_type, from_id, to_id, reason)
        return self.store.put(builder.build())


class _GraphBuilder:
    def __init__(self, graph_id: str) -> None:
        self.graph_id = graph_id
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.goal_id: str | None = None
        self.contract_id: str | None = None
        self.pack_id: str | None = None
        self.candidate_ids: dict[str, str] = {}
        self.selected_ids: list[str] = []
        self.constraint_notes: list[str] = []

    @classmethod
    def from_graph(cls, graph: EvidenceGraph) -> _GraphBuilder:
        builder = cls(graph.graph_id)
        builder.nodes = {node.node_id: node.model_copy(deep=True) for node in graph.nodes}
        builder.edges = [edge.model_copy(deep=True) for edge in graph.edges]
        return builder

    def add_goal(self, goal: ResearchGoal) -> None:
        node_id = "node-goal"
        self.goal_id = node_id
        label = goal.raw_text or goal.object or "user goal"
        self._add_node(
            node_id,
            "UserGoal",
            label,
            refs={"object": goal.object, "target": goal.target, "domain": goal.domain},
            reasons=["用户目标来自 Copilot/Memory 投影，不是已取数证明。"],
        )

    def add_contract(self, contract: SelectionContract) -> None:
        node_id = f"node-contract-{contract.contract_id or 'draft'}"
        self.contract_id = node_id
        self._add_node(
            node_id,
            "ResearchContract",
            contract.research_goal or contract.contract_id or "research contract",
            refs={
                "contract_id": contract.contract_id,
                "domain": contract.domain,
                "response_domain": contract.response_domain,
                "required_fields": list(contract.required_fields),
            },
            reasons=["契约字段是规划目标，不是已映射事实值。"],
        )
        if self.goal_id:
            self.add_edge("FORMULATES", self.goal_id, node_id, "用户目标被规范化为研究契约。")

    def add_candidate(self, candidate: DiscoveryCandidate) -> None:
        node_id = f"node-candidate-{candidate.candidate_id}"
        self.candidate_ids[candidate.candidate_id] = node_id
        self._add_node(
            node_id,
            "SourceCandidate",
            candidate.source_key,
            refs={
                "candidate_id": candidate.candidate_id,
                "source_key": candidate.source_key,
                "source_id": candidate.source_id,
                "verification_status": candidate.verification_status,
                "registry_status": candidate.registry_status,
                "locator_type": candidate.locator.locator_type,
                "locator_value": candidate.locator.value,
            },
            reasons=["Discovery 只产生候选，不表示已取数。"],
        )
        if self.contract_id:
            self.add_edge("DISCOVERED", self.contract_id, node_id, f"契约发现来源候选 {candidate.source_key}。")

    def add_selection(self, selection: SelectedSourcePlan) -> None:
        plan_reasons = list(selection.selection_reason)
        for ranked in selection.selected_candidates:
            node_id = f"node-selected-{ranked.candidate_id}"
            self.selected_ids.append(node_id)
            self._add_node(
                node_id,
                "SelectedSource",
                ranked.source_key,
                refs={
                    "candidate_id": ranked.candidate_id,
                    "source_key": ranked.source_key,
                    "reason_code": ranked.reason_code,
                    "verification_status": ranked.verification_status,
                    "fetched": selection.fetched,
                    "integrated": selection.integrated,
                },
                reasons=[ranked.reason, *plan_reasons],
            )
            from_id = self.candidate_ids.get(ranked.candidate_id)
            if from_id:
                self.add_edge("SELECTED", from_id, node_id, ranked.reason)
        for ranked in selection.rejected_candidates:
            self._flag_rejection(ranked)
        for note in selection.join_risk:
            finding_id = "finding-join-risk"
            if finding_id not in self.nodes:
                self._add_node(
                    finding_id,
                    "QualityFinding",
                    "禁止患者跨研究 Join",
                    refs={"kind": "join_risk"},
                    reasons=[note, "图投影不会创建 SAME_PATIENT 或 JOINED_ACROSS_STUDY 边。"],
                )
            if self.contract_id:
                self.add_edge("FLAGGED_BY", self.contract_id, finding_id, note)

    def add_schema_pack(self, pack: SchemaPack) -> None:
        node_id = f"node-pack-{pack.schema_pack_id}"
        self.pack_id = node_id
        self._add_node(
            node_id,
            "SchemaPack",
            pack.schema_pack_id,
            refs={
                "schema_pack_id": pack.schema_pack_id,
                "domain": pack.domain,
                "binding": pack.binding,
                "status": pack.status,
                "selected_sources": list(pack.selected_sources),
                "row_count": pack.row_count,
                "generates_data": pack.generates_data,
            },
            reasons=["Schema Pack 只提供目标字段清单，不生成数据行。"],
        )
        if self.contract_id:
            self.add_edge("DISCOVERED", self.contract_id, node_id, "契约绑定到 Schema Pack。")

    def add_mappings(self, result: FieldMappingResult) -> None:
        pack_id = self.pack_id or f"node-pack-{result.schema_pack_id}"
        if pack_id not in self.nodes:
            self._add_node(
                pack_id,
                "SchemaPack",
                result.schema_pack_id,
                refs={"schema_pack_id": result.schema_pack_id, "domain": result.domain},
                reasons=["映射结果引用 Schema Pack，不含事实值。"],
            )
            self.pack_id = pack_id
        for mapping in result.mappings:
            self._add_mapping(pack_id, mapping)

    def note_constraint(self, constraint: str) -> None:
        text = constraint.strip()
        if not text:
            return
        self.constraint_notes.append(text)
        finding_id = f"finding-constraint-{len(self.constraint_notes)}"
        self._add_node(
            finding_id,
            "QualityFinding",
            f"用户约束：{text}",
            refs={"kind": "user_constraint", "constraint": text},
            reasons=[f"排除或限制来自用户约束，不是数据缺失证明：{text}"],
        )
        if self.goal_id:
            self.add_edge("FLAGGED_BY", self.goal_id, finding_id, "用户约束进入图，不作为已验证来源。")

    def add_figure_understanding(self, result: FigureUnderstandingResult) -> None:
        source_kind = "Paper" if _looks_like_paper(result.source_id) else "File"
        source_node_id = f"node-source-{_slug(result.source_id)}"
        figure_node_id = f"node-figure-{_slug(result.figure_id or result.source_id)}"
        self._add_node(
            source_node_id,
            source_kind,
            result.source_id,
            refs={"source_id": result.source_id, "kind": source_kind.lower()},
            reasons=["论文/文件来源锚点，不含观测值。"],
        )
        self._add_node(
            figure_node_id,
            "FigureUnderstanding",
            result.figure_id or "figure",
            refs={
                "figure_id": result.figure_id,
                "figure_type": result.figure_type,
                "x_axis": result.x_axis,
                "y_axis": result.y_axis,
                "extractability": result.extractability,
                "digitization_possible": result.digitization_possible,
                "status": result.status,
                "enters_primary_table": False,
            },
            reasons=[
                "只记录图理解结果，不记录观测数据。",
                "enters_primary_table=false，不写 CanonicalRecord。",
            ],
        )
        self.add_edge(
            "EXTRACTED_FROM",
            figure_node_id,
            source_node_id,
            "图理解来自该论文/文件，不是数字化入库。",
        )

    def add_edge(self, edge_type: str, from_id: str, to_id: str, reason: str = "") -> None:
        normalized = edge_type.strip().upper()
        if normalized in FORBIDDEN_EDGE_TYPES:
            raise ForbiddenGraphEdgeError(f"forbidden evidence-graph edge: {normalized}")
        if normalized not in ALLOWED_EDGE_TYPES:
            raise ForbiddenGraphEdgeError(f"unsupported evidence-graph edge: {normalized}")
        edge_id = f"edge-{len(self.edges) + 1}-{normalized.lower()}"
        self.edges.append(
            GraphEdge(
                edge_id=edge_id,
                edge_type=normalized,
                from_id=from_id,
                to_id=to_id,
                reason=reason,
            )
        )

    def build(self) -> EvidenceGraph:
        if any(edge.edge_type in FORBIDDEN_EDGE_TYPES for edge in self.edges):
            raise ForbiddenGraphEdgeError("graph contains forbidden patient-join edges")
        return EvidenceGraph(
            graph_id=self.graph_id,
            nodes=list(self.nodes.values()),
            edges=list(self.edges),
            notice=GRAPH_NOTICE,
            replaces_evidence_builder=False,
            contains_patient_edges=False,
            copies_fact_values=False,
        )

    def _add_mapping(self, pack_id: str, mapping: FieldMapping) -> None:
        node_id = f"node-mapping-{mapping.source_field}-{mapping.target_field}"
        reasons = [
            f"{mapping.source_field} → {mapping.target_field}，status={mapping.status}，confidence={mapping.confidence}。",
            "节点只保存映射关系，不复制字段值。",
        ]
        self._add_node(
            node_id,
            "FieldMapping",
            f"{mapping.source_field}→{mapping.target_field}",
            refs={
                "source_field": mapping.source_field,
                "target_field": mapping.target_field,
                "confidence": mapping.confidence,
                "status": mapping.status,
                "risk_level": mapping.risk_level,
            },
            reasons=reasons,
        )
        self.add_edge("MAPPED_TO", pack_id, node_id, reasons[0])
        for selected_id in self.selected_ids:
            self.add_edge("MAPPED_TO", selected_id, node_id, "所选来源的字段按该映射进入目标清单。")
        if mapping.status.upper() == "REVIEW":
            finding_id = f"finding-review-{mapping.source_field}-{mapping.target_field}"
            self._add_node(
                finding_id,
                "QualityFinding",
                f"{mapping.target_field} 映射状态为 REVIEW",
                refs={
                    "kind": "mapping_review",
                    "source_field": mapping.source_field,
                    "target_field": mapping.target_field,
                    "status": mapping.status,
                    "risk_level": mapping.risk_level,
                    "confidence": mapping.confidence,
                },
                reasons=[
                    f"Matcher 将 {mapping.source_field} → {mapping.target_field} 标为 REVIEW。",
                    f"confidence={mapping.confidence}，risk_level={mapping.risk_level}。",
                    "投影层不改 Quality Gate，也不自动采用该映射值。",
                ],
            )
            self.add_edge("FLAGGED_BY", node_id, finding_id, "字段映射进入 REVIEW。")

    def _flag_rejection(self, ranked: RankedSourceCandidate) -> None:
        candidate_id = self.candidate_ids.get(ranked.candidate_id)
        if candidate_id is None:
            return
        finding_id = f"finding-rejected-{ranked.candidate_id}"
        kind = "user_constraint" if ranked.reason_code == "user_constraint" else ranked.reason_code
        self._add_node(
            finding_id,
            "QualityFinding",
            f"未选择 {ranked.source_key}",
            refs={"kind": kind, "source_key": ranked.source_key, "reason_code": ranked.reason_code},
            reasons=[ranked.reason, f"reason_code={ranked.reason_code}"],
        )
        self.add_edge("FLAGGED_BY", candidate_id, finding_id, ranked.reason)

    def _add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        *,
        refs: dict,
        reasons: list[str],
    ) -> None:
        if node_type not in ALLOWED_NODE_TYPES:
            raise ValueError(f"unsupported evidence-graph node: {node_type}")
        _assert_no_fact_payload(refs)
        self.nodes[node_id] = GraphNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            refs=refs,
            reasons=[item for item in reasons if item],
        )


def _assert_no_fact_payload(refs: dict) -> None:
    lowered = {str(key).lower() for key in refs}
    leaked = lowered & FORBIDDEN_PAYLOAD_KEYS
    if leaked:
        raise ValueError(f"evidence graph must not copy fact/patient payloads: {sorted(leaked)}")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-")[:80] or "item"


def _looks_like_paper(source_id: str) -> bool:
    text = (source_id or "").lower()
    return any(token in text for token in ("paper", "doi", "pmc", "pmid", "arxiv", "europe_pmc"))
