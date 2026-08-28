from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.app.governance.models import AuditStamp
from backend.app.models import ApiModel


RetrievalMethod = Literal["bm25", "semantic", "hashing_dense_fallback", "hybrid", "hybrid_rerank"]


class RetrievalDocument(ApiModel):
    doc_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalRequest(ApiModel):
    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=4000)
    documents: list[RetrievalDocument] = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=10, ge=1, le=100)
    method: RetrievalMethod = "bm25"
    dataset_manifest: str = "inline-request"
    query_understanding_mode: Literal["compat", "raw", "rules", "qwen_single", "qwen_multi_validated"] = "compat"


class RetrievalHit(ApiModel):
    doc_id: str
    source_id: str
    bm25_score: float = Field(ge=0)
    dense_score: float = Field(ge=0, le=1)
    fusion_score: float = Field(ge=0, le=1)
    rerank_score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalTelemetry(ApiModel):
    latency_ms: float = Field(ge=0)
    candidate_count: int = Field(ge=0)
    dense_backend: str
    reranker_backend: str
    qwen_invoked: bool = False
    invocation_count: int = Field(ge=0)
    qwen_invocation_count: int = Field(ge=0)
    qwen_invocation_rate: float = Field(ge=0, le=1)
    query_count: int = Field(default=1, ge=1)
    query_plan_fallback: bool = False
    notice: str


class RetrievalResponse(ApiModel):
    query_id: str
    query: str
    results: list[RetrievalHit]
    method: str
    telemetry: RetrievalTelemetry
    audit: AuditStamp
