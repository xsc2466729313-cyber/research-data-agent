from __future__ import annotations

from math import prod


def _count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _rate(numerator: int, denominator: int) -> float | None:
    numerator = _count(numerator, "numerator")
    denominator = _count(denominator, "denominator")
    if numerator > denominator:
        raise ValueError("numerator cannot exceed denominator")
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if not 0 <= precision <= 1 or not 0 <= recall <= 1:
        raise ValueError("precision and recall must be between 0 and 1")
    denominator = precision + recall
    if denominator == 0:
        return None
    return 2 * precision * recall / denominator


def retrieval_precision(tp: int, fp: int) -> float | None:
    tp = _count(tp, "tp")
    fp = _count(fp, "fp")
    return _rate(tp, tp + fp)


def retrieval_recall(tp: int, fn: int) -> float | None:
    tp = _count(tp, "tp")
    fn = _count(fn, "fn")
    return _rate(tp, tp + fn)


def retrieval_f1(precision: float | None, recall: float | None) -> float | None:
    return _f1(precision, recall)


def faithfulness(faithful_fields: int, sampled_critical_fields: int) -> float | None:
    return _rate(faithful_fields, sampled_critical_fields)


def traceability(
    fields_with_complete_valid_evidence: int,
    key_nonempty_fields: int,
) -> float | None:
    return _rate(fields_with_complete_valid_evidence, key_nonempty_fields)


def error_precision(tp: int, fp: int) -> float | None:
    tp = _count(tp, "tp")
    fp = _count(fp, "fp")
    return _rate(tp, tp + fp)


def error_recall(tp: int, fn: int) -> float | None:
    tp = _count(tp, "tp")
    fn = _count(fn, "fn")
    return _rate(tp, tp + fn)


def error_f1(precision: float | None, recall: float | None) -> float | None:
    return _f1(precision, recall)


def repair_accuracy(correct_repairs: int, automatic_repairs: int) -> float | None:
    return _rate(correct_repairs, automatic_repairs)


def sdti(
    retrieval_f1_value: float | None,
    faithfulness_value: float | None,
    traceability_value: float | None,
    error_f1_value: float | None,
    repair_accuracy_value: float | None,
) -> float | None:
    values = (
        retrieval_f1_value,
        faithfulness_value,
        traceability_value,
        error_f1_value,
        repair_accuracy_value,
    )
    if any(value is None for value in values):
        return None
    numeric_values = tuple(float(value) for value in values if value is not None)
    if any(value < 0 or value > 1 for value in numeric_values):
        raise ValueError("SDTI components must be between 0 and 1")
    return 100 * prod(numeric_values) ** (1 / 5)
