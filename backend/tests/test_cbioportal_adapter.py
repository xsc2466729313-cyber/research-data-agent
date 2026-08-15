from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from backend.app.models import SearchPlan, SearchPlanItem
from backend.app.sources.cbioportal import (
    CBioPortalAdapter,
    CBioPortalAdapterError,
    CBioPortalErrorCode,
)
from backend.app.sources.cbioportal.models import (
    CBioPortalAdapterOptions,
    CBioPortalAdapterRequest,
    CBioPortalTableType,
)


STUDY = {
    "studyId": "brca_metabric",
    "cancerTypeId": "brca",
    "name": "Breast Cancer (METABRIC, Nature 2012 & Nat Commun 2016)",
    "description": "Targeted sequencing of primary breast tumors.",
    "publicStudy": True,
    "pmid": "27161491,30867590,22522925",
    "allSampleCount": 2509,
    "referenceGenome": "hg19",
}
PROFILES = [
    {
        "molecularProfileId": "brca_metabric_cna",
        "studyId": "brca_metabric",
        "molecularAlterationType": "COPY_NUMBER_ALTERATION",
        "datatype": "DISCRETE",
        "name": "Putative copy-number alterations",
    },
    {
        "molecularProfileId": "brca_metabric_mutations",
        "studyId": "brca_metabric",
        "molecularAlterationType": "MUTATION_EXTENDED",
        "datatype": "MAF",
        "name": "Mutations",
    },
]
SAMPLE_LISTS = [
    {
        "sampleListId": "brca_metabric_all",
        "studyId": "brca_metabric",
        "category": "all_cases_in_study",
        "name": "All samples",
        "sampleCount": 2509,
    },
    {
        "sampleListId": "brca_metabric_cna",
        "studyId": "brca_metabric",
        "category": "all_cases_with_cna_data",
        "name": "Samples with CNA data",
        "sampleCount": 2173,
    },
    {
        "sampleListId": "brca_metabric_sequenced",
        "studyId": "brca_metabric",
        "category": "all_cases_with_mutation_data",
        "name": "Samples with mutation data",
        "sampleCount": 2433,
    },
]
GENES = [
    {"entrezGeneId": 2064, "hugoGeneSymbol": "ERBB2", "type": "protein-coding"},
    {"entrezGeneId": 5290, "hugoGeneSymbol": "PIK3CA", "type": "protein-coding"},
    {"entrezGeneId": 7157, "hugoGeneSymbol": "TP53", "type": "protein-coding"},
]
MUTATIONS = [
    {
        "sampleId": "MB-0005",
        "patientId": "MB-0005",
        "studyId": "brca_metabric",
        "molecularProfileId": "brca_metabric_mutations",
        "entrezGeneId": 5290,
        "gene": GENES[1],
        "proteinChange": "H1047R",
        "mutationType": "Missense_Mutation",
        "ncbiBuild": "GRCh37",
    },
    {
        "sampleId": "MB-0006",
        "patientId": "MB-0006",
        "studyId": "brca_metabric",
        "molecularProfileId": "brca_metabric_mutations",
        "entrezGeneId": 7157,
        "gene": GENES[2],
        "proteinChange": "R248Q",
        "mutationType": "Missense_Mutation",
        "ncbiBuild": "GRCh37",
    },
]
CNA_ROWS = [
    {
        "sampleId": "MB-0000",
        "patientId": "MB-0000",
        "studyId": "brca_metabric",
        "molecularProfileId": "brca_metabric_cna",
        "entrezGeneId": 2064,
        "gene": GENES[0],
        "alteration": 2,
    },
    {
        "sampleId": "MB-0001",
        "patientId": "MB-0001",
        "studyId": "brca_metabric",
        "molecularProfileId": "brca_metabric_cna",
        "entrezGeneId": 5290,
        "gene": GENES[1],
        "alteration": 0,
    },
    {
        "sampleId": "MB-0002",
        "patientId": "MB-0002",
        "studyId": "brca_metabric",
        "molecularProfileId": "brca_metabric_cna",
        "entrezGeneId": 7157,
        "gene": GENES[2],
        "alteration": -1,
    },
]
CLINICAL_SAMPLE = [
    {
        "sampleId": "MB-0000",
        "patientId": "MB-0000",
        "studyId": "brca_metabric",
        "patientAttribute": False,
        "clinicalAttributeId": "HER2_STATUS",
        "value": "Negative",
    },
    {
        "sampleId": "MB-0000",
        "patientId": "MB-0000",
        "studyId": "brca_metabric",
        "patientAttribute": False,
        "clinicalAttributeId": "GRADE",
        "value": "3",
    },
]
CLINICAL_PATIENT = [
    {
        "patientId": "MB-0000",
        "studyId": "brca_metabric",
        "patientAttribute": True,
        "clinicalAttributeId": "OS_STATUS",
        "value": "0:LIVING",
    },
    {
        "patientId": "MB-0000",
        "studyId": "brca_metabric",
        "patientAttribute": True,
        "clinicalAttributeId": "OS_MONTHS",
        "value": "140.5",
    },
]


