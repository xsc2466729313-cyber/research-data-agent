from __future__ import annotations

from backend.app.v30.models import CopilotTurnRequest, RouteKind
from backend.app.v30.runtime import V30Runtime


def test_resistance_turn_asks_focus_and_does_not_retrieve() -> None:
    runtime = V30Runtime()
    result = runtime.turn(CopilotTurnRequest(message="我想研究HER2阳性乳腺癌耐药机制"))
    assert result.route.route is RouteKind.CLARIFY
    assert result.understood_goal is not None
    assert result.understood_goal.object == "HER2阳性乳腺癌"
    assert result.understood_goal.target is not None
    assert "耐药" in result.understood_goal.target
    categories = {item.category for item in result.suggested_data_needs}
    assert {"clinical_outcomes", "gene_expression", "mutations", "drug_response"} <= categories
    assert all(item.retrieval_status == "not_retrieved" for item in result.suggested_data_needs)
    assert any("机制" in item.question and "疗效预测" in item.question for item in result.clarifying_questions)
    assert result.ready_for_planner is False
    assert "尚未检索" in result.user_visible_reply
    assert "GSE" not in result.user_visible_reply
    assert "已找到" not in result.user_visible_reply
    assert result.memory.goal is not None
    assert result.memory.goal.object == "HER2阳性乳腺癌"


def test_suggestions_never_claim_dataset_hits() -> None:
    runtime = V30Runtime()
    result = runtime.turn(CopilotTurnRequest(message="我想研究HER2阳性乳腺癌耐药机制"))
    blob = " ".join(
        [result.user_visible_reply]
        + [item.description for item in result.suggested_data_needs]
        + [item.category for item in result.suggested_data_needs]
    )
    assert "GSE" not in blob
    assert "已找到" not in blob
    assert "not_retrieved" in {item.retrieval_status for item in result.suggested_data_needs}


def test_greeting_does_not_write_goal() -> None:
    runtime = V30Runtime()
    result = runtime.turn(CopilotTurnRequest(message="你好"))
    assert result.route.route is RouteKind.CHAT
    assert result.blocked_reason
    assert result.ready_for_planner is False
    assert result.understood_goal is None
    assert result.memory.goal is None
    assert result.memory.clarifications == []


def test_second_turn_records_prediction_focus() -> None:
    runtime = V30Runtime()
    first = runtime.turn(CopilotTurnRequest(message="我想研究HER2阳性乳腺癌耐药机制"))
    second = runtime.turn(
        CopilotTurnRequest(session_id=first.session_id, message="疗效预测")
    )
    assert second.session_id == first.session_id
    assert second.memory.goal is not None
    assert second.memory.goal.object == "HER2阳性乳腺癌"
    assert any(item.answer == "疗效预测" for item in second.memory.clarifications)
    assert second.ready_for_planner is True
    assert second.clarifying_questions == []
