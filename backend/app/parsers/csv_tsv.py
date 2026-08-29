from __future__ import annotations

import csv
import io
from collections import Counter

from backend.app.parsers.base import ParseRequest, ParseResult, ParsedRecord


class CsvTsvParser:
    version = "csv-tsv-v1"

    def parse(self, request: ParseRequest) -> ParseResult:
        text = request.text or ""
        if not text.strip():
            return ParseResult(source_id=request.source_id, parse_method=self.version, records=[], warnings=["空文本"], status="FAILED")
        sample = text[:4096]
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        try:
            text.encode("utf-8")
        except UnicodeError:
            pass
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        records: list[ParsedRecord] = []
        missing_tokens = {"", "na", "n/a", "null", ".", "na."}
        for index, row in enumerate(reader):
            for field, value in row.items():
                raw = "" if value is None else str(value).strip()
                missing = raw.casefold() in missing_tokens
                records.append(
                    ParsedRecord(
                        source_id=request.source_id,
                        source_file=request.filename,
                        source_location=f"row:{index + 2}",
                        raw_field=field or f"column_{len(records)}",
                        raw_value=None if missing else raw,
                        inferred_semantic_type="missing" if missing else self._type(raw),
                        parse_method=self.version,
                        parse_confidence=0.9 if not missing else 0.4,
                        parser_version=self.version,
                        status="PARSED",
                    )
                )
        warnings = []
        if delimiter == "\t":
            warnings.append("检测到 TSV 分隔符。")
        types = Counter(item.inferred_semantic_type for item in records)
        warnings.append("类型画像：" + ", ".join(f"{name}={count}" for name, count in types.items()))
        return ParseResult(
            source_id=request.source_id,
            parse_method=self.version,
            records=records,
            warnings=warnings,
            status="PARSED" if records else "FAILED",
        )

    @staticmethod
    def _type(value: str) -> str:
        folded = value.casefold()
        if folded in {"true", "false", "yes", "no", "是", "否"}:
            return "boolean"
        try:
            float(value.replace(",", ""))
            return "continuous"
        except ValueError:
            if any(token in folded for token in ("patient", "sample", "gse", "gsm")):
                return "identifier"
            return "categorical"
