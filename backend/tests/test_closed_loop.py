from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.agent import (
    AgentTaskRequest,
    ClosedLoopRequest,
    ClosedLoopService,
    ResearchAgentService,
)
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


def test_closed_loop_uses_diagnosis_to_change_next_request_and_audits_improvement():
    base = _base_result()
    first = base.model_copy(update={
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 0.2,
            "target_match": False,
            "target_match_rate": 0.0,
        }),
    })
    second = base.model_copy(update={
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 1.0,
            "target_match": True,
            "target_match_rate": 1.0,
        }),
    })
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
    assert response.iterations[0].diagnoses
    assert response.iterations[0].actions[0].status == "applied"
    assert "闭环修正" in calls[1].question
    assert calls[1].iterative_collection is True
    assert response.iterations[1].improvement is not None
    assert response.iterations[1].improvement.improved is True
    assert response.iterations[1].audit.input_hash != response.iterations[0].audit.input_hash
    assert response.iterations[1].audit.output_hash
    assert any("target match" in item for item in response.improvement_summary)
    assert any("HER2" in item for item in response.iterations[0].audit.safety_constraints)


def test_closed_loop_stops_when_second_round_does_not_improve():
    base = _base_result()
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
        stop_on_no_improvement=True,
    ))

    assert response.completed_iterations == 2
    assert "未达到最小可验证改进" in response.stop_reason
    assert len(calls) == 2


def test_closed_loop_runs_second_round_after_first_passes_quality_gate():
    base = _base_result()
    passing = base.model_copy(update={
        "readiness": base.readiness.model_copy(update={
            "requested_variable_coverage_rate": 1.0,
            "target_match": True,
            "target_match_rate": 1.0,
        }),
        "collection_agent": base.collection_agent.model_copy(update={"critical_gaps": [], "quality_gate": "PASS"}) if base.collection_agent else None,
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
    assert payload["iterations"][0]["audit"]["input_hash"]
    assert payload["iterations"][0]["result"]["task_id"].startswith(payload["loop_id"])
    assert "progress_score" in payload["audit_notice"]
    fetched = client.get(f"/api/v2/agent/closed-loop/{payload['loop_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["loop_id"] == payload["loop_id"]
