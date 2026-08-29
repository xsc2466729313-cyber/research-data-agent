from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from backend.app.models import ApiModel, SourceItem


class DepMapCellLineRecord(ApiModel):
    model_id: str
    cell_line_name: str
    lineage: str
    drug: str | None = None
    auc: float | None = None
    ic50: float | None = None
    response_domain: str = "preclinical_cell_line"
    source_id: str
    url: str
    raw_record: dict[str, Any] = Field(default_factory=dict)


class DepMapAdapterResult(ApiModel):
    task_id: str
    adapter: str = "depmap"
    query: str
    records: list[DepMapCellLineRecord]
    source_items: list[SourceItem]
    request_url: str
    queried_at: datetime
    notice: str
