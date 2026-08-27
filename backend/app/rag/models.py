from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from backend.app.models import ApiModel


class PaperChunk(ApiModel):
    chunk_id: str
    topic_id: str
    paper_id: str
    source_id: str
    provider: str
    source_url: str
    section: str
    section_priority: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=5000)
    raw_field: str
    raw_value: str = Field(min_length=1, max_length=5000)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)


class RAGIndexRequest(ApiModel):
    contract_id: str | None = None


class RAGIndexReport(ApiModel):
    topic_id: str
    chunk_count: int = Field(ge=0)
    paper_count: int = Field(ge=0)
    vector_backend: str
    embedding_backend: str
    graph_backend: str
    graph_node_count: int = Field(ge=0)
    graph_edge_count: int = Field(ge=0)
    indexed_at: datetime
    warnings: list[str] = Field(default_factory=list)


class EvidenceQueryRequest(ApiModel):
    query: str = Field(min_length=2, max_length=1000)
    field_id: str | None = Field(default=None, min_length=1, max_length=256)
    top_k: int = Field(default=5, ge=1, le=20)
    sections: list[str] = Field(default_factory=list, max_length=20)


class RetrievalHit(ApiModel):
    rank: int = Field(ge=1)
    chunk_id: str
    paper_id: str
    source_id: str
    source_url: str
    provider: str
    section: str
    text: str
    score: float = Field(ge=0, le=1)
    semantic_score: float = Field(ge=0, le=1)
    lexical_score: float = Field(ge=0, le=1)
    section_score: float = Field(ge=0, le=1)
    graph_score: float = Field(ge=0, le=1)
    match_reasons: list[str] = Field(default_factory=list)


class EvidenceQueryResponse(ApiModel):
    topic_id: str
    query: str
    field_id: str | None = None
    retrieval_mode: str
    hits: list[RetrievalHit]
    evidence_found: bool
    notice: str

class GraphNode(ApiModel):
    node_id: str
    node_type: str
    label: str
    source_id: str | None = None
    source_url: str | None = None


class GraphEdge(ApiModel):
    source: str
    target: str
    relation: str


class ScientificGraphSnapshot(ApiModel):
    topic_id: str
    backend: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RAGEvaluationCase(ApiModel):
    case_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=2, max_length=1000)
    expected_source_ids: list[str] = Field(min_length=1, max_length=100)
    expected_sections: list[str] = Field(default_factory=list, max_length=20)
    field_id: str | None = None


class RAGEvaluationRequest(ApiModel):
    gold_set_id: str = Field(min_length=1, max_length=128)
    gold_set_version: str = Field(min_length=1, max_length=64)
    gold_set_frozen: bool
    top_k: int = Field(default=5, ge=1, le=20)
    cases: list[RAGEvaluationCase] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_frozen_gold_set(self) -> RAGEvaluationRequest:
        if not self.gold_set_frozen:
            raise ValueError("RAG evaluation requires a reviewed and frozen Gold Set")
        return self


class RAGEvaluationCaseResult(ApiModel):
    case_id: str
    first_relevant_rank: int | None = Field(default=None, ge=1)
    relevant_hits: int = Field(ge=0)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)


class RAGEvaluationMetrics(ApiModel):
    recall_at_k: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    ndcg_at_k: float = Field(ge=0, le=1)
    evidence_hit_rate: float = Field(ge=0, le=1)


class RAGEvaluationResult(ApiModel):
    topic_id: str
    gold_set_id: str
    gold_set_version: str
    top_k: int
    case_count: int = Field(ge=1)
    metrics: RAGEvaluationMetrics
    cases: list[RAGEvaluationCaseResult]
    evaluated_at: datetime
    status: Literal["EVALUATED"] = "EVALUATED"
    notice: str
