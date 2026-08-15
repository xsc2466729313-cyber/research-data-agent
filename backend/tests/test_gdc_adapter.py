from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from backend.app.models import ResearchSpec, SearchPlan, SearchPlanItem
from backend.app.sources.gdc import GDCAdapter, GDCAdapterError, GDCErrorCode
from backend.app.sources.gdc.models import GDCAdapterOptions, GDCAdapterRequest


FILE_BYTES = b"stage-01-gdc-file\n"
FILE_MD5 = hashlib.md5(FILE_BYTES, usedforsecurity=False).hexdigest()
FILE_ID = "65b455f3-fcfb-4e50-95d8-7c513d94f0a6"


def adapter_request(**option_overrides: object) -> GDCAdapterRequest:
    return GDCAdapterRequest(
        research_spec=ResearchSpec(
            task_id="task_gdc_001",
            research_goal="研究 TCGA-BRCA 乳腺癌临床与组学数据",
            disease="Breast Cancer",
            genes=["ERBB2", "PIK3CA"],
            required_data_types=["clinical", "mutation"],
        ),
        search_plan=SearchPlan(
            task_id="task_gdc_001",
            plans=[
                SearchPlanItem(
                    source="GDC",
                    goal="获取 TCGA-BRCA 临床与组学文件",
                    priority=1,
                )
            ],
        ),
        options=GDCAdapterOptions(**option_overrides),
    )


def project_response() -> dict[str, object]:
    return {
        "data": {
            "hits": [
                {
                    "id": "TCGA-BRCA",
                    "project_id": "TCGA-BRCA",
                    "name": "Breast Invasive Carcinoma",
                    "state": "open",
                    "released": True,
                    "primary_site": ["Breast"],
                    "disease_type": ["Ductal and Lobular Neoplasms"],
                    "summary": {"case_count": 1098},
                }
            ]
        }
    }


def files_response(
    *, md5sum: str = FILE_MD5, file_size: int = len(FILE_BYTES)
) -> dict[str, object]:
    return {
        "data": {
            "hits": [
                {
                    "id": FILE_ID,
                    "file_id": FILE_ID,
                    "file_name": "clinical.xml",
                    "md5sum": md5sum,
                    "file_size": file_size,
                    "state": "released",
                    "access": "open",
                    "data_category": "Clinical",
                    "data_type": "Clinical Supplement",
                    "data_format": "BCR XML",
                    "experimental_strategy": None,
                }
            ]
        }
    }


def response_json(request: httpx.Request, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request)


def test_gdc_discovery_builds_official_filters_and_source_items(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            payload = json.loads(request.content)
            assert payload["size"] == 3
            assert payload["sort"] == "file_size:asc"
            filters = payload["filters"]["content"]
            assert any(
                item["content"]["field"] == "cases.project.project_id"
                and item["content"]["value"] == ["TCGA-BRCA"]
                for item in filters
            )
            assert any(
                item["content"]["field"] == "files.access"
                and item["content"]["value"] == ["open"]
                for item in filters
            )
            return response_json(request, files_response())
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GDCAdapter(cache_dir=tmp_path, client=client).run(
            adapter_request(max_files=3)
        )

    assert len(requests) == 2
    assert result.project.project_id == "TCGA-BRCA"
    assert result.project.case_count == 1098
    assert result.cache_hit.project_metadata is False
    assert result.cache_hit.file_metadata is False
    assert len(result.files) == 1
    source = result.source_items[0]
    assert source.source_id == f"gdc:{FILE_ID}"
    assert source.accession == "TCGA-BRCA"
    assert source.url == f"https://api.gdc.cancer.gov/data/{FILE_ID}"
    assert source.checksum == f"md5:{FILE_MD5}"
    assert source.status == "discovered"
    assert source.local_path is None


def test_gdc_metadata_cache_avoids_repeat_network_calls(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            return response_json(request, files_response())
        raise AssertionError(f"Unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GDCAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(adapter_request())
        second = adapter.run(adapter_request())

    assert first.cache_hit.project_metadata is False
    assert first.cache_hit.file_metadata is False
    assert second.cache_hit.project_metadata is True
    assert second.cache_hit.file_metadata is True
    assert call_count == 2


def test_gdc_download_verifies_md5_and_reuses_cached_file(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            return response_json(request, files_response())
        if request.url.path == f"/data/{FILE_ID}":
            return httpx.Response(200, content=FILE_BYTES, request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GDCAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(adapter_request(download=True, max_download_bytes=10_000))
        second = adapter.run(adapter_request(download=True, max_download_bytes=10_000))

    first_source = first.source_items[0]
    second_source = second.source_items[0]
    assert first_source.status == "downloaded"
    assert second_source.status == "cached"
    assert first_source.local_path == second_source.local_path
    assert Path(first_source.local_path).read_bytes() == FILE_BYTES
    assert call_count == 3


def test_gdc_rejects_download_above_configured_limit(tmp_path: Path) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            return response_json(request, files_response(file_size=1000))
        raise AssertionError("The data endpoint must not be called for an oversized file")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(
                adapter_request(download=True, max_download_bytes=100)
            )

    assert exc_info.value.code == GDCErrorCode.DOWNLOAD_TOO_LARGE
    assert all(not path.startswith("/data/") for path in requested_paths)


def test_gdc_checksum_mismatch_is_explicit(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            return response_json(request, files_response(md5sum="0" * 32))
        if request.url.path == f"/data/{FILE_ID}":
            return httpx.Response(200, content=FILE_BYTES, request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(
                adapter_request(download=True)
            )

    assert exc_info.value.code == GDCErrorCode.CHECKSUM_MISMATCH
    assert exc_info.value.details["expected"] == "0" * 32


def test_gdc_invalid_plan_is_rejected_before_network(tmp_path: Path) -> None:
    request = adapter_request()
    request.search_plan.plans[0] = SearchPlanItem(
        source="GEO", goal="获取 GEO 数据", priority=1
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Network must not be called for an invalid plan")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(request)

    assert exc_info.value.code == GDCErrorCode.INVALID_PLAN


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, GDCErrorCode.AUTH_REQUIRED, False),
        (429, GDCErrorCode.RATE_LIMITED, True),
        (503, GDCErrorCode.API_ERROR, True),
    ],
)
def test_gdc_http_failures_are_classified(
    tmp_path: Path,
    status_code: int,
    expected_code: GDCErrorCode,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(adapter_request())

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.upstream_status == status_code


def test_gdc_timeout_is_classified_as_retryable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(adapter_request())

    assert exc_info.value.code == GDCErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_gdc_project_not_found_is_distinct_from_network_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response_json(request, {"data": {"hits": []}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GDCAdapterError) as exc_info:
            GDCAdapter(cache_dir=tmp_path, client=client).run(adapter_request())

    assert exc_info.value.code == GDCErrorCode.PROJECT_NOT_FOUND
    assert exc_info.value.http_status == 404

