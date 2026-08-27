from __future__ import annotations

from dataclasses import dataclass

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.evidence import evidence_references
from backend.app.research_planning.field_planner import FieldPlanningAgent
from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.metric_planner import MetricPlanningAgent
from backend.app.research_planning.models import QuestionCandidate, ResearchTopic


@dataclass(frozen=True)
class ResearchPlanDraft:
    candidates: list[QuestionCandidate]
    evidence_count: int
    required_field_ids: dict[str, list[str]]
    note: str


class ResearchAgent:
    """One product-level planning agent composed from testable planning specialists."""

    VERSION = "research-agent-v1"

    def __init__(self, *, formulation: ResearchFormulationAgent | None = None, fields: FieldPlanningAgent | None = None, metrics: MetricPlanningAgent | None = None) -> None:
        self.formulation = formulation or ResearchFormulationAgent()
        self.fields = fields or FieldPlanningAgent()
        self.metrics = metrics or MetricPlanningAgent()

    def plan(self, topic: ResearchTopic, papers: list[PaperRecord]) -> ResearchPlanDraft:
        candidates = self.formulation.formulate(topic, papers)
        required: dict[str, list[str]] = {}
        for candidate in candidates:
            required[candidate.candidate_id] = [item.field_id for item in self.fields.plan(candidate, papers, topic)[0]]
        evidence_count = len(evidence_references(papers, terms=[topic.topic], evidence_type="research_agent_context", limit=20))
        note = "候选问题由论文证据、字段需求和研究设计共同生成；无证据时仅作为待核验草案。"
        return ResearchPlanDraft(candidates, evidence_count, required, note)
