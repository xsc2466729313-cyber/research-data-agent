from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.app.sources.cbioportal import CBioPortalAdapter
from backend.tests.test_cbioportal_adapter import cbioportal_request, table_by_name


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_CBIOPORTAL_INTEGRATION") != "1",
        reason="Set RUN_CBIOPORTAL_INTEGRATION=1 to call the public cBioPortal API.",
    ),
]


def test_metabric_live_raw_tables_sources_and_cache(tmp_path: Path) -> None:
    adapter = CBioPortalAdapter(cache_dir=tmp_path, timeout_seconds=90)
    request = cbioportal_request(max_records_per_table=5)

    first = adapter.run(request)
    second = adapter.run(request)

    metadata = first.study.raw_metadata
    assert first.study.study_id == "brca_metabric"
    assert metadata["studyId"] == "brca_metabric"
    assert metadata["publicStudy"] is True
    assert metadata["allSampleCount"] > 2_000
    assert "METABRIC" in metadata["name"]

    assert first.selection.mutation_profile_id == "brca_metabric_mutations"
    assert first.selection.cna_profile_id == "brca_metabric_cna"
    assert first.selection.mutation_sample_list_id == "brca_metabric_sequenced"
    assert first.selection.cna_sample_list_id == "brca_metabric_cna"
    assert {gene["hugoGeneSymbol"] for gene in first.selection.genes} == {
        "ERBB2",
        "PIK3CA",
        "TP53",
    }

    expected_tables = {
        "molecular_profiles",
        "sample_lists",
        "genes",
        "mutations",
        "discrete_cna",
        "clinical_sample",
        "clinical_patient",
    }
    assert {table.table_name for table in first.tables} == expected_tables

    mutations = table_by_name(first, "mutations")
    assert 0 < mutations.row_count <= 5
    assert all(row["studyId"] == "brca_metabric" for row in mutations.rows)
    assert {"sampleId", "patientId", "gene", "proteinChange"}.issubset(
        mutations.raw_fields
    )

    cna = table_by_name(first, "discrete_cna")
    assert cna.row_count == 5
    assert cna.upstream_row_count is not None
    assert cna.upstream_row_count > 2_000
    assert cna.truncated is True
    assert all(row["studyId"] == "brca_metabric" for row in cna.rows)
    assert all(isinstance(row["alteration"], int) for row in cna.rows)
    assert all("her2_status" not in row for row in cna.rows)

    for table_name in ("clinical_sample", "clinical_patient"):
        table = table_by_name(first, table_name)
        assert table.row_count == 5
        assert all(row["studyId"] == "brca_metabric" for row in table.rows)
        assert {"patientId", "clinicalAttributeId", "value"}.issubset(
            table.raw_fields
        )

    assert all(source.url.startswith("https://www.cbioportal.org/api/") for source in first.source_items)
    for source in first.source_items:
        path = Path(source.local_path or "")
        assert path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert source.checksum == f"sha256:{digest}"
        assert source.status == "retrieved"

    assert all(second.cache_hit.values())
    assert all(source.status == "cached" for source in second.source_items)
