from __future__ import annotations

import math
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Semantic retrieval requires sentence-transformers from backend/requirements-rag.txt"
        ) from exc
    return SentenceTransformer(model_name)


class SentenceTransformerDenseRetriever:
    """Real neural dense retrieval backend with normalized cosine scores."""

    def __init__(
        self,
        documents: list[str],
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        model: Any | None = None,
        query_instruction: str = "Represent this sentence for searching relevant passages: ",
    ) -> None:
        self.documents = documents
        self.model_name = model_name
        self.name = model_name
        self.query_instruction = query_instruction
        self._model = model or _load_sentence_transformer(model_name)
        self.vectors = self._encode(documents)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        values = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [row.tolist() if hasattr(row, "tolist") else list(row) for row in values]

    def score(self, query: str, index: int) -> float:
        vector = self._encode([self.query_instruction + query])[0]
        cosine = sum(a * b for a, b in zip(vector, self.vectors[index]))
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        vector = self._encode([self.query_instruction + query])[0]
        ranked: list[tuple[int, float]] = []
        for index, other in enumerate(self.vectors):
            cosine = sum(a * b for a, b in zip(vector, other))
            if math.isfinite(cosine):
                ranked.append((index, max(0.0, min(1.0, (cosine + 1.0) / 2.0))))
        return sorted(ranked, key=lambda item: (-item[1], item[0]))[:top_k]
