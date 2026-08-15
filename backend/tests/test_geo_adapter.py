from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from backend.app.models import SearchPlan, SearchPlanItem
from backend.app.sources.geo import GEOAdapter, GEOAdapterError, GEOErrorCode
from backend.app.sources.geo.models import (
    GEOAdapterOptions,
    GEOAdapterRequest,
    GEOResourceType,
)


SMALL_FILE = b"gene\tweight\nERBB2\t1.0\n"


def geo_request(**option_overrides: object) -> GEOAdapterRequest:
    options: dict[str, object] = {"accession": "GSE25066"}
    options.update(option_overrides)
    return GEOAdapterRequest(
        search_plan=SearchPlan(
            task_id="task_geo_001",
            plans=[
                SearchPlanItem(
                    source="GEO",
                    goal="获取乳腺癌队列的表达矩阵和原始来源文件",
                    priority=1,
                )
            ],
        ),
        options=GEOAdapterOptions(**options),
    )


def directory_html(*hrefs: str) -> str:
    links = "".join(f'<a href="{href}">{href}</a>\n' for href in hrefs)
    return f"<!doctype html><html><body>{links}</body></html>"


def html_response(request: httpx.Request, *hrefs: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=directory_html(*hrefs),
        headers={"content-type": "text/html; charset=UTF-8"},
        request=request,
    )


def standard_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/GSE25066/"):
        return html_response(request, "matrix/", "soft/", "suppl/")
    if path.endswith("/matrix/"):
        return html_response(request, "GSE25066_series_matrix.txt.gz")
    if path.endswith("/soft/"):
        return html_response(request, "GSE25066_family.soft.gz")
    if path.endswith("/suppl/"):
        return html_response(
            request,
            "GSE25066_Genelist_weights.txt.gz",
            "GSE25066_RAW.tar",
            "filelist.txt",
        )
    raise AssertionError(f"Unexpected request: {request.method} {request.url}")


