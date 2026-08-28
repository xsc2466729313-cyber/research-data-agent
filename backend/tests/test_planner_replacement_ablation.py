from __future__ import annotations

import json
from pathlib import Path

import httpx

from scripts.run_planner_replacement_ablation import (
    build_metadata,
    run_observations,
    safe_run_row,
    write_report,
)
from backend.app.agent.evaluator import QwenJudge


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


def test_qwen_judge_accepts_object_wrapped_numeric_fields() -> None:
    normalized = QwenJudge._normalize({
        "faithfulness": {"score": 4, "reason": "有来源"},
        "relevance": 5,
        "completeness": {"value": 3},
        "retrieval_quality": {"score": 4},
        "overall": {"score": 4},
        "claim_support_rate": {"rate": 0.75},
        "missing_evidence": [],
        "unsupported_claims": [],
    })

    assert normalized["overall"] == 4
    assert normalized["claim_support_rate"] == 0.75
    assert normalized["relevance"]["score"] == 5


def test_qwen_judge_compacts_context_and_disables_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        context = json.loads(payload["messages"][1]["content"])
        assert payload["model"] == "qwen3.8-max"
        assert payload["enable_thinking"] is False
        assert payload["max_tokens"] == 1200
        assert len(context["source_items"]) == 30
        assert "url" not in context["source_items"][0]
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "faithfulness": {"score": 4, "reason": "有来源"},
                            "relevance": {"score": 4, "reason": "相关"},
                            "completeness": {"score": 3, "reason": "仍有缺口"},
                            "retrieval_quality": {"score": 4, "reason": "排序合理"},
                            "overall": 4,
                            "claim_support_rate": 0.8,
                            "missing_evidence": [],
                            "unsupported_claims": [],
                        }, ensure_ascii=False),
                    }
                }]
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    judge = QwenJudge("test-api-key", model="qwen3.8-max", client=client)
    case = type("Case", (), {"question": "测试问题"})()
    try:
        result = judge.evaluate(
            case,
            {
                "source_items": [
                    {
                        "source_id": f"source-{index}",
                        "source_name": "来源",
                        "source_type": "dataset",
                        "status": "ok",
                        "url": "https://example.invalid",
                    }
                    for index in range(40)
                ],
                "modeling_dataset": {"columns": []},
            },
        )
    finally:
        client.close()

    assert result["overall"] == 4
