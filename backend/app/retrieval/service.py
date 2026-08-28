from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from backend.app.governance.audit import build_audit_stamp
from backend.app.vnext_config import load_vnext_config

from .bm25 import BM25Retriever
from .embedding import HashingDenseRetriever
from .dense import SentenceTransformerDenseRetriever
from .models import RetrievalHit, RetrievalRequest, RetrievalResponse, RetrievalTelemetry
from .query_expansion import expand_query
from .query_understanding import (
    build_rule_plan,
    reciprocal_rank_fusion,
    validate_query_plan,
)
from .reranker import CrossEncoderReranker


class RetrievalServiceV2:
    """Audited retrieval facade with explicit offline-fallback labeling."""

    VERSION = "retrieval-service-v2"

    def __init__(
        self,
        *,
        dense_factory: Callable[[list[str]], Any] | None = None,
        reranker_factory: Callable[[], Any] | None = None,
        query_planner: Callable[[str], Any] | None = None,
    ) -> None:
        self.settings = load_vnext_config().retrieval
        if abs(self.settings.bm25_weight + self.settings.dense_weight - 1.0) > 1e-9:
            raise ValueError("retrieval fusion weights must sum to 1")
        self.invocation_count = 0
        self.qwen_invocation_count = 0
        self._dense_factory = dense_factory or (
            lambda texts: SentenceTransformerDenseRetriever(
                texts,
                model_name=self.settings.dense_backend,
                query_instruction=self.settings.query_instruction,
            )
        )
        self._reranker_factory = reranker_factory or (
            lambda: CrossEncoderReranker(model_name=self.settings.reranker_backend)
        )
        self._query_planner = query_planner

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        started = perf_counter()
        self.invocation_count += 1
        texts = [item.text for item in request.documents]
        queries, plan_fallback = self._queries(request)
        query = queries[0]
        bm25 = BM25Retriever(texts)
        pool_size = min(len(texts), max(request.top_k * self.settings.candidate_pool_multiplier, 20))
        lexical_raw = dict(bm25.search(query, pool_size))
        lexical = self._normalize(lexical_raw)
        if request.method == "bm25":
            dense = None
        elif request.method == "hashing_dense_fallback":
            dense = HashingDenseRetriever(texts)
        else:
            dense = self._dense_factory(texts)
        dense_raw = {} if dense is None else dict(dense.search(query, pool_size))
        pool = set(lexical_raw) | set(dense_raw)
        fused = {
            index: self.settings.bm25_weight * lexical.get(index, 0.0) + self.settings.dense_weight * dense_raw.get(index, 0.0)
            for index in pool
        }

        if len(queries) > 1:
            rrf_rankings = [
                [index for index, _score in bm25.search(item, pool_size)]
                for item in queries
            ]
            rrf_raw = dict(reciprocal_rank_fusion(rrf_rankings, k=60, top_k=pool_size))
            ranked = [index for index, _score in sorted(rrf_raw.items(), key=lambda item: (-item[1], item[0]))]
            final_score = self._normalize(rrf_raw)
            method = f"{request.method}_query_rrf_v1"
        elif request.method == "bm25":
            ranked = sorted(pool, key=lambda index: (-lexical.get(index, 0.0), index))
            final_score = lexical
            method = "bm25_v1"
        elif request.method == "hashing_dense_fallback":
            ranked = sorted(pool, key=lambda index: (-dense_raw.get(index, 0.0), index))
            final_score = dense_raw
            method = "hashing_dense_fallback_v1"
        elif request.method == "semantic":
            ranked = sorted(pool, key=lambda index: (-dense_raw.get(index, 0.0), index))
            final_score = dense_raw
            method = f"semantic_v2:{dense.name}"
        elif request.method == "hybrid":
            ranked = sorted(pool, key=lambda index: (-fused.get(index, 0.0), index))
            final_score = fused
            method = f"bm25_semantic_fusion_v2:{dense.name}"
        elif request.method == "hybrid_rerank":
            reranker = self._reranker_factory()
            initial = sorted(pool, key=lambda index: (-fused.get(index, 0.0), index))
            reranked = reranker.rerank(query, texts, initial[:pool_size], pool_size)
            rerank_raw = dict(reranked)
            rerank_normalized = self._normalize(rerank_raw)
            ranked = [index for index, _ in reranked]
            final_score = rerank_normalized
            method = f"bm25_semantic_cross_encoder_v2:{dense.name}+{reranker.name}"

        hits: list[RetrievalHit] = []
        rerank_values = final_score if request.method == "hybrid_rerank" else {}
        for rank, index in enumerate(ranked[: request.top_k], 1):
            document = request.documents[index]
            hits.append(
                RetrievalHit(
                    doc_id=document.doc_id,
                    source_id=document.source_id,
                    bm25_score=round(lexical.get(index, 0.0), 6),
                    dense_score=round(dense_raw.get(index, 0.0), 6),
                    fusion_score=round(fused.get(index, 0.0), 6),
                    rerank_score=round(rerank_values.get(index, 0.0), 6),
                    rank=rank,
                    metadata=document.metadata,
                )
            )

        output_basis = {
            "query_id": request.query_id,
            "method": method,
            "results": [item.model_dump(mode="json") for item in hits],
        }
        audit = build_audit_stamp(
            input_value=request,
            output_value=output_basis,
            model_name="none" if dense is None else dense.name,
            model_version="not-invoked" if dense is None else dense.name,
            rule_version="0.1",
            schema_version="0.1",
            dataset_manifest=request.dataset_manifest,
        )
        latency = round((perf_counter() - started) * 1000, 3)
        return RetrievalResponse(
            query_id=request.query_id,
            query=request.query,
            results=hits,
            method=method,
            telemetry=RetrievalTelemetry(
                latency_ms=latency,
                candidate_count=len(pool),
                dense_backend="not-invoked" if dense is None else dense.name,
                reranker_backend=self.settings.reranker_backend if request.method == "hybrid_rerank" else "not-invoked",
                qwen_invoked=False,
                invocation_count=self.invocation_count,
                qwen_invocation_count=self.qwen_invocation_count,
                qwen_invocation_rate=(self.qwen_invocation_count / self.invocation_count),
                query_count=len(queries),
                query_plan_fallback=plan_fallback,
                notice=(
                    "This run uses the deterministic hashing offline fallback; it is not a semantic-model result."
                    if request.method == "hashing_dense_fallback"
                    else (
                        "Query understanding failed validation; original query was retained."
                        if plan_fallback
                        else "Model names report the backends actually invoked; Qwen was not used for scoring."
                    )
                ),
            ),
            audit=audit,
        )

    @staticmethod
    def _normalize(values: dict[int, float]) -> dict[int, float]:
        maximum = max(values.values(), default=0.0)
        if maximum <= 0:
            return {key: 0.0 for key in values}
        return {key: min(1.0, max(0.0, value / maximum)) for key, value in values.items()}

    def _queries(self, request: RetrievalRequest) -> tuple[list[str], bool]:
        mode = request.query_understanding_mode
        raw = request.query.strip()
        if mode == "raw":
            return [raw], False
        if mode in {"compat", "rules"}:
            plan = build_rule_plan(raw)
            validation = validate_query_plan(plan, raw)
            if mode == "compat":
                return [expand_query(raw)], False
            return validation.accepted_queries or [raw], validation.fallback_used
        if self._query_planner is None:
            return [raw], True
        try:
            candidate = self._query_planner(raw)
            validation = validate_query_plan(candidate, raw)
            if mode == "qwen_single":
                return ([validation.accepted_queries[0]] if validation.accepted_queries else [raw]), validation.fallback_used
            return validation.accepted_queries or [raw], validation.fallback_used
        except Exception:
            return [raw], True
