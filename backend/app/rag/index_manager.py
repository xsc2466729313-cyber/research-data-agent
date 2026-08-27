from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.app.literature.models import LiteratureScan
from backend.app.rag.chunker import PaperChunker
from backend.app.rag.embedding import EmbeddingBackend, create_embedding_backend
from backend.app.rag.evaluator import RAGEvaluator
from backend.app.rag.graph_store import ScientificGraphStore
from backend.app.rag.hybrid_retriever import HybridRetriever
from backend.app.rag.models import (
    EvidenceQueryRequest,
    EvidenceQueryResponse,
    RAGEvaluationRequest,
    RAGEvaluationResult,
    RAGIndexReport,
    ScientificGraphSnapshot,
)
from backend.app.rag.vector_store import VectorStore, create_vector_store
from backend.app.research_planning.models import QuestionCandidate, ResearchContract, ResearchTopic


class RAGIndexNotFoundError(LookupError):
    pass


@dataclass
class _TopicIndex:
    topic_id: str
    store: VectorStore
    embedding: EmbeddingBackend
    graph: ScientificGraphStore
    retriever: HybridRetriever
    warnings: list[str] = field(default_factory=list)
    indexed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    paper_count: int = 0


class PlanningRAGIndexManager:
    def __init__(self, *, chunker: PaperChunker | None = None) -> None:
        self.chunker = chunker or PaperChunker()
        self._indexes: dict[str, _TopicIndex] = {}
        self._evaluator = RAGEvaluator()

    def index_topic(
        self,
        topic: ResearchTopic,
        scan: LiteratureScan,
        candidates: list[QuestionCandidate],
    ) -> RAGIndexReport:
        index = self._indexes.get(topic.topic_id)
        if index is None:
            embedding, embedding_warnings = create_embedding_backend()
            store, store_warnings = create_vector_store(topic.topic_id)
            graph = ScientificGraphStore(topic.topic_id)
            index = _TopicIndex(
                topic_id=topic.topic_id,
                store=store,
                embedding=embedding,
                graph=graph,
                retriever=HybridRetriever(store=store, embedding=embedding, graph=graph),
                warnings=[*embedding_warnings, *store_warnings],
            )
            self._indexes[topic.topic_id] = index
        else:
            index.store.clear()
            index.graph = ScientificGraphStore(topic.topic_id)
            index.retriever = HybridRetriever(
                store=index.store,
                embedding=index.embedding,
                graph=index.graph,
            )
        chunks = self.chunker.chunk(topic.topic_id, scan.papers)
        if chunks:
            embeddings = index.embedding.embed_documents([chunk.text for chunk in chunks])
            index.store.upsert(chunks, embeddings)
        index.graph.index_planning(topic, scan, candidates, chunks)
        index.paper_count = len(scan.papers)
        index.indexed_at = datetime.now(timezone.utc)
        return self.report(topic.topic_id)

    def index_contract(self, contract: ResearchContract) -> RAGIndexReport:
        index = self._index(contract.topic_id)
        index.graph.index_contract(contract)
        index.indexed_at = datetime.now(timezone.utc)
        return self.report(contract.topic_id)

    def query(self, topic_id: str, request: EvidenceQueryRequest) -> EvidenceQueryResponse:
        index = self._index(topic_id)
        hits = index.retriever.retrieve(request)
        return EvidenceQueryResponse(
            topic_id=topic_id,
            query=request.query,
            field_id=request.field_id,
            retrieval_mode=f"hybrid:{index.store.name}+{index.embedding.name}+{index.graph.backend}",
            hits=hits,
            evidence_found=bool(hits),
            notice=(
                "结果为可点击的证据片段，不是患者级事实；Methods/Data Availability/Supplementary "
                "优先级高于 Abstract/Title。"
            ),
        )

    def graph(self, topic_id: str) -> ScientificGraphSnapshot:
        return self._index(topic_id).graph.snapshot()

    def evaluate(self, topic_id: str, request: RAGEvaluationRequest) -> RAGEvaluationResult:
        index = self._index(topic_id)
        return self._evaluator.evaluate(
            topic_id=topic_id,
            request=request,
            retrieve=index.retriever.retrieve,
        )

    def report(self, topic_id: str) -> RAGIndexReport:
        index = self._index(topic_id)
        snapshot = index.graph.snapshot()
        return RAGIndexReport(
            topic_id=topic_id,
            chunk_count=len(index.store.chunks()),
            paper_count=index.paper_count,
            vector_backend=index.store.name,
            embedding_backend=index.embedding.name,
            graph_backend=index.graph.backend,
            graph_node_count=len(snapshot.nodes),
            graph_edge_count=len(snapshot.edges),
            indexed_at=index.indexed_at,
            warnings=index.warnings,
        )

    def _index(self, topic_id: str) -> _TopicIndex:
        index = self._indexes.get(topic_id)
        if index is None:
            raise RAGIndexNotFoundError("Planning RAG 尚未为该 Topic 建立索引。")
        return index
