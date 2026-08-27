from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable

from backend.app.rag.models import (
    EvidenceQueryRequest,
    RAGEvaluationCaseResult,
    RAGEvaluationMetrics,
    RAGEvaluationRequest,
    RAGEvaluationResult,
    RetrievalHit,
)


class RAGEvaluator:
    def evaluate(
        self,
        *,
        topic_id: str,
        request: RAGEvaluationRequest,
        retrieve: Callable[[EvidenceQueryRequest], list[RetrievalHit]],
    ) -> RAGEvaluationResult:
        case_results: list[RAGEvaluationCaseResult] = []
        reciprocal_ranks: list[float] = []
        recalls: list[float] = []
        ndcgs: list[float] = []
        evidence_hits: list[float] = []
        for case in request.cases:
            hits: list[RetrievalHit] = retrieve(
                EvidenceQueryRequest(
                    query=case.query,
                    field_id=case.field_id,
                    top_k=request.top_k,
                )
            )
            expected_sources = {value.casefold() for value in case.expected_source_ids}
            expected_sections = {value.casefold() for value in case.expected_sections}
            source_hits = [hit for hit in hits if hit.source_id.casefold() in expected_sources]
            strict_hits = [
                hit
                for hit in source_hits
                if not expected_sections or hit.section.casefold() in expected_sections
            ]
            first_rank = source_hits[0].rank if source_hits else None
            recalls.append(1.0 if source_hits else 0.0)
            reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
            ndcgs.append(self._ndcg(source_hits, len(expected_sources), request.top_k))
            evidence_hits.append(1.0 if strict_hits else 0.0)
            case_results.append(
                RAGEvaluationCaseResult(
                    case_id=case.case_id,
                    first_relevant_rank=first_rank,
                    relevant_hits=len(strict_hits),
                    retrieved_chunk_ids=[hit.chunk_id for hit in hits],
                )
            )
        count = len(case_results)
        return RAGEvaluationResult(
            topic_id=topic_id,
            gold_set_id=request.gold_set_id,
            gold_set_version=request.gold_set_version,
            top_k=request.top_k,
            case_count=count,
            metrics=RAGEvaluationMetrics(
                recall_at_k=sum(recalls) / count,
                mrr=sum(reciprocal_ranks) / count,
                ndcg_at_k=sum(ndcgs) / count,
                evidence_hit_rate=sum(evidence_hits) / count,
            ),
            cases=case_results,
            evaluated_at=datetime.now(timezone.utc),
            notice=(
                "这些指标只对应请求中提供的冻结 RAG Gold Set，不替代项目冻结 SDTI，"
                "也不表示临床有效性。"
            ),
        )

    @staticmethod
    def _ndcg(hits: list[RetrievalHit], expected_count: int, top_k: int) -> float:
        seen: set[str] = set()
        dcg = 0.0
        for hit in hits:
            key = hit.source_id.casefold()
            if key in seen:
                continue
            seen.add(key)
            dcg += 1.0 / math.log2(hit.rank + 1)
        ideal_count = min(expected_count, top_k)
        if ideal_count <= 0:
            return 0.0
        ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        return min(1.0, dcg / ideal)
