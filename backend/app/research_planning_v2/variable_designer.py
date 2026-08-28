from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.field_planner import FieldPlanningAgent
from backend.app.research_planning.models import FieldRequirement, QuestionCandidate, ResearchTopic


class VariableDesignerV2:
    """Design variables through the existing evidence-aware field planner."""

    def __init__(self, planner: FieldPlanningAgent | None = None) -> None:
        self.planner = planner or FieldPlanningAgent()

    def design(
        self,
        candidate: QuestionCandidate,
        papers: list[PaperRecord],
        topic: ResearchTopic,
    ) -> tuple[list[FieldRequirement], list[FieldRequirement], list[FieldRequirement]]:
        return self.planner.plan(candidate, papers, topic)
