from __future__ import annotations

from backend.app.agent.models import ParsedResearchQuestion, StudyDesignReport
from backend.app.models import ResearchSpec


class ResearchQuestionParser:
    """Turn a research question and ResearchSpec into a PICO-style task card."""

    def parse(
        self,
        question: str,
        spec: ResearchSpec,
        design: StudyDesignReport | None = None,
    ) -> ParsedResearchQuestion:
        del question
        required_variables = list(spec.required_data_types)
        if design is not None:
            required_variables = [
                variable.variable_id
                for variable in design.required_variables
                if variable.required
            ] or required_variables
        return ParsedResearchQuestion(
            disease=spec.disease,
            population=design.population if design is not None else self._population(spec),
            exposure=design.exposure if design is not None else self._exposure(spec),
            outcome=design.outcome if design is not None else self._outcome(spec),
            required_variables=required_variables,
            research_type=design.research_type if design is not None else None,
        )

    @staticmethod
    def _population(spec: ResearchSpec) -> str:
        subtype = f"、{spec.subtype}" if spec.subtype else ""
        return f"{spec.disease}{subtype}患者/样本"

    @staticmethod
    def _exposure(spec: ResearchSpec) -> str:
        pieces: list[str] = []
        if spec.genes:
            pieces.append("、".join(spec.genes) + " 突变状态")
        if spec.drugs:
            pieces.append("、".join(spec.drugs) + " 治疗")
        return "；".join(pieces) or "待从科研问题中进一步冻结"

    @staticmethod
    def _outcome(spec: ResearchSpec) -> str:
        return "、".join(spec.outcomes) or "待指定"
