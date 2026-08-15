from __future__ import annotations

import httpx

from backend.app.goldset.models import SourceReference
from backend.app.goldset.source_verifier import OfficialSourceVerifier
from backend.tests.goldset_curation_fixtures import gdc_source


def test_official_source_verifier_requires_accession_in_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"project_id": "TCGA-BRCA"}},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OfficialSourceVerifier(client=client).verify(gdc_source())
    finally:
        client.close()

    assert result.status.value == "verified"
    assert result.http_status == 200
    assert result.response_sha256 is not None
    assert result.source.source_id == "gdc:TCGA-BRCA"


def test_source_verifier_rejects_non_official_host_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid host must be rejected before network access")

    source = SourceReference(
        source_id="fake:TCGA-BRCA",
        source_database="gdc",
        accession="TCGA-BRCA",
        url="https://example.org/projects/TCGA-BRCA",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OfficialSourceVerifier(client=client).verify(source)
    finally:
        client.close()

    assert result.status.value == "failed"
    assert "allowlisted" in result.reason
    assert result.http_status is None


def test_source_verifier_rejects_200_page_without_accession() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="official not-found page", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = OfficialSourceVerifier(client=client).verify(gdc_source())
    finally:
        client.close()

    assert result.status.value == "failed"
    assert "did not contain" in result.reason


def test_source_verifier_rejects_redirect_outside_official_domain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.gdc.cancer.gov":
            return httpx.Response(
                302,
                headers={"Location": "https://example.org/TCGA-BRCA"},
                request=request,
            )
        return httpx.Response(200, text="TCGA-BRCA", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    try:
        result = OfficialSourceVerifier(client=client).verify(gdc_source())
    finally:
        client.close()

    assert result.status.value == "failed"
    assert "redirected outside" in result.reason
