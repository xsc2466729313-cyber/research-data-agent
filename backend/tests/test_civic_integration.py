from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.app.sources.civic import CIViCAdapter
from backend.app.sources.civic.models import CIViCTableName
from backend.tests.test_civic_adapter import civic_request, table_by_name


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_CIVIC_INTEGRATION") != "1",
        reason="Set RUN_CIVIC_INTEGRATION=1 to call the CIViC V2 GraphQL API.",
    ),
]


def test_real_civic_breast_evidence_preserves_ids_and_publications(
    tmp_path: Path,
) -> None:
    adapter = CIViCAdapter(cache_dir=tmp_path, timeout_seconds=120)
    request = civic_request(max_evidence_items=3, max_rows_per_table=1_000)

    first = adapter.run(request)
    second = adapter.run(request)

    assert first.total_count > 0
    assert len(first.evidence_items) == 3
    assert all(item.status == "ACCEPTED" for item in first.evidence_items)
    assert all(item.disease_name.casefold().find("breast") >= 0 for item in first.evidence_items)
    assert all(item.raw_evidence["id"] == item.civic_evidence_id for item in first.evidence_items)
    assert all(item.publication_id for item in first.evidence_items)

    relations = table_by_name(first, CIViCTableName.EVIDENCE_RELATIONS)
    assert relations.row_count == 3
    assert all(row["civic_variant_ids"] for row in relations.rows)
    assert all(row["publication_id"] for row in relations.rows)
    assert all(row["raw_value"]["id"] == row["civic_evidence_id"] for row in relations.rows)

    for source in first.source_items:
        path = Path(source.local_path or "")
        assert path.is_file()
        assert source.checksum == (
            f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        )
        assert source.url.startswith("https://civicdb.org/evidence/")
    assert second.cache_hit is True
    assert all(source.status == "cached" for source in second.source_items)
