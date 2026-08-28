from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.evaluation.public_schema import (
    evaluate_schema_matches,
    load_schema_task,
    predict_schema_matches,
    prepare_schema_dataset,
)


def test_exact_and_token_schema_methods_are_label_independent() -> None:
    source = ["patient_id", "total_changes", "unrelated"]
    target = ["patient_id", "total_schedule_changes", "other"]
    assert predict_schema_matches(source, target, "exact_normalized_name") == {("patient_id", "patient_id")}
    assert predict_schema_matches(source, target, "token_jaccard") == {
        ("patient_id", "patient_id"),
        ("total_changes", "total_schedule_changes"),
    }


def test_schema_metrics_count_false_positives_and_negatives() -> None:
    source = ["patient_id", "city"]
    target = ["patient_id", "country"]
    gold = {("patient_id", "patient_id"), ("city", "country")}
    result = evaluate_schema_matches(source, target, gold, "exact_normalized_name")
    assert result.true_positive == 1
    assert result.false_positive == 0
    assert result.false_negative == 1
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(0.5)
    assert result.f1 == pytest.approx(2 / 3)


def test_value_profile_uses_value_overlap_for_renamed_columns() -> None:
    source = ["source_code", "city"]
    target = ["target_code", "town"]
    source_samples = {"source_code": ["A", "B", "C", "D"], "city": ["Paris", "Berlin"]}
    target_samples = {"target_code": ["A", "B", "C", "D"], "town": ["Paris", "Berlin"]}
    predicted = predict_schema_matches(
        source,
        target,
        "project_schema_profile_v2",
        source_samples=source_samples,
        target_samples=target_samples,
    )
    assert ("source_code", "target_code") in predicted


def test_load_schema_task_uses_matches_not_overlap_cols(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    (task / "source_table.csv").write_text("location,district\nA,1\n", encoding="utf-8")
    (task / "target_table.csv").write_text("siteaddress,district,longitude\nA,1,-73.9\n", encoding="utf-8")
    (task / "ground_truth.json").write_text(json.dumps({
        "meta": {"overlap_cols": ["district"]},
        "matches": [{"source_column": "location", "target_column": "siteaddress"}],
    }), encoding="utf-8")
    source, target, gold, *_ = load_schema_task(task)
    assert source == ["location", "district"]
    assert target == ["siteaddress", "district", "longitude"]
    assert gold == {("location", "siteaddress")}


def test_prepare_schema_dataset_requires_download_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="--download"):
        prepare_schema_dataset("valentine_education_covid_meals", tmp_path, download=False)


def test_v3_schema_method_is_label_independent_and_uses_value_context() -> None:
    source = ["age_at_diagnosis", "her2"]
    target = ["patient_age", "her2_status"]
    predicted = predict_schema_matches(
        source,
        target,
        "project_schema_v3",
        source_samples={"age_at_diagnosis": [60, 61], "her2": ["Positive"]},
        target_samples={"patient_age": [60, 61], "her2_status": ["Positive"]},
    )
    assert ("age_at_diagnosis", "patient_age") in predicted
    assert ("her2", "her2_status") in predicted
