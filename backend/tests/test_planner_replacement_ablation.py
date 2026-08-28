from __future__ import annotations

import json
from pathlib import Path

from scripts.run_planner_replacement_ablation import (
    build_metadata,
    run_observations,
    safe_run_row,
    write_report,
)


def test_ablation_metadata_keeps_qwen_as_production_and_reviewer(tmp_path: Path) -> None:
    metadata = build_metadata(
        qwen_model="qwen-plus",
        deepseek_model="deepseek-chat",
        benchmark=tmp_path / "gold.jsonl",
        cases=3,
        repeats=3,
        data_mode="plan_only",
        max_sources=3,
        max_records=500,
        max_rounds=2,
    )

    assert metadata["production_provider"] == "qwen"
    assert metadata["review_provider"] == "qwen"
    assert metadata["shared_summary_provider"] == "qwen"
    assert metadata["ablation_provider"] == "deepseek"
    assert metadata["production_path_modified"] is False
    assert metadata["formal_metrics"].startswith("NOT_EVALUATED")
    assert metadata["fixed_conditions"]["max_rounds"] == 2


def test_ablation_observations_are_auditable() -> None:
    observations = run_observations({
        "status": "完成",
        "used_model": True,
        "used_qwen": False,
        "model_provider": "DeepSeek",
        "model_name": "deepseek-chat",
        "tool_calls": [{}, {}],
        "source_items": [{}],
        "candidate_sources": [{}, {}, {}],
        "modeling_dataset": {"row_count": 12},
        "quality_gate_report": {"overall": "REVIEW"},
        "readiness": {"analysis_ready": False},
    })

    assert observations == {
        "status": "完成",
        "used_model": True,
        "used_qwen": False,
        "reported_provider": "DeepSeek",
        "reported_model": "deepseek-chat",
        "tool_calls": 2,
        "source_items": 1,
        "candidate_sources": 3,
        "dataset_rows": 12,
        "quality_gate": "REVIEW",
        "analysis_ready": False,
    }


def test_ablation_output_whitelist_does_not_persist_secrets(tmp_path: Path) -> None:
    metadata = build_metadata(
        qwen_model="qwen-plus",
        deepseek_model="deepseek-chat",
        benchmark=tmp_path / "gold.jsonl",
        cases=1,
        repeats=1,
        data_mode="plan_only",
        max_sources=1,
        max_records=20,
        max_rounds=2,
    )
    row = {
        "case_id": "case-1",
        "difficulty": "medium",
        "repeat": 1,
        "variant": "Qwen 中间智能体（对照组）",
        "provider": "qwen",
        "planner_model": "qwen-plus",
        "status": "FAILED",
        "rank": None,
        "latency_ms": 1.0,
        "judge_scores": {},
        "api_key": "must-not-be-written",
        "raw_task": {"secret": "must-not-be-written"},
    }
    assert "api_key" not in safe_run_row(row)

    write_report(tmp_path, metadata, {"Qwen 中间智能体（对照组）": [row]})
    content = (tmp_path / "planner_replacement_ablation.json").read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["metadata"]["review_provider"] == "qwen"
    assert "must-not-be-written" not in content
