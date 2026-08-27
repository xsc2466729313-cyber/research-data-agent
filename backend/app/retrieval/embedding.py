from __future__ import annotations

import hashlib
import math
from backend.app.retrieval_text_features import retrieval_tokens


class HashingDenseRetriever:
    """Offline dense scorer; can be replaced by BGE without changing the interface."""

    name = "hashing-dense-fallback-v1"

    def __init__(self, documents: list[str]) -> None:
        self.documents = documents
        self.dimensions = 384
        self.vectors = [self._embed(doc) for doc in documents]

    def score(self, query: str, index: int) -> float:
        vector = self._embed(query)
        other = self.vectors[index]
        return max(0.0, min(1.0, (sum(a * b for a, b in zip(vector, other)) + 1.0) / 2.0))

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in retrieval_tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        ranked = sorted(((i, self.score(query, i)) for i in range(len(self.documents))), key=lambda x: (-x[1], x[0]))
        return ranked[:top_k]
