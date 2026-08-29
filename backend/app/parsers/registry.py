from __future__ import annotations

from backend.app.parsers.base import ParseRequest, ParseResult
from backend.app.parsers.csv_tsv import CsvTsvParser
from backend.app.parsers.excel import ExcelParser
from backend.app.parsers.html_table import HtmlTableParser
from backend.app.parsers.jats import JatsXmlParser
from backend.app.parsers.pdf_text import PdfTextParser


class ParserRegistry:
    def __init__(self) -> None:
        self.csv = CsvTsvParser()
        self.excel = ExcelParser()
        self.html = HtmlTableParser()
        self.pdf = PdfTextParser()
        self.jats = JatsXmlParser()

    def parse(self, request: ParseRequest, *, workbook_bytes: bytes | None = None) -> ParseResult:
        name = request.filename.casefold()
        if name.endswith((".csv", ".tsv", ".txt")):
            return self.csv.parse(request)
        if name.endswith((".xlsx", ".xlsm")):
            return self.excel.parse(request, workbook_bytes=workbook_bytes)
        if name.endswith((".html", ".htm")) or (request.html and "<table" in (request.html or "").casefold()):
            return self.html.parse(request)
        if name.endswith(".pdf") or request.filename.casefold().endswith(".pdf.txt"):
            return self.pdf.parse(request)
        if name.endswith(".xml") or "<article" in (request.text or request.html or "").casefold():
            return self.jats.parse(request)
        if request.html:
            return self.html.parse(request)
        if request.rows:
            return self.excel.parse(request)
        return self.csv.parse(request)
