from __future__ import annotations

import re

from backend.app.literature.models import PaperRecord
from backend.app.research_planning.models import EvidenceReference


_SECTION_PRIORITY = (
    "methods",
    "data_availability",
    "supplementary",
    "table",
    "cohort",
    "results",
    "abstract",
    "title",
)


def evidence_references(
    papers: list[PaperRecord],
    *,
    terms: list[str],
    evidence_type: str,
    limit: int = 3,
    minimum_term_hits: int = 1,
) -> list[EvidenceReference]:
    normalized_terms = [term.casefold() for term in terms if term.strip()]
    matches: list[tuple[int, EvidenceReference]] = []
    for paper in papers:
        sections = dict(paper.sections)
        sections.setdefault("title", paper.title)
        if paper.abstract:
            sections.setdefault("abstract", paper.abstract)
        for section, text in sections.items():
            folded = text.casefold()
            hits = sum(1 for term in normalized_terms if term in folded)
            if hits < minimum_term_hits:
                continue
            priority = _SECTION_PRIORITY.index(section) if section in _SECTION_PRIORITY else len(_SECTION_PRIORITY)
            snippet = _snippet(text, normalized_terms)
            confidence = 0.92 if section == "methods" else 0.82 if section in {"table", "supplementary"} else 0.76 if section == "abstract" else 0.68
            matches.append(
                (
                    hits * 100 - priority,
                    EvidenceReference(
                        paper_id=paper.paper_id,
                        source_id=paper.source_id,
                        provider=paper.provider,
                        section=section,
                        evidence_type=evidence_type,
                        source_url=paper.source_url,
                        text=snippet,
                        confidence=confidence,
                    ),
                )
            )
            break
    matches.sort(key=lambda item: item[0], reverse=True)
    output: list[EvidenceReference] = []
    seen: set[str] = set()
    for _score, evidence in matches:
        if evidence.paper_id in seen:
            continue
        seen.add(evidence.paper_id)
        output.append(evidence)
        if len(output) >= limit:
            break
    return output


def _snippet(text: str, terms: list[str], limit: int = 560) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    folded = compact.casefold()
    positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 120)
    end = min(len(compact), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"
