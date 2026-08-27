from __future__ import annotations

import hashlib
import re

from backend.app.literature.models import PaperRecord
from backend.app.rag.models import PaperChunk


_SECTION_ORDER = {
    "methods": 1,
    "data_availability": 2,
    "supplementary": 3,
    "table": 4,
    "cohort": 5,
    "population": 6,
    "variables": 7,
    "outcome_definition": 8,
    "statistical_analysis": 9,
    "results": 10,
    "abstract": 11,
    "title": 12,
    "limitations": 13,
}


class PaperChunker:
    """Structure-aware paper chunking that never invents absent sections."""

    def __init__(self, *, max_chars: int = 1200, overlap_chars: int = 120) -> None:
        if max_chars < 200:
            raise ValueError("max_chars must be at least 200")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(self, topic_id: str, papers: list[PaperRecord]) -> list[PaperChunk]:
        output: list[PaperChunk] = []
        for paper in papers:
            sections = dict(paper.sections)
            sections.setdefault("title", paper.title)
            if paper.abstract:
                sections.setdefault("abstract", paper.abstract)
            ordered = sorted(
                sections.items(),
                key=lambda item: (_SECTION_ORDER.get(self._normalize_section(item[0]), 99), item[0]),
            )
            for raw_section, raw_text in ordered:
                section = self._normalize_section(raw_section)
                text = re.sub(r"\s+", " ", str(raw_text or "")).strip()
                if not text:
                    continue
                for index, (piece, start, end) in enumerate(self._split(text)):
                    digest = hashlib.sha256(
                        f"{topic_id}|{paper.paper_id}|{section}|{index}|{piece}".encode("utf-8")
                    ).hexdigest()[:24]
                    output.append(
                        PaperChunk(
                            chunk_id=f"chunk-{digest}",
                            topic_id=topic_id,
                            paper_id=paper.paper_id,
                            source_id=paper.source_id,
                            provider=paper.provider,
                            source_url=paper.source_url,
                            section=section,
                            section_priority=_SECTION_ORDER.get(section, 99),
                            chunk_index=index,
                            text=piece,
                            raw_field=raw_section,
                            raw_value=piece,
                            start_char=start,
                            end_char=end,
                        )
                    )
        return output

    def _split(self, text: str) -> list[tuple[str, int, int]]:
        if len(text) <= self.max_chars:
            return [(text, 0, len(text))]
        output: list[tuple[str, int, int]] = []
        start = 0
        while start < len(text):
            target_end = min(len(text), start + self.max_chars)
            end = self._sentence_boundary(text, start, target_end)
            if end <= start:
                end = target_end
            piece = text[start:end].strip()
            if piece:
                actual_start = start + (len(text[start:end]) - len(text[start:end].lstrip()))
                output.append((piece, actual_start, actual_start + len(piece)))
            if end >= len(text):
                break
            start = max(start + 1, end - self.overlap_chars)
        return output

    @staticmethod
    def _sentence_boundary(text: str, start: int, target_end: int) -> int:
        if target_end >= len(text):
            return len(text)
        window = text[start:target_end]
        candidates = [window.rfind(mark) for mark in ("。", "！", "？", ". ", "; ")]
        boundary = max(candidates)
        if boundary < len(window) // 2:
            return target_end
        marker_length = 2 if window[boundary:boundary + 2] in {". ", "; "} else 1
        return start + boundary + marker_length

    @staticmethod
    def _normalize_section(section: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "_", section.casefold()).strip("_")
        aliases = {
            "method": "methods",
            "materials_and_methods": "methods",
            "data_availability_statement": "data_availability",
            "supplement": "supplementary",
            "supplemental": "supplementary",
            "tables": "table",
            "cohort_description": "cohort",
            "outcomes": "outcome_definition",
            "statistics": "statistical_analysis",
        }
        return aliases.get(value, value or "unknown")
