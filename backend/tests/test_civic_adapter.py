from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from backend.app.models import ResponseDomain, SearchPlan, SearchPlanItem
from backend.app.sources.civic import CIViCAdapter, CIViCAdapterError, CIViCErrorCode
from backend.app.sources.civic.models import (
    CIViCAdapterOptions,
    CIViCAdapterRequest,
    CIViCEvidenceLevel,
    CIViCEvidenceType,
    CIViCTableName,
)


EVIDENCE_NODE = {
    "id": 7316,
    "name": "EID7316",
    "link": "/evidence/7316",
    "status": "ACCEPTED",
    "description": "PIK3CA-mutated breast cancer evidence statement.",
    "evidenceType": "PREDICTIVE",
    "evidenceLevel": "A",
    "evidenceRating": 5,
    "evidenceDirection": "SUPPORTS",
    "significance": "SENSITIVITYRESPONSE",
    "variantOrigin": "SOMATIC",
    "therapyInteractionType": "COMBINATION",
    "disease": {
        "id": 22,
        "doid": "1612",
        "name": "Breast Cancer",
        "displayName": "Breast Cancer",
        "diseaseAliases": ["Breast Tumor"],
        "diseaseUrl": "https://www.disease-ontology.org/?id=DOID:1612",
        "link": "/diseases/22",
        "deprecated": False,
    },
    "therapies": [
        {
            "id": 570,
            "name": "Alpelisib",
            "ncitId": "C94214",
            "therapyAliases": ["Piqray"],
            "therapyUrl": "https://example.test/C94214",
            "link": "/therapies/570",
            "deprecated": False,
            "description": "PI3K inhibitor",
        },
        {
            "id": 54,
            "name": "Fulvestrant",
            "ncitId": "C1379",
            "therapyAliases": ["Faslodex"],
            "therapyUrl": "https://example.test/C1379",
            "link": "/therapies/54",
            "deprecated": False,
            "description": "Estrogen receptor antagonist",
        },
    ],
    "source": {
        "id": 2888,
        "sourceType": "PUBMED",
        "citationId": "31091374",
        "citation": "André et al., 2019",
        "title": "Alpelisib for PIK3CA-Mutated Breast Cancer",
        "authorString": "André et al.",
        "journal": "N Engl J Med",
        "publicationDate": "2019-5-16",
        "publicationYear": 2019,
        "pmcId": None,
        "sourceUrl": "http://www.ncbi.nlm.nih.gov/pubmed/31091374",
        "link": "/sources/2888",
        "retracted": False,
        "deprecated": False,
    },
    "molecularProfile": {
        "id": 5299,
        "name": "PIK3CA Q546E OR PIK3CA Q546R",
        "rawName": "#VID886 OR #VID888",
        "link": "/molecular-profiles/5299",
        "isComplex": True,
        "isMultiVariant": True,
        "deprecated": False,
        "molecularProfileAliases": [],
        "variants": [
            {
                "__typename": "GeneVariant",
                "id": 886,
                "name": "Q546E",
                "link": "/variants/886",
                "variantAliases": ["RS121913286"],
                "feature": {
                    "id": 37,
                    "name": "PIK3CA",
                    "fullName": "phosphatidylinositol 3-kinase catalytic alpha",
                    "featureType": "GENE",
                    "featureAliases": ["PI3K-alpha"],
                    "featureInstance": {
                        "__typename": "Gene",
                        "id": 37,
                        "name": "PIK3CA",
                        "entrezId": 5290,
                    },
                },
            },
            {
                "__typename": "GeneVariant",
                "id": 888,
                "name": "Q546R",
                "link": "/variants/888",
                "variantAliases": [],
                "feature": {
                    "id": 37,
                    "name": "PIK3CA",
                    "fullName": "phosphatidylinositol 3-kinase catalytic alpha",
                    "featureType": "GENE",
                    "featureAliases": ["PI3K-alpha"],
                    "featureInstance": {
                        "__typename": "Gene",
                        "id": 37,
                        "name": "PIK3CA",
                        "entrezId": 5290,
                    },
                },
            },
        ],
    },
}

SEARCH_RESPONSE = {
    "data": {
        "evidenceItems": {
            "totalCount": 316,
            "pageInfo": {"endCursor": "MQ", "hasNextPage": True},
            "nodes": [EVIDENCE_NODE],
        }
    }
}