def cbioportal_request(**option_overrides: object) -> CBioPortalAdapterRequest:
    return CBioPortalAdapterRequest(
        search_plan=SearchPlan(
            task_id="task_cbioportal_001",
            plans=[
                SearchPlanItem(
                    source="cBioPortal",
                    goal="获取 METABRIC 临床、突变和拷贝数原始表",
                    priority=1,
                    mode="live",
                )
            ],
        ),
        options=CBioPortalAdapterOptions(**option_overrides),
    )


def json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request)


def standard_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/studies/brca_metabric":
        return json_response(request, STUDY)
    if path == "/api/studies/brca_metabric/molecular-profiles":
        return json_response(request, PROFILES)
    if path == "/api/studies/brca_metabric/sample-lists":
        return json_response(request, SAMPLE_LISTS)
    if path == "/api/genes/fetch":
        assert json.loads(request.content) == ["ERBB2", "PIK3CA", "TP53"]
        assert request.url.params["geneIdType"] == "HUGO_GENE_SYMBOL"
        return json_response(request, GENES)
    if path.endswith("/brca_metabric_mutations/mutations/fetch"):
        body = json.loads(request.content)
        assert body["sampleListId"] == "brca_metabric_sequenced"
        assert body["entrezGeneIds"] == [2064, 5290, 7157]
        return json_response(request, MUTATIONS)
    if path.endswith("/brca_metabric_cna/discrete-copy-number/fetch"):
        body = json.loads(request.content)
        assert body["sampleListId"] == "brca_metabric_cna"
        assert request.url.params["discreteCopyNumberEventType"] == "ALL"
        return json_response(request, CNA_ROWS)
    if path == "/api/studies/brca_metabric/clinical-data":
        if request.url.params["clinicalDataType"] == "SAMPLE":
            return json_response(request, CLINICAL_SAMPLE)
        if request.url.params["clinicalDataType"] == "PATIENT":
            return json_response(request, CLINICAL_PATIENT)
    raise AssertionError(f"Unexpected request: {request.method} {request.url}")


def table_by_name(result: object, table_name: str) -> object:
    return next(table for table in result.tables if table.table_name == table_name)


def test_cbioportal_metabric_preserves_raw_metadata_tables_and_sources(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
            cbioportal_request(max_records_per_table=100)
        )

    assert len(requests) == 8
    assert result.study.study_id == "brca_metabric"
    assert result.study.raw_metadata == STUDY
    assert result.study.raw_metadata["pmid"] == "27161491,30867590,22522925"
    assert result.selection.mutation_profile_id == "brca_metabric_mutations"
    assert result.selection.cna_profile_id == "brca_metabric_cna"
    assert result.selection.mutation_sample_list_id == "brca_metabric_sequenced"
    assert result.selection.cna_sample_list_id == "brca_metabric_cna"
    assert {table.table_name for table in result.tables} == {
        "molecular_profiles",
        "sample_lists",
        "genes",
        "mutations",
        "discrete_cna",
        "clinical_sample",
        "clinical_patient",
    }

    clinical = table_by_name(result, "clinical_sample")
    assert clinical.rows == CLINICAL_SAMPLE
    assert "clinicalAttributeId" in clinical.raw_fields
    mutation = table_by_name(result, "mutations")
    assert mutation.rows[0]["proteinChange"] == "H1047R"
    assert mutation.request.body["sampleListId"] == "brca_metabric_sequenced"
    cna = table_by_name(result, "discrete_cna")
    assert cna.rows[0]["gene"]["hugoGeneSymbol"] == "ERBB2"
    assert cna.rows[0]["alteration"] == 2
    assert "her2_status" not in cna.rows[0]

    assert len(result.source_items) == 8
    assert all(source.accession == "brca_metabric" for source in result.source_items)
    assert all(source.status == "retrieved" for source in result.source_items)
    assert all(source.url.startswith("https://www.cbioportal.org/api/") for source in result.source_items)
    for source in result.source_items:
        payload_path = Path(source.local_path or "")
        assert payload_path.is_file()
        actual_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()
        assert source.checksum == f"sha256:{actual_sha256}"


