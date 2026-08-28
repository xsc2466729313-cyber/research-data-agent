from __future__ import annotations

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.formulation_agent import ResearchFormulationAgent
from backend.app.research_planning.models import QuestionCandidate, ResearchTopic

from .models import StructuredExtractionV2


class QuestionGeneratorV2:
    """Generate candidate questions while preserving the legacy baseline."""

    def __init__(self, formulation: ResearchFormulationAgent | None = None) -> None:
        self.formulation = formulation or ResearchFormulationAgent()

    def generate(
        self,
        topic: ResearchTopic,
        papers: list[PaperRecord],
        extraction: StructuredExtractionV2 | None = None,
    ) -> tuple[list[QuestionCandidate], str]:
        candidates = self.formulation.formulate(topic, papers)
        source = "EVIDENCE_AGENT" if papers and any(item.literature_evidence for item in candidates) else "GENERIC_FALLBACK"
        if extraction and extraction.research_type != "association":
            candidates = [item.model_copy(update={"research_type": extraction.research_type}) for item in candidates]
        return candidates, source
