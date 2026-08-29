from __future__ import annotations

from scripts.run_github_competitor_benchmark import (
    _metrics,
    _paired_macros,
    _project_fmt,
    _winner,
    build_report,
)


def test_binary_metrics_counts_false_positive_and_false_negative() -> None:
    result = _metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_winner_does_not_claim_unmeasured_result() -> None:
    assert _winner(0.8, None) == "暂不能比较"


def test_project_values_are_bold() -> None:
    assert _project_fmt(0.81234) == "**0.8123**"


def test_paired_macros_use_only_common_evaluated_datasets() -> None:
    rows = [
        {"status": "OK", "project": 1.0, "github": 0.5},
        {"status": "OK", "project": 0.0, "github": None},
    ]
    assert _paired_macros(rows, "project", "github") == (1.0, 0.5, 1)


def test_report_explains_that_module_scores_cannot_be_added() -> None:
    module = {"project_macro": 0.8, "github_macro": 0.7, "rows": []}
    payload = {
        "created_at": "2026-08-30T00:00:00+00:00",
        "project_revision": "abc",
        "environment": {"python": "3.14"},
        "repositories": {
            "deepmatcher": {"url": "https://example.test/deepmatcher", "status": "NOT_EVALUATED", "reason": "incompatible"},
            "ditto": {"url": "https://example.test/ditto", "status": "NOT_EVALUATED", "reason": "incompatible"},
            "holoclean": {"url": "https://example.test/holoclean", "status": "NOT_EVALUATED", "reason": "service required"},
        },
        "modules": {
            "retrieval": module,
            "schema_matching": module,
            "entity_matching": module,
            "cleaning": module,
        },
    }
    report = build_report(payload)
    assert "四个分数不能相加" in report
    assert "NOT_EVALUATED" in report
    assert "**0.8000**" in report
