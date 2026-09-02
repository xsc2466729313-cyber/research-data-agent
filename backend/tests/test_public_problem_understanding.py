from __future__ import annotations

import pytest

from backend.app.evaluation.public_problem_understanding import (
    _evaluate_labels,
    _predict_lexicon,
    _predict_sequence_features,
    fit_token_lexicon,
)


def test_token_lexicon_is_fit_from_training_examples() -> None:
    train = [
        ("1", ["patients", "received", "drug"], [1, 0, 0]),
        ("2", ["patients", "received", "drug"], [1, 0, 1]),
    ]
    lexicon = fit_token_lexicon(train, threshold=0.5, min_count=2)
    assert "patients" in lexicon
    assert "drug" in lexicon
    assert "received" not in lexicon


def test_pico_metrics_count_token_false_positives_and_negatives() -> None:
    examples = [("1", ["patients", "drug", "response"], [1, 0, 1])]
    result = _evaluate_labels([[1, 1, 0]], examples, 1.0)
    assert result.true_positive == 1
    assert result.false_positive == 1
    assert result.false_negative == 1
    assert result.precision == pytest.approx(0.5)
    assert result.recall == pytest.approx(0.5)
    assert result.f1 == pytest.approx(0.5)


def test_predict_lexicon_preserves_token_sequence_length() -> None:
    examples = [("1", ["Patients", "received"], [1, 0])]
    assert _predict_lexicon(examples, {"patients": 1.0}) == [[1, 0]]


def test_sequence_features_fill_only_short_positive_span_gaps() -> None:
    examples = [("1", ["drug", "and", "therapy"], [1, 0, 1])]
    lexicon = {
        "token=drug": 1.0,
        "token=therapy": 1.0,
    }
    assert _predict_sequence_features(examples, lexicon, threshold=0.5, gap_fill=1) == [[1, 1, 1]]
