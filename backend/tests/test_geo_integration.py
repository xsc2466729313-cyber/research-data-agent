from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.app.sources.geo import GEOAdapter
from backend.app.sources.geo.models import GEOResourceType
from backend.tests.test_geo_adapter import geo_request


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_GEO_INTEGRATION") != "1",
        reason="Set RUN_GEO_INTEGRATION=1 to call the official NCBI GEO archive.",
    ),
]


def test_gse25066_live_discovery_small_download_and_cache(tmp_path: Path) -> None:
    adapter = GEOAdapter(cache_dir=tmp_path, timeout_seconds=60)
    request = geo_request(
        accession="GSE25066",
        resource_types=[GEOResourceType.SUPPLEMENT],
        max_files_per_type=1,
        download=True,
        max_download_bytes=1_000_000,
    )

    first = adapter.run(request)
    second = adapter.run(request)

    assert first.accession == "GSE25066"
    assert first.availability[0].status == "available"
    assert first.resources[0].file_name == "GSE25066_Genelist_weights.txt.gz"
    assert first.resources[0].file_size is not None
    assert first.resources[0].file_size > 0
    source = first.source_items[0]
    assert source.status == "downloaded"
    assert source.local_path is not None
    assert source.url == (
        "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE25nnn/GSE25066/"
        "suppl/GSE25066_Genelist_weights.txt.gz"
    )
    local_path = Path(source.local_path)
    assert local_path.is_file()
    actual_sha256 = hashlib.sha256(local_path.read_bytes()).hexdigest()
    assert source.checksum == f"sha256:{actual_sha256}"
    assert second.source_items[0].status == "cached"
    assert second.cache_hit.accession_directory is True
    assert second.cache_hit.resource_directories["supplement"] is True


def test_gse76360_live_matrix_soft_and_supplement_discovery(
    tmp_path: Path,
) -> None:
    result = GEOAdapter(cache_dir=tmp_path, timeout_seconds=60).run(
        geo_request(accession="GSE76360", max_files_per_type=10)
    )

    assert result.accession == "GSE76360"
    assert {item.resource_type for item in result.availability} == set(
        GEOResourceType
    )
    assert all(item.status == "available" for item in result.availability)
    names = {resource.file_name for resource in result.resources}
    assert "GSE76360_series_matrix.txt.gz" in names
    assert "GSE76360_family.soft.gz" in names
    assert "GSE76360_RAW.tar" in names
    assert "GSE76360_non_normalized.txt.gz" in names
    assert all(source.accession == "GSE76360" for source in result.source_items)
    assert all(source.status == "discovered" for source in result.source_items)
    assert all(source.url.startswith("https://ftp.ncbi.nlm.nih.gov/") for source in result.source_items)
