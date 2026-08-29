from __future__ import annotations

from datetime import datetime, timezone

from backend.app.contracts.models import (
    ContractFieldRequirement,
    FrozenResearchContract,
    PopulationSpec,
    VariableSpec,
)
from backend.app.research_planning.models import QuestionCandidate, ResearchContract, ResearchTopic


class FrozenContractBuilder:
    """Project the planning-layer contract into the production FrozenResearchContract."""

    def from_planning(
        self,
        planning: ResearchContract,
        *,
        topic: ResearchTopic | None = None,
        candidate: QuestionCandidate | None = None,
    ) -> FrozenResearchContract:
        generation = getattr(candidate, "generation_source", None) or (
            "EVIDENCE_AGENT" if planning.literature_evidence else "GENERIC_FALLBACK"
        )
        granularity = self._granularity(planning, topic)
        response_domain = "clinical"
        if "cell" in (planning.research_question + planning.population).casefold():
            response_domain = "preclinical"
        return FrozenResearchContract(
            contract_id=planning.contract_id,
            topic_id=planning.topic_id,
            candidate_id=planning.candidate_id,
            research_goal=planning.research_question,
            population=PopulationSpec(
                disease=(topic.disease if topic and topic.disease else "breast cancer"),
                subtype=self._subtype(planning),
                treatment_context=planning.population,
            ),
            exposure=VariableSpec(name=planning.exposure, canonical_field=self._canonical(planning.required_fields, "exposure")),
            outcome=VariableSpec(name=planning.outcome, canonical_field=self._canonical(planning.required_fields, "outcome")),
            required_fields=[self._field(item) for item in planning.required_fields],
            recommended_fields=[self._field(item) for item in planning.recommended_fields],
            optional_fields=[self._field(item) for item in planning.optional_fields],
            data_granularity=granularity,
            treatment_context=planning.population,
            response_domain=response_domain,
            unresolved_questions=list(planning.validation_warnings),
            literature_evidence_count=len(planning.literature_evidence),
            generation_source=generation if generation in {"EVIDENCE_AGENT", "GENERIC_FALLBACK", "LEGACY_TEMPLATE"} else "GENERIC_FALLBACK",
            status=getattr(planning, "lifecycle_status", "DRAFT"),
            frozen_at=getattr(planning, "frozen_at", None),
            audit={
                "planning_validation_status": planning.validation_status,
                "created_at": (planning.created_at or datetime.now(timezone.utc)).isoformat(),
            },
        )

    @staticmethod
    def _field(item: object) -> ContractFieldRequirement:
        return ContractFieldRequirement(
            field_id=item.field_id,
            label=item.label,
            canonical_name=item.canonical_name,
            role=item.role,
            priority=item.priority.value if hasattr(item.priority, "value") else str(item.priority),
            reason=item.reason,
            evidence_status=item.evidence_status,
            aliases=list(getattr(item, "aliases", []) or []),
        )

    @staticmethod
    def _canonical(fields: list[object], role: str) -> str | None:
        match = next((item.field_id for item in fields if getattr(item, "role", "") == role), None)
        return match

    @staticmethod
    def _subtype(planning: ResearchContract) -> str | None:
        text = f"{planning.research_question} {planning.population}".casefold()
        if "her2" in text and "negative" not in text:
            return "HER2-positive"
        if "triple" in text or "tnbc" in text or "三阴" in planning.research_question:
            return "Triple-negative"
        return None

    @staticmethod
    def _granularity(planning: ResearchContract, topic: ResearchTopic | None) -> str:
        known = getattr(topic, "known_data_granularity", None) if topic is not None else None
        if known in {"patient", "sample", "cell_line", "trial", "publication"}:
            return known
        text = f"{planning.research_question} {planning.research_type}".casefold()
        if "cell line" in text or "细胞系" in planning.research_question:
            return "cell_line"
        if "trial" in text or "试验" in planning.research_question:
            return "trial"
        if "sample" in text or "表达" in planning.research_question:
            return "sample"
        return "patient"
