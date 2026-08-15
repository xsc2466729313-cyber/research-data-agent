from __future__ import annotations

import pytest

from backend.app.evaluation.metrics import (
    error_f1,
    error_precision,
    error_recall,
    faithfulness,
    repair_accuracy,
    retrieval_f1,
    retrieval_precision,
    retrieval_recall,
    sdti,
    traceability,
)


def test_retrieval_metrics_follow_frozen_formulas() -> None:
    precision = retrieval_precision(8, 2)
    recall = retrieval_recall(8, 4)

    assert precision == pytest.approx(0.8)
    assert recall == pytest.approx(2 / 3)
    assert retrieval_f1(precision, recall) == pytest.approx(
        2 * precision * recall / (precision + recall)
    )


def test_integration_error_and_repair_metrics_follow_frozen_formulas() -> None:
    assert faithfulness(19, 20) == pytest.approx(0.95)
    assert traceability(99, 100) == pytest.approx(0.99)
    precision = error_precision(9, 1)
    recall = error_recall(9, 3)
    assert error_f1(precision, recall) == pytest.approx(
        2 * precision * recall / (precision + recall)
    )
    assert repair_accuracy(18, 20) == pytest.approx(0.9)


def test_sdti_is_the_frozen_five_component_geometric_mean() -> None:
    values = (0.8, 0.95, 1.0, 0.9, 0.85)

    assert sdti(*values) == pytest.approx(100 * (0.8 * 0.95 * 1 * 0.9 * 0.85) ** 0.2)


def test_zero_denominators_and_missing_components_are_not_evaluated() -> None:
    assert retrieval_precision(0, 0) is None
    assert retrieval_recall(0, 0) is None
    assert retrieval_f1(0.0, 0.0) is None
    assert faithfulness(0, 0) is None
    assert traceability(0, 0) is None
    assert error_precision(0, 0) is None
    assert error_recall(0, 0) is None
    assert error_f1(None, 1.0) is None
    assert repair_accuracy(0, 0) is None
    assert sdti(1.0, 1.0, None, 1.0, 1.0) is None


def test_metric_functions_reject_invalid_counts_instead_of_clamping() -> None:
    with pytest.raises(ValueError):
        retrieval_precision(-1, 0)
    with pytest.raises(ValueError):
        faithfulness(2, 1)
    with pytest.raises(ValueError):
        repair_accuracy(True, 1)
    with pytest.raises(ValueError):
        sdti(1.1, 1.0, 1.0, 1.0, 1.0)
