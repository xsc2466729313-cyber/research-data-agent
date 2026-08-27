from __future__ import annotations

from .bm25 import BM25Retriever
from .embedding import HashingDenseRetriever
from .query_expansion import expand_query
from .reranker import LexicalReranker


class HybridRetrieverV2:
    """BM25 + dense candidate fusion with an optional transparent reranking stage."""

    name = "bm25+dense+reranker-v2"

    def __init__(self, documents: list[str], *, use_reranker: bool = True) -> None:
        self.documents = documents
        self.bm25 = BM25Retriever(documents)
        self.dense = HashingDenseRetriever(documents)
        self.reranker = LexicalReranker() if use_reranker else None

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        expanded = expand_query(query)
        pool_size = max(top_k * 5, 20)
        lexical = dict(self.bm25.search(expanded, pool_size))
        dense = dict(self.dense.search(expanded, pool_size))
        pool = set(lexical) | set(dense)
        fused = [(i, 0.55 * self._norm(lexical.get(i, 0.0), lexical.values()) + 0.45 * dense.get(i, 0.0)) for i in pool]
        fused.sort(key=lambda x: (-x[1], x[0]))
        if self.reranker:
            reranked = self.reranker.rerank(expanded, self.documents, [i for i, _ in fused[:pool_size]], top_k)
            return [(i, round(score, 6)) for i, score in reranked]
        return [(i, round(score, 6)) for i, score in fused[:top_k]]

    @staticmethod
    def _norm(value: float, values: object) -> float:
        vals = list(values)
        maximum = max(vals, default=0.0)
        return value / maximum if maximum else 0.0
