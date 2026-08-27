from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol

from backend.app.rag.text_features import retrieval_tokens


class EmbeddingBackend(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashingEmbeddingBackend:
    """Deterministic offline fallback; useful for tests, not advertised as BGE."""

    name = "hashing-lexical-v1"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 64:
            raise ValueError("dimensions must be at least 64")
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return retrieval_tokens(text)


class BGEEmbeddingBackend:
    name = "BAAI/bge-small-zh-v1.5"
    query_instruction = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, *, model_name: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "BGE backend requires optional dependencies from backend/requirements-rag.txt"
            ) from exc
        self.model_name = model_name or os.getenv("RAG_BGE_MODEL", self.name)
        self._model = SentenceTransformer(self.model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        values = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [row.tolist() for row in values]

    def embed_query(self, text: str) -> list[float]:
        values = self._model.encode(
            [self.query_instruction + text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return values[0].tolist()


def create_embedding_backend() -> tuple[EmbeddingBackend, list[str]]:
    requested = os.getenv("RAG_EMBEDDING_BACKEND", "hashing").strip().casefold()
    if requested == "bge":
        try:
            return BGEEmbeddingBackend(), []
        except Exception as exc:
            return HashingEmbeddingBackend(), [
                f"BGE 未启用，已回退 hashing embedding：{type(exc).__name__}。"
            ]
    return HashingEmbeddingBackend(), []
