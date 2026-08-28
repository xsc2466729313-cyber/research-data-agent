from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.models import FieldRequirement, MetricRequirement, QuestionCandidate, ResearchTopic
from backend.app.research_planning.research_contract import ResearchContractBuilder


class ContractBuilderV2(ResearchContractBuilder):
    """V2 named facade; validation remains delegated to the proven builder."""

    def build_sections(
        self,
        topic: ResearchTopic,
        candidate: QuestionCandidate,
        papers: list[PaperRecord],
    ) -> tuple[list[FieldRequirement], list[FieldRequirement], list[FieldRequirement], list[MetricRequirement]]:
        required, recommended, optional = self.field_planner.plan(candidate, papers, topic)
        return required, recommended, optional, self.metric_planner.plan(candidate, papers)


ResearchContractBuilderV2 = ContractBuilderV2
