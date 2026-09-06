from __future__ import annotations

from backend.app.v30.models import MemorySnapshot


def is_ready_for_planner(memory: MemorySnapshot) -> bool:
    """Gate: never guess a research goal. Ready only when Copilot already closed clarifications."""
    goal = memory.goal
    if goal is None or not goal.object or not goal.target:
        return False
    return all(item.answer for item in memory.clarifications)


def compile_topic(memory: MemorySnapshot) -> str:
    """Turn session memory into an existing-planning topic string. Does not invent schema fields."""
    goal = memory.goal
    chunks: list[str] = []
    if goal and goal.object:
        chunks.append(goal.object)
    if goal and goal.target:
        chunks.append(goal.target)
    answers = [item.answer.strip() for item in memory.clarifications if item.answer and item.answer.strip()]
    if answers:
        chunks.append("研究重点为" + "、".join(answers))
    if memory.constraints:
        chunks.append("约束：" + "；".join(memory.constraints))
    if chunks:
        return "，".join(chunks)
    if goal and goal.raw_text:
        return goal.raw_text.strip()
    return ""
