from __future__ import annotations

from backend.app.retrieval import (
    RetrievalDocument,
    RetrievalRequest,
    RetrievalServiceV2,
    build_rule_plan,
    query_plan_cache_key,
    reciprocal_rank_fusion,
    validate_query_plan,
)
from backend.app.evaluation.public_retrieval import BM25Index, QueryUnderstandingIndex, evaluate_retriever


def test_rule_plan_preserves_protected_terms_and_validates_queries():
    query = 'PIK3CA 2+ "HER2 positive" response'
    plan = build_rule_plan(query)
    checked = validate_query_plan(plan, query)
    assert checked.valid is True
    assert "PIK3CA" in checked.protected_terms
    assert "2" in checked.protected_terms
    assert checked.accepted_queries


def test_invalid_generated_plan_falls_back_to_original_query():
    checked = validate_query_plan(
        {"keyword_query": "breast cancer", "paraphrase_query": "", "evidence_query": ""},
        "PIK3CA 2+ HER2",
    )
    assert checked.valid is False
    assert checked.fallback_used is True
    assert checked.accepted_queries == ["PIK3CA 2+ HER2"]


def test_rule_plan_bounds_long_public_query_fields():
    plan = build_rule_plan("HER2 " + ("evidence " * 1200))
    assert len(plan.keyword_query) <= 4000
    assert len(plan.paraphrase_query) <= 4000
    assert len(plan.evidence_query) <= 4000


def test_rrf_is_stable_and_deterministic():
    assert reciprocal_rank_fusion([[1, 2], [2, 1], [3]], k=60)[:2] == [(1, 0.03252247488101534), (2, 0.03252247488101534)]
    assert reciprocal_rank_fusion([[2], [1]], k=60) == [(1, 1 / 61), (2, 1 / 61)]


def test_query_plan_cache_key_changes_with_model_or_query():
    first = query_plan_cache_key(query_id="q1", query="PIK3CA", model_id="qwen", prompt_version="v1", schema_version="v1")
    second = query_plan_cache_key(query_id="q1", query="PIK3CA", model_id="qwen-max", prompt_version="v1", schema_version="v1")
    assert first != second


def test_rules_mode_uses_rrf_and_reports_query_count():
    service = RetrievalServiceV2()
    result = service.search(RetrievalRequest(
        query_id="rules-query",
        query="HER2 乳腺癌",
        query_understanding_mode="rules",
        top_k=2,
        documents=[
            RetrievalDocument(doc_id="a", source_id="s1", text="HER2 breast cancer"),
            RetrievalDocument(doc_id="b", source_id="s2", text="ERBB2 breast cancer"),
        ],
    ))
    assert result.telemetry.query_count >= 2
    assert "query_rrf" in result.method
    assert result.telemetry.query_plan_fallback is False


def test_public_ablation_wrapper_changes_only_query_layer():
    corpus = {"d1": "HER2 breast cancer response", "d2": "weather forecast"}
    queries = {"q1": "HER2 乳腺癌"}
    qrels = {"q1": {"d1": 1}}
    baseline = BM25Index(corpus)
    rules = QueryUnderstandingIndex(baseline, "rules")
    baseline_metrics = evaluate_retriever(baseline, queries, qrels)
    rules_metrics = evaluate_retriever(rules, queries, qrels)
    assert rules.method_id.endswith("_query_rules")
    assert rules_metrics.query_count == baseline_metrics.query_count
    assert rules_metrics.ndcg_at_10 >= 0
