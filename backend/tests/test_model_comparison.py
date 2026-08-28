from __future__ import annotations

import json
from pathlib import Path

from scripts.run_model_comparison import audit_result, load_cases, summarize, write_outputs


def test_model_comparison_loads_jsonl_without_secret_fields(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps({"case_id": "a", "question": "研究乳腺癌治疗响应"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert load_cases(path) == [{"case_id": "a", "question": "研究乳腺癌治疗响应"}]


def test_model_comparison_rejects_provider_mismatch() -> None:
    valid, error = audit_result({"used_model": True, "model_provider": "千问", "model_name": "qwen-plus"}, "deepseek")
    assert valid is False
    assert error == "provider_mismatch:千问"


def test_model_comparison_summary_marks_formal_metrics_unavailable() -> None:
    rows = [
        {"provider": "qwen", "status": "完成", "audit_valid": True, "latency_ms": 10, "tool_calls": 2, "source_items": 1, "dataset_rows": 5, "quality_gate": "REVIEW"},
        {"provider": "deepseek", "status": "FAILED", "audit_valid": False, "latency_ms": 20, "tool_calls": 0, "source_items": 0, "dataset_rows": 0, "quality_gate": "UNKNOWN"},
    ]
    summary = summarize(rows)
    assert summary["qwen"]["completed"] == 1
    assert summary["deepseek"]["failure_rate"] == 1.0
    assert summary["qwen"]["formal_quality_metrics"].startswith("NOT_EVALUATED")


def test_model_comparison_outputs_do_not_include_api_key(tmp_path: Path) -> None:
    metadata = {
        "question_set": "questions.jsonl", "cases": 1, "providers_run": ["qwen"], "repeats": 1,
        "data_mode": "plan_only", "max_sources": 1, "max_records": 10,
        "iterative_collection": True, "max_rounds": 2,
        "summary": {"qwen": {"runs": 1, "completed": 0, "failure_rate": 1.0, "latency_ms_mean": None, "tool_calls_mean": None, "source_items_mean": None, "dataset_rows_mean": None}},
    }
    rows = [{"case_id": "a", "repeat": 1, "provider": "qwen", "status": "FAILED", "api_key": "must-not-be-written"}]
    write_outputs(tmp_path, metadata, rows)
    content = (tmp_path / "comparison.json").read_text(encoding="utf-8")
    assert "api_key" not in content
    assert "must-not-be-written" not in content
