from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from backend.app.parsers.base import ParseRequest, ParseResult, ParsedRecord


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.caption = ""
        self._in_caption = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._current = []
        elif tag == "tr" and self._current is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "caption":
            self._in_caption = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._current is not None:
            if any(self._row):
                self._current.append(self._row)
            self._row = None
        elif tag == "table" and self._current is not None:
            if self._current:
                self.tables.append(self._current)
            self._current = None
        elif tag == "caption":
            self._in_caption = False

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self.caption += data
        if self._cell is not None:
            self._cell.append(data)


class HtmlTableParser:
    version = "html-table-v1"

    def parse(self, request: ParseRequest) -> ParseResult:
        markup = request.html or request.text or ""
        if "<table" not in markup.casefold():
            return ParseResult(
                source_id=request.source_id,
                parse_method=self.version,
                records=[],
                warnings=["未发现 HTML table。"],
                status="FAILED",
            )
        parser = _TableParser()
        parser.feed(markup)
        records: list[ParsedRecord] = []
        for table_index, table in enumerate(parser.tables):
            header = table[0]
            for row_index, row in enumerate(table[1:], start=2):
                for col_index, value in enumerate(row):
                    field = header[col_index] if col_index < len(header) else f"column_{col_index}"
                    records.append(
                        ParsedRecord(
                            source_id=request.source_id,
                            source_file=request.filename,
                            source_location=f"table:{table_index}:row:{row_index}",
                            raw_field=html_lib.unescape(field),
                            raw_value=html_lib.unescape(value),
                            inferred_semantic_type="categorical",
                            parse_method=self.version,
                            parse_confidence=0.75,
                            parser_version=self.version,
                            status="PARSED",
                        )
                    )
        warnings = [f"caption={parser.caption.strip()}"] if parser.caption.strip() else []
        return ParseResult(
            source_id=request.source_id,
            parse_method=self.version,
            records=records,
            warnings=warnings,
            status="PARSED" if records else "FAILED",
        )
