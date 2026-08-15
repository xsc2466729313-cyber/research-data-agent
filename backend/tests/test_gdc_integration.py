from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.app.sources.gdc import GDCAdapter
from backend.tests.test_gdc_adapter import adapter_request


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_GDC_INTEGRATION") != "1",
        reason="Set RUN_GDC_INTEGRATION=1 to call the official GDC API.",
    ),
]


def test_tcga_brca_live_discovery_download_and_cache(tmp_path: Path) -> None:
    adapter = GDCAdapter(cache_dir=tmp_path, timeout_seconds=60)
    request = adapter_request(
        max_files=1,
        data_types=["Clinical Supplement"],
        download=True,
        max_download_bytes=1_000_000,
    )

    first = adapter.run(request)
    second = adapter.run(request)

    assert first.project.project_id == "TCGA-BRCA"
    assert first.project.released is True
    assert first.project.case_count > 0
    assert "Breast" in first.project.primary_site
    assert len(first.files) == 1

    file = first.files[0]
    source = file.source_item
    assert file.access == "open"
    assert file.file_size > 0
    assert source.accession == "TCGA-BRCA"
    assert source.url == f"https://api.gdc.cancer.gov/data/{file.file_id}"
    assert source.status == "downloaded"
    assert source.local_path is not None

    local_path = Path(source.local_path)
    assert local_path.is_file()
    digest = hashlib.md5(local_path.read_bytes(), usedforsecurity=False).hexdigest()
    assert digest == file.md5sum
    assert second.source_items[0].status == "cached"
    assert second.cache_hit.project_metadata is True
    assert second.cache_hit.file_metadata is True

