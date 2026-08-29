from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.agent import (
    AgentTaskRequest,
    ClosedLoopRequest,
    ClosedLoopService,
    ResearchAgentService,
)
from backend.app.agent.models import CollectionSearchAction
from backend.app.main import app


QUESTION = "研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系"


def _base_result():
    return ResearchAgentService().run(
        AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
            iterative_collection=False,
        )
    )


def _geo_followup() -> CollectionSearchAction:
    return CollectionSearchAction(
        action_id="follow-up-geo",
        tool_name="geo.search_datasets",
        source_name="NCBI GEO",
        priority=1,
        rationale="补齐结局或必要字段",
        status="待执行",
        strategy_id="geo_series_matrix",
        strategy_label="GEO Series Matrix",
    )


def _with_followup(result, **readiness_updates):
    collection = result.collection_agent
    assert collection is not None
    collection = collection.model_copy(update={"next_actions": [_geo_followup()]})
    readiness = result.readiness.model_copy(update=readiness_updates) if readiness_updates else result.readiness
    return result.model_copy(update={"readiness": readiness, "collection_agent": collection})


def _without_followup(result, **readiness_updates):
    collection = result.collection_agent
    if collection is not None:
        collection = collection.model_copy(update={"next_actions": []})
    readiness = result.readiness.model_copy(update=readiness_updates) if readiness_updates else result.readiness
    return result.model_copy(update={"readiness": readiness, "collection_agent": collection})


def test_closed_loop_uses_diagnosis_to_change_next_request_and_audits_improvement():
    base = _base_result()
    first = _with_followup(
        base,
        requested_variable_coverage_rate=0.2,
        target_match=False,
        target_match_rate=0.0,
    )
    second = _without_followup(
        base,
        requested_variable_coverage_rate=1.0,
        target_match=True,
        target_match_rate=1.0,
    )
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return first if len(calls) == 1 else second

    service = ClosedLoopService(object(), runner=runner)
    response = service.run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
            iterative_collection=False,
        ),
        max_iterations=2,
        min_improvement=0.05,
    ))

    assert response.completed_iterations == 2
    assert response.presentation == "comparison"
    assert response.improved is True
    assert response.display_iterations == [1, 2]
    assert response.iterations[0].diagnoses
    assert response.iterations[0].actions[0].status == "applied"
    assert "闭环修正" in calls[1].question
    assert "NCBI GEO" in calls[1].preferred_sources
    assert calls[1].iterative_collection is True
    assert calls[1].max_sources > calls[0].max_sources
    assert response.iterations[1].improvement is not None
    assert response.iterations[1].improvement.improved is True
    assert response.iterations[1].audit.input_hash != response.iterations[0].audit.input_hash
    assert response.iterations[1].audit.output_hash
    assert any("目标匹配" in item for item in response.improvement_summary)
    assert any("HER2" in item for item in response.iterations[0].audit.safety_constraints)


def test_closed_loop_stops_when_no_legal_followup_remains():
    base = _without_followup(
        _base_result(),
        requested_variable_coverage_rate=1.0,
        target_match=True,
        target_match_rate=1.0,
    )
    if base.collection_agent is not None:
        base = base.model_copy(update={
            "collection_agent": base.collection_agent.model_copy(update={"critical_gaps": [], "next_actions": [], "quality_gate": "PASS"}),
        })
    if base.quality_gate_report is not None:
        base = base.model_copy(update={
            "quality_gate_report": base.quality_gate_report.model_copy(update={"overall": "PASS", "publish_allowed": True, "traceability": 1.0}),
        })
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return base

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
        ),
        max_iterations=3,
        require_two_rounds=False,
        stop_on_no_improvement=True,
    ))

    assert response.completed_iterations == 1
    assert len(calls) == 1
    assert response.presentation == "best_only"
    assert response.display_iterations == [1]
    assert response.improved is False


