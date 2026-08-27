from __future__ import annotations

from .bm25 import BM25Retriever


class LexicalReranker:
    """Transparent reranker used offline; production can inject a cross-encoder."""

    name = "lexical-reranker-v1"

    def rerank(self, query: str, documents: list[str], candidates: list[int], top_k: int = 10) -> list[tuple[int, float]]:
        scorer = BM25Retriever(documents)
        ranked = [(index, scorer.score(query, index)) for index in candidates]
        return sorted(ranked, key=lambda x: (-x[1], x[0]))[:top_k]
