from __future__ import annotations

from backend.app.literature.models import LiteratureScan
from backend.app.rag.models import GraphEdge, GraphNode, PaperChunk, ScientificGraphSnapshot
from backend.app.research_planning.models import QuestionCandidate, ResearchContract, ResearchTopic


class ScientificGraphStore:
    """Scientific-data lineage graph; graph edges never imply patient identity."""

    def __init__(self, topic_id: str) -> None:
        self.topic_id = topic_id
        try:
            import networkx as nx

            self._graph = nx.DiGraph()
            self.backend = "networkx"
        except ImportError:
            self._graph = None
            self.backend = "builtin-adjacency"
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[tuple[str, str, str], GraphEdge] = {}

    def index_planning(
        self,
        topic: ResearchTopic,
        scan: LiteratureScan,
        candidates: list[QuestionCandidate],
        chunks: list[PaperChunk],
    ) -> None:
        topic_node = f"topic:{topic.topic_id}"
        self._add_node(GraphNode(node_id=topic_node, node_type="ResearchTopic", label=topic.topic))
        for paper in scan.papers:
            paper_node = f"paper:{paper.paper_id}"
            self._add_node(
                GraphNode(
                    node_id=paper_node,
                    node_type="Paper",
                    label=paper.title,
                    source_id=paper.source_id,
                    source_url=paper.source_url,
                )
            )
            self._add_edge(topic_node, paper_node, "HAS_EVIDENCE_CANDIDATE")
            for accession in paper.dataset_accessions:
                dataset_node = f"dataset:{accession}"
                self._add_node(
                    GraphNode(
                        node_id=dataset_node,
                        node_type="Dataset",
                        label=accession,
                        source_id=accession,
                    )
                )
                self._add_edge(paper_node, dataset_node, "USES_DATASET")
        for candidate in candidates:
            question_node = f"question:{candidate.candidate_id}"
            self._add_node(
                GraphNode(node_id=question_node, node_type="ResearchQuestion", label=candidate.question)
            )
            self._add_edge(topic_node, question_node, "FORMULATES")
            for evidence in candidate.literature_evidence:
                self._add_edge(f"paper:{evidence.paper_id}", question_node, "SUPPORTS")
        for chunk in chunks:
            chunk_node = f"chunk:{chunk.chunk_id}"
            self._add_node(
                GraphNode(
                    node_id=chunk_node,
                    node_type="PaperChunk",
                    label=f"{chunk.section} #{chunk.chunk_index + 1}",
                    source_id=chunk.source_id,
                    source_url=chunk.source_url,
                )
            )
            self._add_edge(chunk_node, f"paper:{chunk.paper_id}", "EXTRACTED_FROM")

    def index_contract(self, contract: ResearchContract) -> None:
        contract_node = f"contract:{contract.contract_id}"
        question_node = f"question:{contract.candidate_id}"
        self._add_node(
            GraphNode(node_id=contract_node, node_type="ResearchContract", label=contract.research_question)
        )
        self._add_edge(question_node, contract_node, "SELECTED_AS")
        for requirement in [
            *contract.required_fields,
            *contract.recommended_fields,
            *contract.optional_fields,
        ]:
            field_node = f"field:{requirement.field_id}"
            self._add_node(
                GraphNode(node_id=field_node, node_type="Variable", label=requirement.label)
            )
            self._add_edge(contract_node, field_node, f"REQUIRES_{requirement.priority.value.upper()}")
            for evidence in requirement.literature_evidence:
                self._add_edge(f"paper:{evidence.paper_id}", field_node, "DEFINES")

    def related_paper_ids(self, field_id: str | None) -> set[str]:
        if not field_id:
            return set()
        target = f"field:{field_id}"
        return {
            edge.source.removeprefix("paper:")
            for edge in self._edges.values()
            if edge.target == target and edge.relation == "DEFINES" and edge.source.startswith("paper:")
        }

    def snapshot(self) -> ScientificGraphSnapshot:
        return ScientificGraphSnapshot(
            topic_id=self.topic_id,
            backend=self.backend,
            nodes=sorted(self._nodes.values(), key=lambda item: item.node_id),
            edges=sorted(
                self._edges.values(),
                key=lambda item: (item.source, item.target, item.relation),
            ),
        )

    def _add_node(self, node: GraphNode) -> None:
        self._nodes[node.node_id] = node
        if self._graph is not None:
            self._graph.add_node(node.node_id, **node.model_dump(mode="json"))

    def _add_edge(self, source: str, target: str, relation: str) -> None:
        edge = GraphEdge(source=source, target=target, relation=relation)
        self._edges[(source, target, relation)] = edge
        if self._graph is not None:
            self._graph.add_edge(source, target, relation=relation)
