from __future__ import annotations

import math
import re
from collections import Counter


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+-]+|[\u4e00-\u9fff]", text.casefold())


class BM25Retriever:
    """Small dependency-free BM25 implementation for deterministic offline use."""

    name = "bm25-v1"

    def __init__(self, documents: list[str], *, k1: float = 1.2, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._terms = [_tokens(doc) for doc in documents]
        self._lengths = [len(item) for item in self._terms]
        self._avgdl = sum(self._lengths) / max(1, len(self._lengths))
        self._df: Counter[str] = Counter(term for terms in self._terms for term in set(terms))

    def score(self, query: str, index: int) -> float:
        q = _tokens(query)
        terms = self._terms[index]
        counts = Counter(terms)
        value = 0.0
        for term in q:
            if term not in counts:
                continue
            df = self._df[term]
            idf = math.log(1.0 + (len(self.documents) - df + 0.5) / (df + 0.5))
            tf = counts[term]
            denom = tf + self.k1 * (1 - self.b + self.b * len(terms) / max(1.0, self._avgdl))
            value += idf * tf * (self.k1 + 1) / denom
        return value

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        ranked = sorted(((i, self.score(query, i)) for i in range(len(self.documents))), key=lambda x: (-x[1], x[0]))
        return ranked[:top_k]
