from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from .bm25 import BM25Retriever


class LexicalReranker:
    """Transparent reranker used offline; production can inject a cross-encoder."""

    name = "lexical-reranker-v1"

    def rerank(self, query: str, documents: list[str], candidates: list[int], top_k: int = 10) -> list[tuple[int, float]]:
        scorer = BM25Retriever(documents)
        ranked = [(index, scorer.score(query, index)) for index in candidates]
        return sorted(ranked, key=lambda x: (-x[1], x[0]))[:top_k]


@lru_cache(maxsize=2)
def _load_cross_encoder(model_name: str) -> Any:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "Neural reranking requires sentence-transformers from backend/requirements-rag.txt"
        ) from exc
    return CrossEncoder(model_name)


class CrossEncoderReranker:
    """Real query-document reranker; scores are converted to [0, 1]."""

    def __init__(
        self,
        *,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2",
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.name = model_name
        self._model = model or _load_cross_encoder(model_name)

    def rerank(
        self,
        query: str,
        documents: list[str],
        candidates: list[int],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        pairs = [(query, documents[index]) for index in candidates]
        raw = self._model.predict(pairs, show_progress_bar=False)
        scores = [float(value) for value in raw]
        normalized = [1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, value)))) for value in scores]
        ranked = sorted(zip(candidates, normalized), key=lambda item: (-item[1], item[0]))
        return ranked[:top_k]
