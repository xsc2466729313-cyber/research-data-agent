from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


class SentenceTransformerBenchmarkIndex:
    method_id = "vnext_bge_small_en_v1_5"
    method_label = "VNext BGE-small-en-v1.5"
    estimated_cost_usd = 0.0
    qwen_invocation_rate = 0.0

    def __init__(
        self,
        corpus: dict[str, str],
        *,
        model_name: str,
        cache_path: Path,
        model: Any | None = None,
        query_instruction: str = "Represent this sentence for searching relevant passages: ",
        batch_size: int | None = None,
        max_seq_length: int | None = None,
    ) -> None:
        started = time.perf_counter()
        self.doc_ids = list(corpus)
        self.documents = [corpus[item] for item in self.doc_ids]
        self.model_name = model_name
        self.query_instruction = query_instruction
        self.batch_size = batch_size or int(os.getenv("VNEXT_EMBED_BATCH_SIZE", "256"))
        self.max_seq_length = max_seq_length or int(os.getenv("VNEXT_EMBED_MAX_SEQ_LENGTH", "128"))
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        self.model = model
        if hasattr(self.model, "max_seq_length"):
            self.model.max_seq_length = self.max_seq_length
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = cache_path.with_suffix(".json")
        expected = {"model_name": model_name, "document_count": len(self.doc_ids), "first_doc_id": self.doc_ids[0] if self.doc_ids else None, "max_seq_length": self.max_seq_length}
        if cache_path.exists() and meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8")) == expected:
            self.embeddings = np.load(cache_path, mmap_mode="r")
        else:
            encoded = model.encode(
                self.documents,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=True,
            )
            self.embeddings = np.asarray(encoded, dtype=np.float32)
            np.save(cache_path, self.embeddings)
            meta_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
        self.index_build_seconds = time.perf_counter() - started
        self._query_cache: dict[str, np.ndarray] = {}

    def reset_query_cache(self) -> None:
        self._query_cache.clear()

    def scores(self, query: str) -> np.ndarray:
        vector = self._query_cache.get(query)
        if vector is None:
            encoded = self.model.encode(
                [self.query_instruction + query],
                batch_size=1,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vector = np.asarray(encoded[0], dtype=np.float32)
            self._query_cache[query] = vector
        return np.asarray(self.embeddings @ vector, dtype=np.float32)

    def scores_many(self, queries: list[str]) -> list[np.ndarray]:
        missing = [query for query in queries if query not in self._query_cache]
        if missing:
            encoded = self.model.encode(
                [self.query_instruction + query for query in missing],
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            for query, vector in zip(missing, encoded):
                self._query_cache[query] = np.asarray(vector, dtype=np.float32)
        query_matrix = np.asarray([self._query_cache[query] for query in queries], dtype=np.float32)
        scores = query_matrix @ np.asarray(self.embeddings, dtype=np.float32).T
        return [np.asarray(row, dtype=np.float32) for row in scores]

    def rank(self, query: str, top_k: int) -> list[str]:
        scores = self.scores(query)
        count = min(top_k, len(scores))
        if count <= 0:
            return []
        candidates = np.argpartition(-scores, count - 1)[:count]
        ranked = candidates[np.argsort(-scores[candidates], kind="stable")]
        return [self.doc_ids[int(index)] for index in ranked]

    def rank_many(self, queries: list[str], top_k: int) -> list[list[str]]:
        output: list[list[str]] = []
        for scores in self.scores_many(queries):
            count = min(top_k, len(scores))
            candidates = np.argpartition(-scores, count - 1)[:count] if count else np.array([], dtype=int)
            ranked = candidates[np.argsort(-scores[candidates], kind="stable")]
            output.append([self.doc_ids[int(index)] for index in ranked])
        return output


class HybridSemanticBenchmarkIndex:
    method_id = "vnext_bm25_bge_fusion_v1"
    method_label = "VNext BM25 + BGE fusion"
    estimated_cost_usd = 0.0
    qwen_invocation_rate = 0.0

    def __init__(self, lexical: Any, semantic: SentenceTransformerBenchmarkIndex, *, lexical_weight: float = 0.55, dense_weight: float = 0.45) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.doc_ids = semantic.doc_ids
        self.documents = semantic.documents
        self.lexical_weight = lexical_weight
        self.dense_weight = dense_weight
        self.index_build_seconds = semantic.index_build_seconds

    def reset_query_cache(self) -> None:
        self.semantic.reset_query_cache()

    def rank(self, query: str, top_k: int) -> list[str]:
        return self._rank_scores(query, self.semantic.scores(query), top_k)

    def _rank_scores(self, query: str, dense_scores: np.ndarray, top_k: int) -> list[str]:
        lexical_scores = self.lexical.score(query)
        pool_size = min(len(self.doc_ids), max(200, top_k * 2))
        dense_candidates = np.argpartition(-dense_scores, pool_size - 1)[:pool_size] if pool_size else np.array([], dtype=int)
        lexical_candidates = sorted(lexical_scores, key=lambda index: (-lexical_scores[index], self.doc_ids[index]))[:pool_size]
        candidates = set(int(index) for index in dense_candidates) | set(lexical_candidates)
        lexical_max = max(lexical_scores.values(), default=0.0)
        fused = {
            index: self.lexical_weight * (lexical_scores.get(index, 0.0) / lexical_max if lexical_max else 0.0)
            + self.dense_weight * max(0.0, min(1.0, (float(dense_scores[index]) + 1.0) / 2.0))
            for index in candidates
        }
        ranked = sorted(candidates, key=lambda index: (-fused[index], self.doc_ids[index]))[:top_k]
        return [self.doc_ids[index] for index in ranked]

    def rank_many(self, queries: list[str], top_k: int) -> list[list[str]]:
        dense_scores = self.semantic.scores_many(queries)
        return [self._rank_scores(query, scores, top_k) for query, scores in zip(queries, dense_scores)]


class CrossEncoderBenchmarkIndex:
    method_id = "vnext_bm25_bge_cross_encoder_v1"
    method_label = "VNext BM25 + BGE + CrossEncoder"
    estimated_cost_usd = 0.0
    qwen_invocation_rate = 0.0

    def __init__(
        self,
        hybrid: HybridSemanticBenchmarkIndex,
        *,
        model_name: str,
        rerank_k: int = 10,
        model: Any | None = None,
    ) -> None:
        started = time.perf_counter()
        self.hybrid = hybrid
        self.doc_ids = hybrid.doc_ids
        self.documents = hybrid.documents
        self.by_id = dict(zip(self.doc_ids, self.documents))
        self.model_name = model_name
        self.rerank_k = rerank_k
        if model is None:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(model_name)
        self.model = model
        self.index_build_seconds = hybrid.index_build_seconds + (time.perf_counter() - started)

    def reset_query_cache(self) -> None:
        self.hybrid.reset_query_cache()

    def rank(self, query: str, top_k: int) -> list[str]:
        candidates = self.hybrid.rank(query, max(top_k, 100))
        head = candidates[: self.rerank_k]
        raw = self.model.predict([(query, self.by_id[doc_id]) for doc_id in head], show_progress_bar=False)
        scored = sorted(zip(head, [float(item) for item in raw]), key=lambda item: (-item[1], item[0]))
        reranked_ids = [item[0] for item in scored]
        return (reranked_ids + candidates[self.rerank_k :])[:top_k]
