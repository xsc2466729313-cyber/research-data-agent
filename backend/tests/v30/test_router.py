from __future__ import annotations

from backend.app.v30.models import ClarificationRecord, MemorySnapshot, ResearchGoal, RouteKind
from backend.app.v30.router.service import RouterAgent


def test_greeting_routes_to_chat() -> None:
    decision = RouterAgent().decide("你好")
    assert decision.route is RouteKind.CHAT
    assert decision.fallback is True


def test_her2_definition_is_concept_qa() -> None:
    decision = RouterAgent().decide("什么是HER2")
    assert decision.route is RouteKind.CONCEPT_QA
    assert decision.domain == "oncology"


def test_redshift_definition_is_not_oncology() -> None:
    decision = RouterAgent().decide("什么是红移")
    assert decision.route is RouteKind.CONCEPT_QA
    assert decision.domain == "astronomy"
    assert decision.domain != "oncology"


def test_resistance_study_needs_clarify() -> None:
    decision = RouterAgent().decide("我想研究HER2阳性乳腺癌耐药机制")
    assert decision.route is RouteKind.CLARIFY
    assert decision.domain == "oncology"


def test_empty_message_does_not_enter_clarify() -> None:
    decision = RouterAgent().decide("")
    assert decision.route is RouteKind.CHAT
    assert decision.route is not RouteKind.CLARIFY
    assert decision.reason == "empty_message"


def test_plan_route_only_after_clarifications() -> None:
    router = RouterAgent()
    empty = MemorySnapshot(session_id="s1")
    assert router.decide("请生成方案", empty).route is RouteKind.CHAT
    ready = MemorySnapshot(
        session_id="s1",
        goal=ResearchGoal(object="HER2阳性乳腺癌", target="耐药机制分析", domain="oncology"),
        clarifications=[
            ClarificationRecord(question_id="research_focus", question="q", answer="疗效预测"),
        ],
    )
    assert router.decide("请生成方案", ready).route is RouteKind.PLAN
