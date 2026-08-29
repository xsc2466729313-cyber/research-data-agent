from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.app.models import ApiModel


class ParsedRecord(ApiModel):
    source_id: str
    source_file: str | None = None
    source_location: str | None = None
    raw_field: str
    raw_value: Any = None
    inferred_semantic_type: str | None = None
    parse_method: str
    parse_confidence: float = Field(ge=0, le=1)
    parser_version: str
    status: Literal["PARSED", "REVIEW", "FAILED"]


class ParseRequest(ApiModel):
    source_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=500)
    text: str | None = Field(default=None, max_length=2_000_000)
    html: str | None = Field(default=None, max_length=2_000_000)
    rows: list[dict[str, Any]] | None = None


class ParseResult(ApiModel):
    source_id: str
    parse_method: str
    records: list[ParsedRecord]
    warnings: list[str] = Field(default_factory=list)
    status: Literal["PARSED", "REVIEW", "FAILED"]
