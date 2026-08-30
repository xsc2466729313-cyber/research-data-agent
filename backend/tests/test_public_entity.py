from __future__ import annotations

import pytest

from backend.app.evaluation.public_entity import EntityRuleConfig, evaluate_entity_pairs
from backend.app.integration.entity_matcher_v3 import EntityMatcherV3Config


def test_entity_metrics_count_false_positives_and_negatives() -> None:
    pairs = [
        ({"title": "same book"}, {"title": "same book"}, 1),
        ({"title": "same book"}, {"title": "same book"}, 0),
        ({"title": "missing match"}, {"title": "different"}, 1),
    ]
    result = evaluate_entity_pairs(pairs, "exact_title")
    assert result.true_positive == 1
    assert result.false_positive == 1
    assert result.false_negative == 1
    assert result.precision == pytest.approx(0.5)
    assert result.recall == pytest.approx(0.5)
    assert result.f1 == pytest.approx(0.5)


def test_project_rule_handles_title_and_supporting_fields() -> None:
    pairs = [
        ({"title": "A neural database", "authors": "Jane Doe", "year": "2020"}, {"title": "A neural database system", "authors": "Jane Doe", "year": "2020"}, 1),
        ({"title": "A neural database", "authors": "Jane Doe", "year": "2020"}, {"title": "A neural system", "authors": "Other", "year": "1990"}, 0),
    ]
    result = evaluate_entity_pairs(pairs, "project_portability_rule_v1")
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)


def test_entity_fusion_requires_both_candidate_views() -> None:
    pairs = [
        ({"title": "same book", "year": "2020"}, {"title": "same book", "year": "2020"}, 1),
        ({"title": "same book", "year": "2020"}, {"title": "different title", "year": "1990"}, 0),
    ]
    result = evaluate_entity_pairs(
        pairs,
        "project_entity_fusion_v4",
        rule_config={
            "v2": EntityRuleConfig(0.35, 0.20, 0.15, 0.20, 0.10, 0.50),
            "v3": EntityMatcherV3Config(review_threshold=0.50),
        },
    )
    assert result.true_positive == 1
    assert result.false_positive == 0
