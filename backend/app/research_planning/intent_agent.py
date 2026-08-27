from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.research_planning.models import ResearchTopic, TopicCreateRequest


_DOMAIN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("oncology", ("癌", "肿瘤", "oncology", "cancer", "carcinoma", "sarcoma")),
    ("astronomy", ("黑洞", "暗物质", "星系", "宇宙", "black hole", "dark matter", "galaxy")),
    ("biomedicine", ("治疗", "预后", "基因", "蛋白", "免疫", "therapy", "gene", "protein")),
)


class ResearchIntentAgent:
    """Deterministic, schema-validated first pass over a broad research topic."""

    def understand(self, request: TopicCreateRequest) -> ResearchTopic:
        text = request.topic.strip()
        domain = request.domain_hint or self._domain(text)
        disease = self._disease(text)
        population = self._population(text, disease)
        exposure = self._exposure(text)
        outcome = self._outcome(text)
        granularity = "patient" if domain in {"oncology", "biomedicine"} and disease else None
        missing: list[str] = []
        for label, value in (
            ("population", population),
            ("exposure", exposure),
            ("outcome", outcome),
            ("data_granularity", granularity),
        ):
            if value is None:
                missing.append(label)
        ambiguity = "high" if len(missing) >= 2 else "medium" if missing else "low"
        return ResearchTopic(
            topic_id=f"topic-{uuid4().hex[:12]}",
            topic=text,
            domain=domain,
            disease=disease,
            known_population=population,
            known_exposure=exposure,
            known_outcome=outcome,
            known_data_granularity=granularity,
            ambiguity_level=ambiguity,
            missing_dimensions=missing,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _domain(text: str) -> str:
        folded = text.casefold()
        for domain, tokens in _DOMAIN_PATTERNS:
            if any(token in folded for token in tokens):
                return domain
        return "general_science"

    @staticmethod
    def _disease(text: str) -> str | None:
        folded = text.casefold()
        if "乳腺癌" in text or "breast cancer" in folded:
            return "breast cancer"
        match = re.search(r"([\u4e00-\u9fff]{1,12}(?:癌|肿瘤))", text)
        return match.group(1) if match else None

    @staticmethod
    def _population(text: str, disease: str | None) -> str | None:
        folded = text.casefold()
        if not disease:
            return None
        if "her2" in folded and ("阳性" in text or "positive" in folded):
            return f"HER2-positive {disease} patients"
        if any(token in folded for token in ("患者", "patients", "cohort")):
            return f"{disease} patients"
        return None

    @staticmethod
    def _exposure(text: str) -> str | None:
        folded = text.casefold()
        genes = re.findall(r"\b[A-Z][A-Z0-9-]{2,11}\b", text)
        if genes:
            return f"{genes[0]} molecular status"
        if "新辅助" in text or "neoadjuvant" in folded:
            return "neoadjuvant treatment"
        if "免疫治疗" in text or "immunotherapy" in folded:
            return "immunotherapy"
        return None

    @staticmethod
    def _outcome(text: str) -> str | None:
        folded = text.casefold()
        if "pcr" in folded or "病理完全缓解" in text:
            return "pathological complete response"
        if any(token in folded for token in ("预后", "生存", "survival", "prognosis")):
            return "survival outcome"
        if any(token in folded for token in ("响应", "反应", "response")):
            return "treatment response"
        return None
