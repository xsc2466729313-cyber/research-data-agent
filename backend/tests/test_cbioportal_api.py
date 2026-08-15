from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app, get_cbioportal_adapter
from backend.app.sources.cbioportal import CBioPortalAdapter
from backend.tests.test_cbioportal_adapter import (
    cbioportal_request,
    standard_handler,
)


client = TestClient(app)


def test_cbioportal_adapter_api_returns_metabric_raw_tables(
    tmp_path: Path,
) -> None:
    transport_client = httpx.Client(transport=httpx.MockTransport(standard_handler))
    adapter = CBioPortalAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_cbioportal_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/cbioportal",
            json=cbioportal_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_cbioportal_adapter, None)
        transport_client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "cbioportal"
    assert payload["study"]["study_id"] == "brca_metabric"
    assert payload["study"]["raw_metadata"]["studyId"] == "brca_metabric"
    assert {table["table_name"] for table in payload["tables"]} >= {
        "clinical_sample",
        "clinical_patient",
        "mutations",
        "discrete_cna",
    }
    cna = next(
        table for table in payload["tables"] if table["table_name"] == "discrete_cna"
    )
    assert cna["rows"][0]["gene"]["hugoGeneSymbol"] == "ERBB2"
    assert cna["rows"][0]["alteration"] == 2
    assert "her2_status" not in cna["rows"][0]


def test_cbioportal_adapter_api_exposes_structured_failure_code(
    tmp_path: Path,
) -> None:
    request = cbioportal_request(study_id="../secret")

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid study ID must not call cBioPortal")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = CBioPortalAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_cbioportal_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/cbioportal",
            json=request.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_cbioportal_adapter, None)
        transport_client.close()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_study_id"
    assert detail["retryable"] is False
