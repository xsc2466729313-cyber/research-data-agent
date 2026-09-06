from __future__ import annotations

from backend.app.v30.copilot.service import ResearchCopilot
from backend.app.v30.memory.service import MemoryService, SessionNotFoundError
from backend.app.v30.models import (
    CopilotTurnRequest,
    CopilotTurnResponse,
    MemoryPatch,
    MemorySnapshot,
    PlanRequest,
    PlanResponse,
    RouteDecision,
    RouteRequest,
)
from backend.app.v30.planner.service import PlannerFacade
from backend.app.v30.router.service import RouterAgent


class V30Runtime:
    """Route → Copilot → Memory → optional Planner facade. Does not call adapters or the medical agent service."""

    def __init__(
        self,
        *,
        router: RouterAgent | None = None,
        copilot: ResearchCopilot | None = None,
        memory: MemoryService | None = None,
    ) -> None:
        self.router = router or RouterAgent()
        self.copilot = copilot or ResearchCopilot()
        self.memory = memory or MemoryService()

    def create_session(self) -> MemorySnapshot:
        return self.memory.create_session()

    def get_memory(self, session_id: str) -> MemorySnapshot:
        return self.memory.get(session_id)

    def route(self, request: RouteRequest) -> RouteDecision:
        memory = None
        if request.session_id:
            try:
                memory = self.memory.get(request.session_id)
            except SessionNotFoundError:
                memory = None
        return self.router.decide(request.message, memory)

    def turn(self, request: CopilotTurnRequest) -> CopilotTurnResponse:
        snapshot = self.memory.get_or_create(request.session_id)
        decision = self.router.decide(request.message, snapshot)
        draft = self.copilot.draft(request.message, decision, snapshot)
        if draft.write_goal:
            snapshot = self.memory.apply_patch(
                snapshot.session_id,
                MemoryPatch(goal=draft.goal_to_store, clarifications=draft.clarifications_to_store),
            )
        if draft.constraints_to_add:
            snapshot = self.memory.add_constraints(snapshot.session_id, draft.constraints_to_add)
        snapshot = self.memory.get(snapshot.session_id)
        return CopilotTurnResponse(
            session_id=snapshot.session_id,
            route=decision,
            understood_goal=draft.understood_goal,
            suggested_data_needs=draft.suggested_data_needs,
            clarifying_questions=draft.clarifying_questions,
            ready_for_planner=draft.ready_for_planner,
            user_visible_reply=draft.user_visible_reply,
            blocked_reason=draft.blocked_reason,
            memory=snapshot,
        )

    def plan(self, request: PlanRequest, *, planner: PlannerFacade) -> PlanResponse:
        memory = self.memory.get(request.session_id)
        return planner.plan(
            session_id=request.session_id,
            memory=memory,
            question_override=request.question_override,
        )
