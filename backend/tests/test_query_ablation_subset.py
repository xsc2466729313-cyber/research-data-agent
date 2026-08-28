from __future__ import annotations

from scripts.build_query_ablation_subset import select_length_stratified_queries
from scripts.run_query_understanding_ablation import _filter_evaluation_subset


def test_length_stratified_selection_is_deterministic_and_balanced() -> None:
    queries = {f"q{index}": "word " * index for index in range(1, 31)}
    first = select_length_stratified_queries(queries, set(queries), count=15, seed="fixed")
    second = select_length_stratified_queries(queries, set(queries), count=15, seed="fixed")
    assert first == second
    assert len(first) == 15
    assert {label: sum(item["stratum"] == label for item in first) for label in ("short", "medium", "long")} == {
        "short": 5,
        "medium": 5,
        "long": 5,
    }


def test_evaluation_subset_filters_all_methods_to_same_queries() -> None:
    queries = {"q1": "one", "q2": "two", "q3": "three"}
    qrels = {query_id: {f"d{index}": 1} for index, query_id in enumerate(queries, start=1)}
    selected = [
        {"query_id": "q1", "stratum": "short"},
        {"query_id": "q3", "stratum": "long"},
    ]
    subset_queries, subset_qrels, strata = _filter_evaluation_subset(queries, qrels, selected)
    assert list(subset_queries) == ["q1", "q3"]
    assert list(subset_qrels) == ["q1", "q3"]
    assert strata == {"short": ["q1"], "long": ["q3"]}
