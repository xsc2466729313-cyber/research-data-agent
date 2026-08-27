from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Protocol

from backend.app.rag.models import PaperChunk


class VectorStore(Protocol):
    name: str

    def clear(self) -> None: ...

    def upsert(self, chunks: list[PaperChunk], embeddings: list[list[float]]) -> None: ...

    def query(self, embedding: list[float], top_k: int) -> list[tuple[PaperChunk, float]]: ...

    def chunks(self) -> list[PaperChunk]: ...


class InMemoryVectorStore:
    name = "memory-cosine"

    def __init__(self) -> None:
        self._records: dict[str, tuple[PaperChunk, list[float]]] = {}

    def clear(self) -> None:
        self._records.clear()

    def upsert(self, chunks: list[PaperChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        for chunk, embedding in zip(chunks, embeddings):
            self._records[chunk.chunk_id] = (chunk, embedding)

    def query(self, embedding: list[float], top_k: int) -> list[tuple[PaperChunk, float]]:
        scored = [
            (chunk, self._cosine(embedding, vector))
            for chunk, vector in self._records.values()
        ]
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [(chunk, max(0.0, min(1.0, score))) for chunk, score in scored[:top_k]]

    def chunks(self) -> list[PaperChunk]:
        return [record[0] for record in self._records.values()]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)


class ChromaVectorStore:
    name = "chroma"

    def __init__(self, *, collection_name: str, path: Path | None = None) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "Chroma backend requires optional dependencies from backend/requirements-rag.txt"
            ) from exc
        self._client = chromadb.PersistentClient(path=str(path)) if path else chromadb.Client()
        self._collection = self._client.get_or_create_collection(collection_name)
        self._chunks: dict[str, PaperChunk] = {}

    def clear(self) -> None:
        result = self._collection.get()
        ids = result.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        self._chunks.clear()

    def upsert(self, chunks: list[PaperChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return
        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.text for chunk in chunks],
            metadatas=[{"chunk_json": chunk.model_dump_json()} for chunk in chunks],
        )
        self._chunks.update({chunk.chunk_id: chunk for chunk in chunks})

    def query(self, embedding: list[float], top_k: int) -> list[tuple[PaperChunk, float]]:
        record_count = self._collection.count()
        if record_count <= 0:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, record_count),
            include=["metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        output: list[tuple[PaperChunk, float]] = []
        for chunk_id, metadata, distance in zip(ids, metadatas, distances):
            chunk = self._chunks.get(chunk_id)
            if chunk is None and metadata and metadata.get("chunk_json"):
                chunk = PaperChunk.model_validate_json(metadata["chunk_json"])
                self._chunks[chunk.chunk_id] = chunk
            if chunk is None:
                continue
            score = 1.0 - float(distance or 0.0)
            output.append((chunk, max(0.0, min(1.0, score))))
        return output

    def chunks(self) -> list[PaperChunk]:
        if self._chunks:
            return list(self._chunks.values())
        result = self._collection.get(include=["metadatas"])
        for metadata in result.get("metadatas") or []:
            if metadata and metadata.get("chunk_json"):
                chunk = PaperChunk.model_validate_json(metadata["chunk_json"])
                self._chunks[chunk.chunk_id] = chunk
        return list(self._chunks.values())


def create_vector_store(topic_id: str) -> tuple[VectorStore, list[str]]:
    requested = os.getenv("RAG_VECTOR_BACKEND", "memory").strip().casefold()
    if requested == "chroma":
        name = "planning_" + "".join(char for char in topic_id.casefold() if char.isalnum())[-40:]
        path_value = os.getenv("RAG_CHROMA_PATH", "").strip()
        path = Path(path_value) if path_value else None
        try:
            return ChromaVectorStore(collection_name=name, path=path), []
        except Exception as exc:
            return InMemoryVectorStore(), [
                f"Chroma 未启用，已回退内存向量库：{type(exc).__name__}。"
            ]
    return InMemoryVectorStore(), []
