from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from pydantic import Field

from backend.app.models import ApiModel
from backend.app.retrieval.query_expansion import expand_query


class RetrievalQueryPlan(ApiModel):
    """Domain-neutral, auditable query understanding output."""

    intent: str = Field(default="retrieve relevant evidence", max_length=500)
    key_concepts: list[str] = Field(default_factory=list, max_length=8)
    entities: list[str] = Field(default_factory=list, max_length=8)
    constraints: list[str] = Field(default_factory=list, max_length=8)
    must_keep_terms: list[str] = Field(default_factory=list, max_length=32)
    keyword_query: str = Field(default="", max_length=4000)
    paraphrase_query: str = Field(default="", max_length=4000)
    evidence_query: str = Field(default="", max_length=4000)


class QueryPlanValidation(ApiModel):
    valid: bool
    accepted_queries: list[str] = Field(default_factory=list)
    rejected_queries: list[str] = Field(default_factory=list)
    protected_terms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    fallback_used: bool = False


_TOKEN_RE = re.compile(r"(?:[A-Z]{2,}[A-Z0-9_+./-]*|\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9_+./-]{1,})")
_QUOTED_RE = re.compile(r"[\"']([^\"']{2,80})[\"']")
_NEGATION_TERMS = ("not", "no", "without", "否", "不", "无", "未")


def protected_terms(query: str) -> list[str]:
    terms = [item.strip() for item in _QUOTED_RE.findall(query or "") if item.strip()]
    terms.extend(_TOKEN_RE.findall(query or ""))
    terms.extend(term for term in (query or "").split() if term.isupper() and len(term) > 1)
    return list(dict.fromkeys(terms))[:32]


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def _bounded_query(query: str, limit: int = 4000) -> str:
    """Keep generated plans within the public contract for long BEIR queries."""
    value = normalize_query(query)
    return value if len(value) <= limit else value[:limit].rstrip()


def build_rule_plan(query: str) -> RetrievalQueryPlan:
    raw = normalize_query(query)
    expanded = normalize_query(expand_query(raw))
    terms = protected_terms(raw)
    words = [item for item in re.findall(r"[A-Za-z][A-Za-z0-9_+./-]{1,}|[\u4e00-\u9fff]{2,}", raw) if item]
    concepts = list(dict.fromkeys(words))[:8]
    constraints = [term for term in _NEGATION_TERMS if term.casefold() in raw.casefold()][:8]
    return RetrievalQueryPlan(
        intent="retrieve relevant evidence",
        key_concepts=concepts,
        entities=terms[:8],
        constraints=constraints,
        must_keep_terms=terms,
        keyword_query=_bounded_query(expanded),
        paraphrase_query=_bounded_query(raw),
        evidence_query=_bounded_query(f"{expanded} evidence"),
    )


def validate_query_plan(plan: RetrievalQueryPlan | dict[str, Any], original_query: str) -> QueryPlanValidation:
    parsed = plan if isinstance(plan, RetrievalQueryPlan) else RetrievalQueryPlan.model_validate(plan)
    raw = normalize_query(original_query)
    protected = list(dict.fromkeys([*protected_terms(raw), *parsed.must_keep_terms]))
    candidates = [parsed.keyword_query, parsed.paraphrase_query, parsed.evidence_query]
    accepted: list[str] = []
    rejected: list[str] = []
    reasons: list[str] = []
    for candidate in candidates:
        value = normalize_query(candidate)
        if not value or len(value) > 4000:
            continue
        folded = value.casefold()
        missing = [term for term in protected if term.casefold() not in folded]
        if missing:
            rejected.append(value)
            reasons.append(f"query dropped because protected terms are missing: {','.join(missing[:6])}")
            continue
        if value not in accepted:
            accepted.append(value)
    if not accepted:
        return QueryPlanValidation(
            valid=False,
            accepted_queries=[raw],
            rejected_queries=rejected,
            protected_terms=protected,
            reasons=[*reasons, "all generated queries were invalid; original query retained"],
            fallback_used=True,
        )
    return QueryPlanValidation(
        valid=True,
        accepted_queries=accepted,
        rejected_queries=rejected,
        protected_terms=protected,
        reasons=reasons,
        fallback_used=False,
    )


def query_plan_cache_key(*, query_id: str, query: str, model_id: str, prompt_version: str, schema_version: str) -> str:
    payload = {
        "query_id": query_id,
        "query": query,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def reciprocal_rank_fusion(rankings: Iterable[Iterable[int]], *, k: int = 60, top_k: int | None = None) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ordered if top_k is None else ordered[:top_k]


__all__ = [
    "RetrievalQueryPlan",
    "QueryPlanValidation",
    "build_rule_plan",
    "normalize_query",
    "protected_terms",
    "query_plan_cache_key",
    "reciprocal_rank_fusion",
    "validate_query_plan",
]