def civic_request(**option_overrides: object) -> CIViCAdapterRequest:
    options: dict[str, object] = {"max_evidence_items": 1}
    options.update(option_overrides)
    return CIViCAdapterRequest(
        search_plan=SearchPlan(
            task_id="task_civic_001",
            plans=[
                SearchPlanItem(
                    source="CIViC",
                    goal="获取乳腺癌变异、药物和出版物证据关系",
                    priority=1,
                    mode="live",
                )
            ],
        ),
        options=CIViCAdapterOptions(**options),
    )


def json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request)


def standard_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.url.path == "/api/graphql"
    payload = json.loads(request.content)
    assert payload["variables"]["diseaseName"] == "Breast Cancer"
    assert payload["variables"]["first"] == 1
    assert "status: ACCEPTED" in payload["query"]
    assert "variantHgvs" not in payload["query"]
    return json_response(request, SEARCH_RESPONSE)


def table_by_name(result: object, table_name: CIViCTableName) -> object:
    return next(table for table in result.tables if table.table_name == table_name)


def test_civic_maps_accepted_evidence_to_traceable_relation_tables(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    assert len(requests) == 1
    assert result.response_domain == ResponseDomain.KNOWLEDGE_EVIDENCE
    assert result.status_filter == "ACCEPTED"
    assert result.total_count == 316
    assert result.next_cursor == "MQ"
    assert result.search_request.variables["diseaseName"] == "Breast Cancer"
    assert {table.table_name for table in result.tables} == set(CIViCTableName)

    evidence = result.evidence_items[0]
    assert evidence.civic_evidence_id == 7316
    assert evidence.evidence_id == "CIViC:EID7316"
    assert evidence.status == "ACCEPTED"
    assert evidence.disease_name == "Breast Cancer"
    assert evidence.therapy_names == ["Alpelisib", "Fulvestrant"]
    assert evidence.publication_id == "31091374"
    assert evidence.raw_evidence == EVIDENCE_NODE

    genes = table_by_name(result, CIViCTableName.GENES)
    assert genes.row_count == 1
    assert genes.rows[0]["gene_symbol"] == "PIK3CA"
    assert genes.rows[0]["entrez_id"] == 5290
    variants = table_by_name(result, CIViCTableName.VARIANTS)
    assert [row["civic_variant_id"] for row in variants.rows] == [886, 888]
    therapies = table_by_name(result, CIViCTableName.THERAPIES)
    assert [row["name"] for row in therapies.rows] == ["Alpelisib", "Fulvestrant"]
    sources = table_by_name(result, CIViCTableName.SOURCES)
    assert sources.rows[0]["citationId"] == "31091374"
    assert sources.rows[0]["citation"] == "André et al., 2019"

    relations = table_by_name(result, CIViCTableName.EVIDENCE_RELATIONS)
    assert relations.row_count == 1
    relation = relations.rows[0]
    assert relation["civic_disease_id"] == 22
    assert relation["gene_symbols"] == ["PIK3CA"]
    assert relation["civic_variant_ids"] == [886, 888]
    assert relation["civic_therapy_ids"] == [570, 54]
    assert relation["publication_id"] == "31091374"
    assert relation["relation_scope"] == "molecular_profile_context"
    assert relation["is_complex_molecular_profile"] is True

    for table in result.tables:
        for row in table.rows:
            assert row["raw_field"]
            assert "raw_value" in row


def test_civic_source_item_points_to_verified_raw_evidence(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    source = result.source_items[0]
    assert source.source_id == "civic:EID7316"
    assert source.accession == "EID7316"
    assert source.url == "https://civicdb.org/evidence/7316"
    assert source.status == "retrieved"
    path = Path(source.local_path or "")
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == EVIDENCE_NODE
    assert source.checksum == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_civic_cache_avoids_repeat_network_calls(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CIViCAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(civic_request())
        second = adapter.run(civic_request())

    assert call_count == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.source_items[0].status == "cached"


def test_civic_detects_tampering_in_evidence_cache(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        adapter = CIViCAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(civic_request())
        Path(first.source_items[0].local_path or "").write_text("{}", encoding="utf-8")
        with pytest.raises(CIViCAdapterError) as exc_info:
            adapter.run(civic_request())

    assert exc_info.value.code == CIViCErrorCode.CACHE_ERROR


def test_civic_filters_and_cursor_are_forwarded(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["variables"] == {
            "diseaseName": "Breast Cancer",
            "first": 1,
            "after": "CURSOR-2",
            "molecularProfileName": "PIK3CA",
            "therapyName": "Alpelisib",
            "evidenceType": "PREDICTIVE",
            "evidenceLevel": "A",
        }
        return json_response(request, SEARCH_RESPONSE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        CIViCAdapter(cache_dir=tmp_path, client=client).run(
            civic_request(
                after_cursor="CURSOR-2",
                molecular_profile_name="PIK3CA",
                therapy_name="Alpelisib",
                evidence_type=CIViCEvidenceType.PREDICTIVE,
                evidence_level=CIViCEvidenceLevel.A,
            )
        )


def test_civic_table_limits_are_explicit(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = CIViCAdapter(cache_dir=tmp_path, client=client).run(
            civic_request(max_rows_per_table=1)
        )

    variants = table_by_name(result, CIViCTableName.VARIANTS)
    assert variants.row_count == 1
    assert variants.upstream_row_count == 2
    assert variants.truncated is True
    relations = table_by_name(result, CIViCTableName.EVIDENCE_RELATIONS)
    assert relations.row_count == 1
    assert relations.truncated is False


def test_civic_invalid_plan_is_rejected_before_network(tmp_path: Path) -> None:
    request = civic_request()
    request.search_plan.plans[0] = SearchPlanItem(
        source="AACT", goal="获取临床试验", priority=1
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid plan must not call CIViC")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(request)

    assert exc_info.value.code == CIViCErrorCode.INVALID_PLAN


def test_civic_invalid_query_is_rejected_before_network(tmp_path: Path) -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid query must not call CIViC")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(
                civic_request(therapy_name="Alpelisib\u0000")
            )

    assert exc_info.value.code == CIViCErrorCode.INVALID_QUERY


def test_civic_no_evidence_is_not_a_network_failure(tmp_path: Path) -> None:
    payload = {
        "data": {
            "evidenceItems": {
                "totalCount": 0,
                "pageInfo": {"endCursor": None, "hasNextPage": False},
                "nodes": [],
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(request, payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    assert exc_info.value.code == CIViCErrorCode.NO_EVIDENCE
    assert exc_info.value.http_status == 404
    assert exc_info.value.retryable is False


def test_civic_graphql_errors_are_classified_and_not_cached(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return json_response(
            request,
            {"errors": [{"message": "Schema changed"}], "data": None},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CIViCAdapter(cache_dir=tmp_path, client=client)
        for _ in range(2):
            with pytest.raises(CIViCAdapterError) as exc_info:
                adapter.run(civic_request())
            assert exc_info.value.code == CIViCErrorCode.GRAPHQL_ERROR

    assert call_count == 2
    assert not list(tmp_path.rglob("*.cache.json"))


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, CIViCErrorCode.INVALID_QUERY, False),
        (401, CIViCErrorCode.AUTHENTICATION_ERROR, False),
        (429, CIViCErrorCode.RATE_LIMITED, True),
        (503, CIViCErrorCode.REMOTE_ERROR, True),
    ],
)
def test_civic_http_failures_are_classified(
    tmp_path: Path,
    status_code: int,
    expected_code: CIViCErrorCode,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.upstream_status == status_code


def test_civic_timeout_is_retryable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    assert exc_info.value.code == CIViCErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    "payload",
    [
        [SEARCH_RESPONSE],
        {"data": None},
        {"data": {"evidenceItems": {"totalCount": "316", "nodes": []}}},
        {
            "data": {
                "evidenceItems": {
                    "totalCount": 1,
                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                    "nodes": "not-a-list",
                }
            }
        },
    ],
)
def test_civic_rejects_invalid_response_shapes(tmp_path: Path, payload: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(request, payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CIViCAdapterError) as exc_info:
            CIViCAdapter(cache_dir=tmp_path, client=client).run(civic_request())

    assert exc_info.value.code == CIViCErrorCode.INVALID_RESPONSE
