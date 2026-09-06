from __future__ import annotations

from backend.app.v30.memory.store import InMemorySessionStore, SessionNotFoundError
from backend.app.v30.models import ClarificationRecord, MemoryPatch, MemorySnapshot, ResearchGoal

__all__ = ["MemoryService", "SessionNotFoundError"]


class MemoryService:
    """Minimal research-session memory: goal, clarifications, constraints only."""

    def __init__(self, store: InMemorySessionStore | None = None) -> None:
        self._store = store or InMemorySessionStore()

    def create_session(self, session_id: str | None = None) -> MemorySnapshot:
        return self._store.create(session_id)

    def get(self, session_id: str) -> MemorySnapshot:
        return self._store.get(session_id)

    def get_or_create(self, session_id: str | None) -> MemorySnapshot:
        if not session_id:
            return self.create_session()
        try:
            return self.get(session_id)
        except SessionNotFoundError:
            return self.create_session(session_id)

    def apply_patch(self, session_id: str, patch: MemoryPatch) -> MemorySnapshot:
        current = self.get(session_id)
        next_goal = current.goal if patch.goal is None else patch.goal
        next_clarifications = current.clarifications if patch.clarifications is None else patch.clarifications
        next_constraints = current.constraints if patch.constraints is None else patch.constraints
        return self._store.put(
            MemorySnapshot(
                session_id=session_id,
                goal=next_goal,
                clarifications=list(next_clarifications),
                constraints=list(next_constraints),
            )
        )

    def replace_goal(self, session_id: str, goal: ResearchGoal | None) -> MemorySnapshot:
        return self.apply_patch(session_id, MemoryPatch(goal=goal))

    def upsert_clarification(self, session_id: str, record: ClarificationRecord) -> MemorySnapshot:
        current = self.get(session_id)
        updated = [item.model_copy(deep=True) for item in current.clarifications]
        for index, item in enumerate(updated):
            if item.question_id == record.question_id:
                updated[index] = record
                break
        else:
            updated.append(record)
        return self.apply_patch(session_id, MemoryPatch(clarifications=updated))

    def add_constraints(self, session_id: str, constraints: list[str]) -> MemorySnapshot:
        current = self.get(session_id)
        merged = list(current.constraints)
        for item in constraints:
            value = item.strip()
            if value and value not in merged:
                merged.append(value)
        return self.apply_patch(session_id, MemoryPatch(constraints=merged))
