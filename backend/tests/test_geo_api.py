from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app, get_geo_adapter
from backend.app.sources.geo import GEOAdapter
from backend.tests.test_geo_adapter import geo_request, standard_handler


client = TestClient(app)


def test_geo_adapter_api_returns_registered_official_sources(
    tmp_path: Path,
) -> None:
    transport_client = httpx.Client(transport=httpx.MockTransport(standard_handler))
    adapter = GEOAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_geo_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/geo",
            json=geo_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_geo_adapter, None)
        transport_client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "geo"
    assert payload["accession"] == "GSE25066"
    assert len(payload["availability"]) == 3
    assert payload["resources"][0]["file_name"] == (
        "GSE25066_series_matrix.txt.gz"
    )
    assert payload["source_items"][0]["url"].startswith(
        "https://ftp.ncbi.nlm.nih.gov/geo/series/"
    )
    assert payload["source_items"][0]["status"] == "discovered"


def test_geo_adapter_api_exposes_structured_failure_code(tmp_path: Path) -> None:
    request_payload = geo_request(accession="GPL96")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid accession must not call GEO")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GEOAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_geo_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/geo",
            json=request_payload.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_geo_adapter, None)
        transport_client.close()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_accession"
    assert detail["retryable"] is False
