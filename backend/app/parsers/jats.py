from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from backend.app.parsers.base import ParseRequest, ParseResult, ParsedRecord
from backend.app.parsers.html_table import HtmlTableParser


class JatsXmlParser:
    """Extract JATS tables and figure captions. Does not digitize plot pixels."""

    version = "jats-xml-v1"

    def parse(self, request: ParseRequest) -> ParseResult:
        xml_text = request.text or request.html or ""
        if not xml_text.strip():
            return ParseResult(
                source_id=request.source_id,
                parse_method=self.version,
                records=[],
                warnings=["未提供论文 XML；禁止根据图画像素猜测数值。"],
                status="REVIEW",
            )
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return ParseResult(
                source_id=request.source_id,
                parse_method=self.version,
                records=[],
                warnings=["JATS XML 无法解析；未猜测表格。"],
                status="REVIEW",
            )
        records: list[ParsedRecord] = []
        warnings: list[str] = []
        for index, table_wrap in enumerate(root.findall(".//{*}table-wrap")):
            table_el = table_wrap.find(".//{*}table")
            if table_el is None:
                continue
            html = ET.tostring(table_el, encoding="unicode")
            parsed = HtmlTableParser().parse(
                ParseRequest(
                    source_id=request.source_id,
                    filename=request.filename,
                    html=html,
                )
            )
            for item in parsed.records:
                records.append(
                    item.model_copy(
                        update={
                            "source_location": f"table-wrap:{index}:{item.source_location or 'cell'}",
                            "parse_method": self.version,
                            "parser_version": self.version,
                        }
                    )
                )
        for index, fig in enumerate(root.findall(".//{*}fig")):
            caption = "".join(fig.itertext())
            excerpt = " ".join(caption.split())[:800]
            if not excerpt:
                continue
            records.append(
                ParsedRecord(
                    source_id=request.source_id,
                    source_file=request.filename,
                    source_location=f"fig:{index}",
                    raw_field="figure_caption",
                    raw_value=excerpt,
                    inferred_semantic_type="figure_caption",
                    parse_method=self.version,
                    parse_confidence=0.6,
                    parser_version=self.version,
                    status="REVIEW",
                )
            )
            warnings.append(
                f"图 {index + 1} 仅提取图注，未从图像素读数；数值需对照原图或补充表。"
            )
        digest = hashlib.sha256(xml_text.encode("utf-8", errors="ignore")).hexdigest()[:16]
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
        status = "PARSED" if any(item.inferred_semantic_type != "figure_caption" for item in records[:-1]) else "REVIEW"
        if not any(item.raw_field != "content_hash" and item.inferred_semantic_type != "figure_caption" for item in records):
            warnings.append("本文没有可解析表格；图注不得当作测量值。")
        return ParseResult(
            source_id=request.source_id,
            parse_method=self.version,
            records=records,
            warnings=warnings,
            status=status,
        )
