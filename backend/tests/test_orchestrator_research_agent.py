from backend.app.agent.orchestrator import ResearchOrchestrator


def test_orchestrator_routes_missing_question_to_planning():
    decision = ResearchOrchestrator().decide(question="")
    assert decision.next_stage == "research_planning"


def test_orchestrator_never_bypasses_quality_gate():
    decision = ResearchOrchestrator().decide(question="q", quality_gate="FAIL")
    assert decision.next_stage == "quality_review"
    assert "quality_agent" in decision.required_tools