def test_cbioportal_cache_avoids_repeat_network_and_marks_sources_cached(
    tmp_path: Path,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CBioPortalAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(cbioportal_request())
        second = adapter.run(cbioportal_request())

    assert call_count == 8
    assert not any(first.cache_hit.values())
    assert all(second.cache_hit.values())
    assert all(source.status == "cached" for source in second.source_items)


def test_cbioportal_clinical_only_skips_molecular_discovery(tmp_path: Path) -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
            cbioportal_request(tables=[CBioPortalTableType.CLINICAL_SAMPLE])
        )

    assert requested_paths == [
        "/api/studies/brca_metabric",
        "/api/studies/brca_metabric/clinical-data",
    ]
    assert [table.table_name for table in result.tables] == ["clinical_sample"]
    assert result.selection.genes == []


def test_cbioportal_marks_page_limited_tables_as_truncated(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
            cbioportal_request(
                tables=[CBioPortalTableType.CLINICAL_SAMPLE],
                max_records_per_table=2,
            )
        )

    table = result.tables[0]
    assert table.row_count == 2
    assert table.upstream_row_count is None
    assert table.truncated is True


def test_cbioportal_discrete_cna_limits_output_but_caches_full_response(
    tmp_path: Path,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
            cbioportal_request(
                tables=[CBioPortalTableType.DISCRETE_CNA],
                max_records_per_table=2,
            )
        )

    table = table_by_name(result, "discrete_cna")
    assert table.row_count == 2
    assert table.upstream_row_count == 3
    assert table.truncated is True
    cached_payload = json.loads(Path(table.source_item.local_path or "").read_text())
    assert cached_payload == CNA_ROWS


def test_cbioportal_detects_tampered_cache(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        adapter = CBioPortalAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(
            cbioportal_request(tables=[CBioPortalTableType.CLINICAL_SAMPLE])
        )
        Path(first.study.source_item.local_path or "").write_text(
            "{}", encoding="utf-8"
        )
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            adapter.run(
                cbioportal_request(tables=[CBioPortalTableType.CLINICAL_SAMPLE])
            )

    assert exc_info.value.code == CBioPortalErrorCode.CACHE_ERROR


@pytest.mark.parametrize("study_id", ["../secret", "BRCA/METABRIC", " brca metabric "])
def test_cbioportal_invalid_study_id_is_rejected_before_network(
    tmp_path: Path, study_id: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid study ID must not call cBioPortal")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request(study_id=study_id)
            )

    assert exc_info.value.code == CBioPortalErrorCode.INVALID_STUDY_ID


def test_cbioportal_invalid_plan_is_rejected_before_network(tmp_path: Path) -> None:
    request = cbioportal_request()
    request.search_plan.plans[0] = SearchPlanItem(
        source="GEO", goal="获取 GEO 数据", priority=1
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid plan must not call cBioPortal")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(request)

    assert exc_info.value.code == CBioPortalErrorCode.INVALID_PLAN


def test_cbioportal_study_not_found_is_distinct_from_network_failure(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request()
            )

    assert exc_info.value.code == CBioPortalErrorCode.STUDY_NOT_FOUND
    assert exc_info.value.http_status == 404
    assert exc_info.value.retryable is False


def test_cbioportal_missing_gene_is_explicit(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/genes/fetch":
            return json_response(request, GENES[:2])
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request(tables=[CBioPortalTableType.MUTATIONS])
            )

    assert exc_info.value.code == CBioPortalErrorCode.GENE_NOT_FOUND
    assert exc_info.value.details["missing_gene_symbols"] == ["TP53"]


def test_cbioportal_invalid_profile_override_is_explicit(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request(
                    tables=[CBioPortalTableType.MUTATIONS],
                    mutation_profile_id="brca_metabric_not_real",
                )
            )

    assert exc_info.value.code == CBioPortalErrorCode.INVALID_SELECTION


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, CBioPortalErrorCode.AUTH_REQUIRED, False),
        (429, CBioPortalErrorCode.RATE_LIMITED, True),
        (503, CBioPortalErrorCode.REMOTE_ERROR, True),
    ],
)
def test_cbioportal_http_failures_are_classified(
    tmp_path: Path,
    status_code: int,
    expected_code: CBioPortalErrorCode,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request()
            )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.upstream_status == status_code


def test_cbioportal_timeout_is_retryable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request()
            )

    assert exc_info.value.code == CBioPortalErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_cbioportal_rejects_wrong_json_shape(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(request, [STUDY])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CBioPortalAdapterError) as exc_info:
            CBioPortalAdapter(cache_dir=tmp_path, client=client).run(
                cbioportal_request()
            )

    assert exc_info.value.code == CBioPortalErrorCode.INVALID_RESPONSE
