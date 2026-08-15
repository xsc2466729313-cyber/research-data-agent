from __future__ import annotations

import os

import pytest

from backend.app.goldset.source_verifier import OfficialSourceVerifier
from backend.tests.goldset_curation_fixtures import gdc_source


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_GOLDSET_SOURCE_INTEGRATION") != "1",
    reason="Set RUN_GOLDSET_SOURCE_INTEGRATION=1 to verify TCGA-BRCA with GDC.",
)
def test_live_gdc_accession_verification() -> None:
    verifier = OfficialSourceVerifier()
    try:
        result = verifier.verify(gdc_source())
    finally:
        verifier.close()

    assert result.status.value == "verified"
    assert result.http_status == 200
    assert result.source.accession == "TCGA-BRCA"
    assert result.response_sha256 is not None
