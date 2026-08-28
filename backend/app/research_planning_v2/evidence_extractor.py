from __future__ import annotations

import hashlib
import re
from typing import Iterable

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.evidence import evidence_references

from .models import EvidencePackItemV2, StructuredExtractionV2


class EvidenceExtractorV2:
    """Extract research slots from supplied papers without inventing facts.

    This is deliberately provider/model agnostic. A future Qwen adapter can
    replace the slot detector, but every returned slot must still point to a
    real ``source_id`` and excerpt in the Evidence Pack.
    """

    _SLOT_TERMS: dict[str, tuple[str, ...]] = {
        "population": ("patient", "patients", "cohort", "breast cancer", "乳腺癌"),
        "intervention": ("neoadjuvant", "treatment", "therapy", "治療", "治疗"),
        "exposure": ("mutation", "expression", "PIK3CA", "biomarker", "暴露"),
        "comparator": ("control", "comparator", "wild type", "对照"),
        "outcome": ("pCR", "pathological complete response", "response", "survival", "结局", "疗效"),
        "covariates": ("age", "stage", "subtype", "ER", "PR", "HER2", "covariate"),
        "subgroups": ("subgroup", "stratified", "亚组", "分层"),
    }

    def extract(
        self,
        topic: str,
        papers: list[PaperRecord],
        *,
        user_constraints: dict[str, object] | None = None,
    ) -> tuple[StructuredExtractionV2, list[EvidencePackItemV2]]:
        pack = self.build_evidence_pack(topic, papers)
        refs = [item.evidence_id for item in pack]
        source = "EVIDENCE_AGENT" if pack else "GENERIC_FALLBACK"
        text = " ".join([topic, *(item.text for item in pack)]).casefold()
        slots: dict[str, list[str]] = {name: [] for name in self._SLOT_TERMS}
        for slot, terms in self._SLOT_TERMS.items():
            present = [term for term in terms if term.casefold() in text]
            if present:
                slots[slot] = [self._canonical_term(term) for term in present[:4]]
        constraints = user_constraints or {}
        for slot in slots:
            value = constraints.get(slot)
            if isinstance(value, str) and value.strip():
                slots[slot] = [value.strip()]
            elif isinstance(value, list):
                slots[slot] = [str(item).strip() for item in value if str(item).strip()]
        research_type = self._research_type(topic, text)
        granularity = "sample" if any(token in text for token in ("expression", "sample", "样本")) else "patient_or_sample"
        confidence = 0.78 if pack and slots["outcome"] else 0.62 if pack else 0.25
        return StructuredExtractionV2(
            population=slots["population"],
            intervention=slots["intervention"],
            exposure=slots["exposure"],
            comparator=slots["comparator"],
            outcome=slots["outcome"],
            covariates=slots["covariates"],
            subgroups=slots["subgroups"],
            granularity=granularity,
            research_type=research_type,
            evidence_refs=refs,
            extraction_source=source,
            confidence=confidence,
        ), pack

    def build_evidence_pack(self, topic: str, papers: list[PaperRecord], *, limit: int = 20) -> list[EvidencePackItemV2]:
        terms = self._query_terms(topic)
        refs = evidence_references(papers, terms=terms, evidence_type="research_agent_extraction", limit=limit)
        output: list[EvidencePackItemV2] = []
        for ref in refs:
            digest = hashlib.sha256(f"{ref.source_id}|{ref.paper_id}|{ref.section}|{ref.text}".encode("utf-8")).hexdigest()[:16]
            output.append(EvidencePackItemV2(
                evidence_id=f"evidence-{digest}",
                paper_id=ref.paper_id,
                source_id=ref.source_id,
                source_url=ref.source_url,
                provider=ref.provider,
                section=ref.section,
                evidence_type=ref.evidence_type,
                text=ref.text,
                raw_value=ref.text,
                confidence=ref.confidence,
            ))
        return output

    @staticmethod
    def _query_terms(topic: str) -> list[str]:
        tokens = [token for token in re.split(r"[\s,，;；:：/]+", topic.strip()) if len(token) >= 2]
        defaults = ["breast cancer", "乳腺癌", "patient", "cohort", "outcome", "response"]
        return list(dict.fromkeys(tokens + defaults))[:20]

    @staticmethod
    def _canonical_term(term: str) -> str:
        aliases = {"patients": "patient", "cohort": "cohort", "pcr": "pCR", "er": "ER", "pr": "PR", "her2": "HER2"}
        return aliases.get(term.casefold(), term)

    @staticmethod
    def _research_type(topic: str, text: str) -> str:
        folded = f"{topic} {text}".casefold()
        if any(token in folded for token in ("predict", "prediction", "预测")):
            return "classification_prediction"
        if any(token in folded for token in ("survival", "生存", "hazard", "kaplan")):
            return "survival_analysis"
        if any(token in folded for token in ("subgroup", "亚组", "heterogeneity", "异质")):
            return "subgroup_association"
        return "association"
