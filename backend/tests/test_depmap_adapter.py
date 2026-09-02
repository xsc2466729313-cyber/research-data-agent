from __future__ import annotations

import httpx
import pytest

from backend.app.sources.depmap import DepMapAdapter, DepMapAdapterError, DepMapErrorCode


BUNDLE = {
    "models": [
        {"ModelID": "ACH-000001", "CellLineName": "MCF7", "OncotreeLineage": "Breast"},
        {"ModelID": "ACH-000002", "CellLineName": "A549", "OncotreeLineage": "Lung"},
        {"ModelID": "ACH-000003", "CellLineName": "T47D", "OncotreeLineage": "Breast"},
    ],
    "sensitivity": [
        {"ModelID": "ACH-000001", "Drug": "Alpelisib", "AUC": 0.42, "IC50": 1.2},
        {"ModelID": "ACH-000002", "Drug": "Alpelisib", "AUC": 0.11, "IC50": 0.4},
    ],
}


def test_depmap_keeps_breast_lineage_and_preclinical_domain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == DepMapAdapter.DOWNLOADS_URL
        return httpx.Response(200, json=BUNDLE, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DepMapAdapter(client=client).search(task_id="task-depmap", drug="Alpelisib", max_records=50)

    assert {record.model_id for record in result.records} == {"ACH-000001", "ACH-000003"}
    assert all(record.response_domain == "preclinical_cell_line" for record in result.records)
    assert all(record.source_id.startswith("depmap:") for record in result.records)
    mcf7 = next(record for record in result.records if record.model_id == "ACH-000001")
    assert mcf7.auc == 0.42
    assert mcf7.ic50 == 1.2
    assert mcf7.drug == "Alpelisib"
    assert "preclinical_cell_line" in result.notice
    assert "pCR" in result.notice or "患者" in result.notice


def test_depmap_raises_when_no_breast_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"models": [{"ModelID": "ACH-9", "CellLineName": "A549", "OncotreeLineage": "Lung"}]},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DepMapAdapterError) as exc_info:
            DepMapAdapter(client=client).search(task_id="task-empty")

    assert exc_info.value.code == DepMapErrorCode.NO_RECORDS


def test_depmap_uses_official_figshare_release_when_portal_requires_verification() -> None:
    model_csv = (
        "ModelID,CellLineName,StrippedCellLineName,OncotreeLineage\n"
        "ACH-000001,MCF7,MCF7,Breast\n"
        "ACH-000002,A549,A549,Lung\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == DepMapAdapter.DOWNLOADS_URL:
            return httpx.Response(200, text="<html>Verification</html>", request=request)
        if url == DepMapAdapter.FIGSHARE_ARTICLE_API:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "name": "Model.csv",
                            "download_url": "https://ndownloader.figshare.com/files/1",
                            "computed_md5": "abc123",
                        }
                    ]
                },
                request=request,
            )
        if url == "https://ndownloader.figshare.com/files/1":
            return httpx.Response(200, text=model_csv, request=request)
        raise AssertionError(f"unexpected URL: {url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = DepMapAdapter(client=client).search(task_id="task-figshare")

    assert [record.model_id for record in result.records] == ["ACH-000001"]
    assert result.request_url == DepMapAdapter.FIGSHARE_ARTICLE_API
    assert any(item.source_id == "depmap:figshare:27993248:model" for item in result.source_items)
    assert "不补造" in result.notice
