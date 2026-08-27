from __future__ import annotations

import re

from backend.app.rag.embedding import EmbeddingBackend
from backend.app.rag.graph_store import ScientificGraphStore
from backend.app.rag.models import EvidenceQueryRequest, RetrievalHit
from backend.app.rag.text_features import retrieval_tokens
from backend.app.rag.vector_store import VectorStore
from backend.app.retrieval.bm25 import BM25Retriever


_SECTION_SCORES = {
    "methods": 1.0,
    "data_availability": 0.95,
    "supplementary": 0.9,
    "table": 0.88,
    "cohort": 0.84,
    "population": 0.82,
    "variables": 0.82,
    "outcome_definition": 0.9,
    "statistical_analysis": 0.86,
    "results": 0.68,
    "abstract": 0.56,
    "title": 0.42,
}


class HybridRetriever:
    def __init__(
        self,
        *,
        store: VectorStore,
        embedding: EmbeddingBackend,
        graph: ScientificGraphStore,
    ) -> None:
        self.store = store
        self.embedding = embedding
        self.graph = graph
        self._bm25 = BM25Retriever([chunk.text for chunk in store.chunks()])

    def retrieve(self, request: EvidenceQueryRequest) -> list[RetrievalHit]:
        query_embedding = self.embedding.embed_query(request.query)
        semantic = {
            chunk.chunk_id: (chunk, score)
            for chunk, score in self.store.query(query_embedding, max(request.top_k * 4, 20))
        }
        related_papers = self.graph.related_paper_ids(request.field_id)
        candidates = []
        requested_sections = {section.casefold() for section in request.sections}
        chunks = self.store.chunks()
        if len(self._bm25.documents) != len(chunks):
            self._bm25 = BM25Retriever([chunk.text for chunk in chunks])
        lexical_scores = [self._bm25.score(request.query, index) for index, _chunk in enumerate(chunks)]
        max_lexical = max(lexical_scores, default=0.0)
        for index, chunk in enumerate(chunks):
            if requested_sections and chunk.section.casefold() not in requested_sections:
                continue
            semantic_score = semantic.get(chunk.chunk_id, (chunk, 0.0))[1]
            lexical_score = lexical_scores[index] / max_lexical if max_lexical else self._lexical_score(request.query, chunk.text)
            # Character-level Chinese tokenization can create accidental BM25 hits;
            # retain the deterministic overlap fallback for Chinese-only queries.
            non_ascii_ratio = sum(ord(char) > 127 for char in request.query) / max(1, len(request.query))
            if not re.search(r"[A-Za-z]", request.query) or non_ascii_ratio > 0.35:
                lexical_score = self._lexical_score(request.query, chunk.text)
            section_score = _SECTION_SCORES.get(chunk.section, 0.35)
            graph_score = 1.0 if chunk.paper_id in related_papers else 0.0
            combined = (
                0.55 * semantic_score
                + 0.30 * lexical_score
                + 0.10 * section_score
                + 0.05 * graph_score
            )
            reasons: list[str] = []
            if lexical_score > 0:
                reasons.append("词法命中")
            if semantic_score >= 0.5:
                reasons.append("语义相似")
            if section_score >= 0.85:
                reasons.append(f"高优先级章节:{chunk.section}")
            if graph_score:
                reasons.append(f"图谱关联字段:{request.field_id}")
            candidates.append(
                (combined, chunk, semantic_score, lexical_score, section_score, graph_score, reasons)
            )
        candidates.sort(key=lambda item: (-item[0], item[1].section_priority, item[1].chunk_id))
        return [
            RetrievalHit(
                rank=rank,
                chunk_id=chunk.chunk_id,
                paper_id=chunk.paper_id,
                source_id=chunk.source_id,
                source_url=chunk.source_url,
                provider=chunk.provider,
                section=chunk.section,
                text=chunk.text,
                score=max(0.0, min(1.0, round(score, 6))),
                semantic_score=max(0.0, min(1.0, round(semantic_score, 6))),
                lexical_score=max(0.0, min(1.0, round(lexical_score, 6))),
                section_score=section_score,
                graph_score=graph_score,
                match_reasons=reasons,
            )
            for rank, (score, chunk, semantic_score, lexical_score, section_score, graph_score, reasons) in enumerate(
                candidates[: request.top_k], start=1
            )
        ]

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        query_tokens = HybridRetriever._tokens(query)
        text_tokens = HybridRetriever._tokens(text)
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = query_tokens & text_tokens
        return min(1.0, len(overlap) / max(1, len(query_tokens)))

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(retrieval_tokens(text))