def test_closed_loop_hides_comparison_when_second_round_does_not_improve():
    base = _with_followup(_base_result())
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return base

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
        ),
        max_iterations=2,
        stop_on_no_improvement=True,
    ))

    assert response.completed_iterations == 2
    assert len(calls) == 2
    assert response.presentation == "best_only"
    assert response.display_iterations == [response.best_iteration]
    assert response.improved is False
    joined = " ".join(response.improvement_summary)
    assert "没有新的合法补法" in joined or "第二轮已" in joined or "仍缺" in joined or "指标未变" in joined
    assert all(card.label != "progress score" for card in response.highlight_cards)
    assert "必要字段覆盖" not in [card.label for card in response.highlight_cards]
    assert not any(card.value in {"0.0%", "0%"} for card in response.highlight_cards)


def test_closed_loop_runs_second_round_after_first_passes_quality_gate():
    base = _base_result()
    passing = base.model_copy(update={
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 1.0,
            "target_match": True,
            "target_match_rate": 1.0,
        }),
        "collection_agent": base.collection_agent.model_copy(update={"critical_gaps": [], "quality_gate": "PASS", "next_actions": []}) if base.collection_agent else None,
        "quality_gate_report": base.quality_gate_report.model_copy(update={
            "overall": "PASS",
            "publish_allowed": True,
            "traceability": 1.0,
        }) if base.quality_gate_report else None,
    })
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return passing

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
        ),
        max_iterations=2,
        require_two_rounds=True,
    ))

    assert response.completed_iterations == 2
    assert len(calls) == 2
    assert response.iterations[0].actions[0].action_type == "supplemental_verification"
    assert response.iterations[0].actions[0].status == "applied"
    assert "闭环修正" in calls[1].question
    assert response.iterations[1].improvement is not None
    assert response.presentation == "best_only"
    assert response.display_iterations == [response.best_iteration]
    assert response.improved is False


def test_closed_loop_returns_first_result_when_second_round_regresses():
    base = _base_result()
    first = _with_followup(
        base,
        requested_variable_coverage_rate=0.50,
        target_match=True,
        target_match_rate=0.787,
    )
    second = _without_followup(
        base,
        requested_variable_coverage_rate=0.80,
        target_match=False,
        target_match_rate=0.0,
    )
    calls = []

    def runner(request, **_kwargs):
        calls.append(request)
        return first if len(calls) == 1 else second

    response = ClosedLoopService(object(), runner=runner).run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(
            question=QUESTION,
            use_qwen=False,
            data_mode="plan_only",
            max_sources=2,
            max_records=100,
        ),
        max_iterations=2,
    ))

    assert response.completed_iterations == 2
    assert response.improved is False
    assert response.presentation == "best_only"
    assert response.best_iteration == 1
    assert response.display_iterations == [1]
    assert response.final_result is not None
    assert response.final_result.readiness.target_match_rate == 0.787


def test_closed_loop_api_returns_round_comparison():
    client = TestClient(app)
    response = client.post(
        "/api/v2/agent/closed-loop",
        json={
            "initial_request": {
                "question": QUESTION,
                "use_qwen": False,
                "data_mode": "plan_only",
                "max_sources": 2,
                "max_records": 100,
                "iterative_collection": False,
            },
            "max_iterations": 2,
            "stop_on_no_improvement": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["completed_iterations"] >= 1
    assert payload["presentation"] in {"best_only", "comparison"}
    assert payload["display_iterations"]
    assert payload["user_notice"]
    assert payload["iterations"][0]["audit"]["input_hash"]
    assert payload["iterations"][0]["result"]["task_id"].startswith(payload["loop_id"])
    assert "progress_score" in payload["audit_notice"]
    fetched = client.get(f"/api/v2/agent/closed-loop/{payload['loop_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["loop_id"] == payload["loop_id"]
    if payload["presentation"] == "best_only":
        assert payload["display_iterations"] == [payload["best_iteration"]]
        assert (
            "没有新的合法补法" in payload["user_notice"]
            or payload["completed_iterations"] == 1
            or "第二轮已" in payload["user_notice"]
            or "仍缺" in payload["user_notice"]
        )
