from __future__ import annotations

from types import SimpleNamespace

from backend.app.evaluation.toolkit_run import run_toolkit_evaluation


def test_toolkit_run_without_task_stays_pending() -> None:
    payload = run_toolkit_evaluation(None)
    assert payload["available"] is False
    assert payload["status"] == "待运行"
    assert {item.key for item in payload["metrics"]} == {
        "cleaning_retention",
        "retrieval_ndcg@10",
        "integration_macro_f1",
        "task_fitness",
        "quality_gate",
    }
    assert all(item.value is None for item in payload["metrics"])


def test_toolkit_run_computes_from_current_task() -> None:
    task = SimpleNamespace(
        task_id="task-toolkit",
        modeling_dataset=SimpleNamespace(
            rows=[{"patient_id": "P1", "her2_status": "Equivocal", "er_status": "NA"}],
            columns=[],
        ),
        readiness=SimpleNamespace(cleaned_value_count=2),
        study_design=SimpleNamespace(
            required_variables=[
                SimpleNamespace(variable_id="her2_status", required=True, available=True, matched_fields=["her2_status"]),
                SimpleNamespace(variable_id="pik3ca", required=True, available=False, matched_fields=[]),
                SimpleNamespace(variable_id="age", required=False, available=True, matched_fields=["age"]),
            ]
        ),
        data_alignment=SimpleNamespace(patient_count=10, unresolved_identity_row_count=1, duplicate_identity_count=0),
        quality_gate_report=SimpleNamespace(overall="REVIEW"),
        competition_report=SimpleNamespace(
            rag_matches=[
                SimpleNamespace(match_score=0.9, selected=True),
                SimpleNamespace(match_score=0.2, selected=False),
            ],
            unified_evaluation=SimpleNamespace(
                task_adaptive_fitness=SimpleNamespace(
                    fitness_score=72.0,
                    dimensions=[
                        SimpleNamespace(value=0.8),
                        SimpleNamespace(value=0.7),
                        SimpleNamespace(value=0.9),
                        SimpleNamespace(value=0.6),
                    ],
                )
            ),
        ),
    )
    payload = run_toolkit_evaluation(task)
    by_key = {item.key: item for item in payload["metrics"]}
    assert payload["available"] is True
    assert by_key["cleaning_retention"].value is not None
    assert 0.0 <= by_key["cleaning_retention"].value <= 1.0
    assert by_key["retrieval_ndcg@10"].value == 1.0
    assert by_key["integration_macro_f1"].value is not None
    assert by_key["task_fitness"].unit == "score"
    assert by_key["quality_gate"].value == 0.5
    assert payload["quality_gate"] == "REVIEW"
    assert "Hospital" in by_key["cleaning_retention"].reason
    assert by_key["cleaning_retention"].headline is not None
    assert "Valentine" in by_key["integration_macro_f1"].reason or "不是行业标准" in by_key["integration_macro_f1"].reason


def test_toolkit_cleaning_does_not_score_empty_or_missing_only_tables() -> None:
    empty = run_toolkit_evaluation(SimpleNamespace(
        task_id="empty-table",
        modeling_dataset=SimpleNamespace(rows=[], columns=[]),
        readiness=SimpleNamespace(cleaned_value_count=0),
        study_design=None,
        data_alignment=None,
        quality_gate_report=None,
        competition_report=None,
    ))
    missing_only = run_toolkit_evaluation(SimpleNamespace(
        task_id="missing-table",
        modeling_dataset=SimpleNamespace(rows=[{"patient_id": "", "her2_status": "—", "source_id": "s1"}], columns=[]),
        readiness=SimpleNamespace(cleaned_value_count=0),
        study_design=None,
        data_alignment=None,
        quality_gate_report=None,
        competition_report=None,
    ))
    empty_metric = next(item for item in empty["metrics"] if item.key == "cleaning_retention")
    missing_metric = next(item for item in missing_only["metrics"] if item.key == "cleaning_retention")
    assert empty_metric.value is None
    assert missing_metric.value is None
    assert "空表" in empty_metric.reason or "没有宽表" in empty_metric.reason
    assert "不能把空表" in missing_metric.reason or "已填写" in missing_metric.reason


def test_toolkit_cleaning_headline_is_not_a_fake_perfect_coverage_score() -> None:
    payload = run_toolkit_evaluation(SimpleNamespace(
        task_id="clean-cells",
        modeling_dataset=SimpleNamespace(rows=[{"patient_id": "P1", "her2_status": "Positive"}], columns=[]),
        readiness=SimpleNamespace(cleaned_value_count=0),
        study_design=None,
        data_alignment=None,
        quality_gate_report=None,
        competition_report=None,
    ))
    cleaning = next(item for item in payload["metrics"] if item.key == "cleaning_retention")
    assert cleaning.value == 1.0
    assert cleaning.headline == "未发现错误清洗"
    assert "不是字段覆盖" in (cleaning.plain_meaning or "") or "必要字段" in (cleaning.plain_meaning or "")
