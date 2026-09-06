from __future__ import annotations

import re
import string

from backend.app.v30.models import MemorySnapshot, RouteDecision, RouteKind
from backend.app.v30.router import rules


_PUNCTUATION = string.punctuation + "。！？，、；：…—·“”‘’（）【】《》"


class RouterAgent:
    """Deterministic first-pass router. Does not fetch data or call the medical pipeline."""

    def decide(self, message: str, memory: MemorySnapshot | None = None) -> RouteDecision:
        text = (message or "").strip()
        if not text:
            return RouteDecision(
                route=RouteKind.CHAT,
                domain="unknown",
                fallback=True,
                reason="empty_message",
                confidence=1.0,
            )

        domain = self._domain(text)
        if self._is_chat(text):
            return RouteDecision(
                route=RouteKind.CHAT,
                domain=domain,
                fallback=True,
                reason="greeting_or_smalltalk",
                confidence=0.95,
            )
        if self._is_plan(text) and self._session_ready_for_plan(memory):
            return RouteDecision(
                route=RouteKind.PLAN,
                domain=memory.goal.domain if memory and memory.goal and memory.goal.domain else domain,
                fallback=False,
                reason="user_asked_to_plan_after_clarification",
                confidence=0.8,
            )
        if self._is_concept(text) and not self._is_research(text):
            return RouteDecision(
                route=RouteKind.CONCEPT_QA,
                domain=domain,
                fallback=False,
                reason="concept_question",
                confidence=0.9,
            )
        if self._is_research(text):
            return RouteDecision(
                route=RouteKind.CLARIFY,
                domain=domain,
                fallback=False,
                reason="research_intent_needs_clarification",
                confidence=0.85,
            )
        return RouteDecision(
            route=RouteKind.CHAT,
            domain=domain,
            fallback=True,
            reason="no_research_object",
            confidence=0.4,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", "", text).casefold()

    def _is_chat(self, text: str) -> bool:
        compact = self._normalize(text).strip(_PUNCTUATION)
        return compact in {self._normalize(phrase) for phrase in rules.chat_phrases()}

    def _is_concept(self, text: str) -> bool:
        folded = text.strip().casefold()
        compact = self._normalize(text)
        for prefix in rules.concept_prefixes():
            prefix_folded = prefix.casefold()
            if folded.startswith(prefix_folded) or compact.startswith(self._normalize(prefix)):
                return True
        return False

    def _is_research(self, text: str) -> bool:
        compact = self._normalize(text)
        return any(self._normalize(token) in compact for token in rules.research_tokens())

    def _is_plan(self, text: str) -> bool:
        compact = self._normalize(text)
        return any(self._normalize(token) in compact for token in rules.plan_tokens())

    @staticmethod
    def _session_ready_for_plan(memory: MemorySnapshot | None) -> bool:
        if memory is None or memory.goal is None:
            return False
        if not memory.clarifications:
            return False
        return all(item.answer for item in memory.clarifications)

    def _domain(self, text: str) -> str:
        compact = self._normalize(text)
        for name, tokens in rules.domain_tokens().items():
            if any(self._normalize(token) in compact for token in tokens):
                return name
        return "unknown"