def test_geo_discovers_matrix_soft_and_supplements_with_real_urls(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GEOAdapter(cache_dir=tmp_path, client=client).run(
            geo_request(accession="gse25066")
        )

    assert len(requests) == 4
    assert result.accession == "GSE25066"
    assert result.portal_url.endswith("acc=GSE25066")
    assert {item.resource_type for item in result.availability} == set(
        GEOResourceType
    )
    assert all(item.status == "available" for item in result.availability)
    assert [resource.file_name for resource in result.resources] == [
        "GSE25066_series_matrix.txt.gz",
        "GSE25066_family.soft.gz",
        "GSE25066_Genelist_weights.txt.gz",
        "GSE25066_RAW.tar",
    ]
    source = result.source_items[0]
    assert source.source_id.startswith("geo:GSE25066:")
    assert source.accession == "GSE25066"
    assert source.source_name == "NCBI GEO"
    assert source.url == (
        "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE25nnn/GSE25066/"
        "matrix/GSE25066_series_matrix.txt.gz"
    )
    assert source.status == "discovered"
    assert source.local_path is None
    assert source.checksum is None


def test_geo_directory_cache_avoids_repeat_network_calls(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GEOAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(geo_request())
        second = adapter.run(geo_request())

    assert call_count == 4
    assert first.cache_hit.accession_directory is False
    assert not any(first.cache_hit.resource_directories.values())
    assert second.cache_hit.accession_directory is True
    assert all(second.cache_hit.resource_directories.values())


def test_geo_download_records_sha256_and_reuses_verified_cache(
    tmp_path: Path,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if request.url.path.endswith("GSE25066_Genelist_weights.txt.gz"):
            return httpx.Response(200, content=SMALL_FILE, request=request)
        return standard_handler(request)

    request = geo_request(
        resource_types=[GEOResourceType.SUPPLEMENT],
        max_files_per_type=1,
        download=True,
        max_download_bytes=10_000,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GEOAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(request)
        second = adapter.run(request)

    expected_sha256 = hashlib.sha256(SMALL_FILE).hexdigest()
    first_source = first.source_items[0]
    second_source = second.source_items[0]
    assert call_count == 3
    assert first_source.status == "downloaded"
    assert first_source.checksum == f"sha256:{expected_sha256}"
    assert Path(first_source.local_path or "").read_bytes() == SMALL_FILE
    assert second_source.status == "cached"
    assert second_source.local_path == first_source.local_path
    assert second.resources[0].file_size == len(SMALL_FILE)


def test_geo_detects_tampering_in_cached_download(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("GSE25066_Genelist_weights.txt.gz"):
            return httpx.Response(200, content=SMALL_FILE, request=request)
        return standard_handler(request)

    request = geo_request(
        resource_types=[GEOResourceType.SUPPLEMENT],
        max_files_per_type=1,
        download=True,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GEOAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(request)
        Path(first.source_items[0].local_path or "").write_bytes(b"tampered")
        with pytest.raises(GEOAdapterError) as exc_info:
            adapter.run(request)

    assert exc_info.value.code == GEOErrorCode.CHECKSUM_MISMATCH


def test_geo_rejects_oversized_download_before_writing_file(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("GSE25066_Genelist_weights.txt.gz"):
            return httpx.Response(200, content=b"x" * 1_000, request=request)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(
                geo_request(
                    resource_types=[GEOResourceType.SUPPLEMENT],
                    max_files_per_type=1,
                    download=True,
                    max_download_bytes=100,
                )
            )

    assert exc_info.value.code == GEOErrorCode.DOWNLOAD_TOO_LARGE
    assert not list((tmp_path / "files").rglob("*.part"))


@pytest.mark.parametrize(
    ("accession", "bucket"),
    [
        ("GSE1", "GSEnnn"),
        ("GSE999", "GSEnnn"),
        ("GSE1000", "GSE1nnn"),
        ("GSE25066", "GSE25nnn"),
        ("GSE76360", "GSE76nnn"),
    ],
)
def test_geo_accession_bucket_matches_ncbi_directory_rule(
    accession: str, bucket: str
) -> None:
    assert GEOAdapter.accession_bucket(accession) == bucket


@pytest.mark.parametrize("accession", ["GPL96", "GSE0", "GSE25A66", "25066"])
def test_geo_invalid_accession_is_rejected_before_network(
    tmp_path: Path, accession: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid accession must not call GEO")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(
                geo_request(accession=accession)
            )

    assert exc_info.value.code == GEOErrorCode.INVALID_ACCESSION


def test_geo_invalid_plan_is_rejected_before_network(tmp_path: Path) -> None:
    request = geo_request()
    request.search_plan.plans[0] = SearchPlanItem(
        source="GDC", goal="获取 TCGA 数据", priority=1
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid plan must not call GEO")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(request)

    assert exc_info.value.code == GEOErrorCode.INVALID_PLAN


def test_geo_accession_not_found_is_distinct_from_network_failure(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(geo_request())

    assert exc_info.value.code == GEOErrorCode.ACCESSION_NOT_FOUND
    assert exc_info.value.http_status == 404
    assert exc_info.value.retryable is False


def test_geo_missing_requested_resource_has_specific_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/GSE25066/"):
            return html_response(request, "matrix/")
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(
                geo_request(resource_types=[GEOResourceType.SOFT])
            )

    assert exc_info.value.code == GEOErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.http_status == 404


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (429, GEOErrorCode.RATE_LIMITED, True),
        (503, GEOErrorCode.REMOTE_ERROR, True),
        (403, GEOErrorCode.REMOTE_ERROR, False),
    ],
)
def test_geo_http_failures_are_classified(
    tmp_path: Path,
    status_code: int,
    expected_code: GEOErrorCode,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(geo_request())

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.upstream_status == status_code


def test_geo_timeout_is_retryable_network_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GEOAdapterError) as exc_info:
            GEOAdapter(cache_dir=tmp_path, client=client).run(geo_request())

    assert exc_info.value.code == GEOErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_geo_ignores_parent_external_and_manifest_links(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/GSE25066/"):
            return html_response(request, "suppl/")
        return html_response(
            request,
            "../",
            "/geo/series/GSE25nnn/GSE25066/",
            "https://example.org/unsafe.tar",
            "filelist.txt",
            "valid supplement.txt.gz",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GEOAdapter(cache_dir=tmp_path, client=client).run(
            geo_request(resource_types=[GEOResourceType.SUPPLEMENT])
        )

    assert [resource.file_name for resource in result.resources] == [
        "valid supplement.txt.gz"
    ]
    assert result.resources[0].download_url.endswith("valid%20supplement.txt.gz")
