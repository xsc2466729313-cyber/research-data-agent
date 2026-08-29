from __future__ import annotations

import hashlib
import re

from backend.app.parsers.base import ParseRequest, ParseResult, ParsedRecord


class PdfTextParser:
    """Extract plain text blocks. Does not guess table values if layout is uncertain."""

    version = "pdf-text-v1"

    def parse(self, request: ParseRequest) -> ParseResult:
        text = request.text or ""
        if not text.strip():
            return ParseResult(
                source_id=request.source_id,
                parse_method=self.version,
                records=[],
                warnings=["未提供 PDF 文本层；禁止模型猜测表格。"],
                status="REVIEW",
            )
        sections = self._sections(text)
        records = []
        for name, body in sections.items():
            excerpt = re.sub(r"\s+", " ", body).strip()[:800]
            records.append(
                ParsedRecord(
                    source_id=request.source_id,
                    source_file=request.filename,
                    source_location=f"section:{name}",
                    raw_field=name,
                    raw_value=excerpt,
                    inferred_semantic_type="prose",
                    parse_method=self.version,
                    parse_confidence=0.7,
                    parser_version=self.version,
                    status="PARSED",
                )
            )
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
        records.append(
            ParsedRecord(
                source_id=request.source_id,
                source_file=request.filename,
                source_location="document",
                raw_field="content_hash",
                raw_value=digest,
                inferred_semantic_type="identifier",
                parse_method=self.version,
                parse_confidence=1.0,
                parser_version=self.version,
                status="PARSED",
            )
        )
        return ParseResult(source_id=request.source_id, parse_method=self.version, records=records, status="PARSED")

    @staticmethod
    def _sections(text: str) -> dict[str, str]:
        headings = ("abstract", "introduction", "methods", "results", "discussion", "references")
        found: dict[str, str] = {}
        remaining = text
        for heading in headings:
            pattern = re.compile(rf"(?im)^(abstract|introduction|methods|results|discussion|references)\b")
            match = pattern.search(remaining)
            if not match:
                continue
            start = match.end()
            next_match = re.search(r"(?im)^(introduction|methods|results|discussion|references)\b", remaining[start:])
            body = remaining[start : start + next_match.start()] if next_match else remaining[start:]
            found[match.group(1).casefold()] = body
            remaining = remaining[start:]
        if not found:
            found["body"] = text
        return found
