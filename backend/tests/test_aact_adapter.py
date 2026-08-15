from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from backend.app.models import SearchPlan, SearchPlanItem
from backend.app.sources.aact import (
    AACTAdapterError,
    AACTClinicalTrialsAdapter,
    AACTErrorCode,
)
from backend.app.sources.aact.models import (
    AACTAdapterOptions,
    AACTAdapterRequest,
    AACTTableName,
    TrialResultsStatus,
)


RESULTS_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT01104584",
            "briefTitle": "Breast MRI Study",
            "officialTitle": "A Breast Cancer MRI Study",
        },
        "statusModule": {"overallStatus": "COMPLETED"},
        "conditionsModule": {
            "conditions": ["Breast Cancer"],
            "keywords": ["MRI"],
        },
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE3"],
            "enrollmentInfo": {"count": 460, "type": "ACTUAL"},
        },
        "armsInterventionsModule": {
            "interventions": [
                {
                    "type": "DRUG",
                    "name": "Gadobutrol",
                    "description": "Single intravenous injection",
                    "armGroupLabels": ["Gadobutrol"],
                }
            ]
        },
        "outcomesModule": {
            "primaryOutcomes": [
                {
                    "measure": "Sensitivity",
                    "description": "Detection sensitivity",
                    "timeFrame": "Immediately after imaging",
                }
            ],
            "secondaryOutcomes": [
                {"measure": "Specificity", "timeFrame": "Immediately after imaging"}
            ],
        },
        "eligibilityModule": {
            "eligibilityCriteria": "Adults with newly diagnosed breast cancer",
            "healthyVolunteers": False,
            "sex": "FEMALE",
            "minimumAge": "18 Years",
        },
    },
    "resultsSection": {
        "outcomeMeasuresModule": {
            "outcomeMeasures": [
                {
                    "type": "PRIMARY",
                    "title": "Difference in sensitivity",
                    "paramType": "MEAN",
                    "unitOfMeasure": "percent",
                    "classes": [
                        {
                            "title": "Reader 1",
                            "categories": [
                                {
                                    "title": "All participants",
                                    "measurements": [
                                        {
                                            "groupId": "OG000",
                                            "value": "15.2",
                                            "lowerLimit": "11.8",
                                            "upperLimit": "18.7",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    },
    "derivedSection": {
        "conditionBrowseModule": {
            "meshes": [{"id": "D001943", "term": "Breast Neoplasms"}]
        }
    },
    "hasResults": True,
}

NO_RESULTS_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT03751449",
            "briefTitle": "Breast Cancer Feasibility Study",
        },
        "statusModule": {"overallStatus": "RECRUITING"},
        "conditionsModule": {"conditions": ["Breast Cancer"]},
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["NA"],
            "enrollmentInfo": {"count": 20, "type": "ESTIMATED"},
        },
        "armsInterventionsModule": {
            "interventions": [
                {"type": "OTHER", "name": "Feasibility intervention"}
            ]
        },
        "outcomesModule": {
            "primaryOutcomes": [
                {"measure": "Feasibility", "timeFrame": "12 months"}
            ]
        },
        "eligibilityModule": {
            "eligibilityCriteria": "Adults with breast cancer",
            "healthyVolunteers": False,
            "sex": "ALL",
        },
    },
    "hasResults": False,
}

SEARCH_RESPONSE = {
    "totalCount": 16709,
    "studies": [RESULTS_STUDY, NO_RESULTS_STUDY],
    "nextPageToken": "NEXT_TOKEN_001",
}


def aact_request(**option_overrides: object) -> AACTAdapterRequest:
    options: dict[str, object] = {"max_trials": 2}
    options.update(option_overrides)
    return AACTAdapterRequest(
        search_plan=SearchPlan(
            task_id="task_aact_001",
            plans=[
                SearchPlanItem(
                    source="AACT/ClinicalTrials.gov",
                    goal="获取乳腺癌临床试验多关系原始表",
                    priority=1,
                    mode="live",
                )
            ],
        ),
        options=AACTAdapterOptions(**options),
    )


def json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload, request=request)


def standard_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.url.path == "/api/v2/studies"
    assert "breast-research-data-agent" not in request.headers["user-agent"]
    assert request.url.params["query.cond"] == "Breast Cancer"
    assert request.url.params["pageSize"] == "2"
    assert request.url.params["format"] == "json"
    assert request.url.params["countTotal"] == "true"
    return json_response(request, SEARCH_RESPONSE)


def table_by_name(result: object, table_name: AACTTableName) -> object:
    return next(table for table in result.tables if table.table_name == table_name)


def test_aact_maps_breast_trials_to_required_relational_tables(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
            aact_request()
        )

    assert len(requests) == 1
    assert result.condition == "Breast Cancer"
    assert result.total_count == 16709
    assert result.next_page_token == "NEXT_TOKEN_001"
    assert result.search_request.parameters["query.cond"] == "Breast Cancer"
    assert {table.table_name for table in result.tables} == set(AACTTableName)

    assert [trial.nct_id for trial in result.trials] == [
        "NCT01104584",
        "NCT03751449",
    ]
    assert all(trial.trial_id == trial.nct_id for trial in result.trials)
    assert result.trials[0].results_status == TrialResultsStatus.AVAILABLE
    assert result.trials[1].results_status == TrialResultsStatus.NOT_REPORTED
    assert result.trials[0].raw_study == RESULTS_STUDY
    assert result.trials[1].raw_study == NO_RESULTS_STUDY

    studies = table_by_name(result, AACTTableName.STUDIES)
    assert studies.row_count == 2
    assert studies.rows[0]["protocolSection"] == RESULTS_STUDY["protocolSection"]
    conditions = table_by_name(result, AACTTableName.CONDITIONS)
    assert conditions.row_count == 2
    assert conditions.rows[0]["name"] == "Breast Cancer"
    interventions = table_by_name(result, AACTTableName.INTERVENTIONS)
    assert interventions.rows[0]["name"] == "Gadobutrol"
    eligibility = table_by_name(result, AACTTableName.ELIGIBILITIES)
    assert eligibility.rows[0]["eligibilityCriteria"].startswith("Adults")
    outcomes = table_by_name(result, AACTTableName.OUTCOMES)
    assert outcomes.row_count == 3
    assert outcomes.rows[0]["outcome_type"] == "primary"
    measurements = table_by_name(result, AACTTableName.OUTCOME_MEASUREMENTS)
    assert measurements.row_count == 1
    assert measurements.rows[0]["measurement"]["value"] == "15.2"
    assert measurements.rows[0]["outcome_title"] == "Difference in sensitivity"

    for table in result.tables:
        for row in table.rows:
            assert row["nct_id"] == row["trial_id"]
            assert row["source_id"] == f"clinicaltrials:{row['nct_id']}"

    serialized = json.dumps(result.model_dump(mode="json")).casefold()
    assert "negative_result" not in serialized
    assert "no_efficacy" not in serialized


def test_aact_source_items_point_to_verified_raw_trials(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
            aact_request()
        )

    assert len(result.source_items) == 2
    assert all(source.status == "retrieved" for source in result.source_items)
    for source in result.source_items:
        assert source.source_id == f"clinicaltrials:{source.accession}"
        assert source.url == (
            f"https://clinicaltrials.gov/api/v2/studies/{source.accession}"
        )
        path = Path(source.local_path or "")
        assert path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert source.checksum == f"sha256:{digest}"


def test_aact_cache_avoids_repeat_network_calls(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(aact_request())
        second = adapter.run(aact_request())

    assert call_count == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert all(source.status == "cached" for source in second.source_items)


def test_aact_detects_tampering_in_trial_cache(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        adapter = AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client)
        first = adapter.run(aact_request())
        Path(first.source_items[0].local_path or "").write_text("{}", encoding="utf-8")
        with pytest.raises(AACTAdapterError) as exc_info:
            adapter.run(aact_request())

    assert exc_info.value.code == AACTErrorCode.CACHE_ERROR


def test_aact_table_limits_are_explicit(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(standard_handler)) as client:
        result = AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
            aact_request(max_rows_per_table=1)
        )

    studies = table_by_name(result, AACTTableName.STUDIES)
    assert studies.row_count == 1
    assert studies.upstream_row_count == 2
    assert studies.truncated is True
    measurements = table_by_name(result, AACTTableName.OUTCOME_MEASUREMENTS)
    assert measurements.row_count == 1
    assert measurements.upstream_row_count == 1
    assert measurements.truncated is False


def test_aact_query_terms_and_page_token_are_forwarded(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query.term"] == "AREA[NCTId]NCT01104584"
        assert request.url.params["pageToken"] == "TOKEN-2"
        return standard_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
            aact_request(
                query_terms="AREA[NCTId]NCT01104584",
                page_token="TOKEN-2",
            )
        )


def test_aact_invalid_plan_is_rejected_before_network(tmp_path: Path) -> None:
    request = aact_request()
    request.search_plan.plans[0] = SearchPlanItem(
        source="cBioPortal", goal="获取基因组队列", priority=1
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid plan must not call ClinicalTrials.gov")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(request)

    assert exc_info.value.code == AACTErrorCode.INVALID_PLAN


def test_aact_invalid_query_is_rejected_before_network(tmp_path: Path) -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid query must not call ClinicalTrials.gov")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
                aact_request(query_terms="breast\u0000cancer")
            )

    assert exc_info.value.code == AACTErrorCode.INVALID_QUERY


def test_aact_no_studies_is_not_a_network_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(request, {"totalCount": 0, "studies": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
                aact_request()
            )

    assert exc_info.value.code == AACTErrorCode.NO_STUDIES
    assert exc_info.value.http_status == 404
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, AACTErrorCode.INVALID_QUERY, False),
        (429, AACTErrorCode.RATE_LIMITED, True),
        (503, AACTErrorCode.REMOTE_ERROR, True),
    ],
)
def test_aact_http_failures_are_classified(
    tmp_path: Path,
    status_code: int,
    expected_code: AACTErrorCode,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
                aact_request()
            )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.upstream_status == status_code


def test_aact_timeout_is_retryable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
                aact_request()
            )

    assert exc_info.value.code == AACTErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    "payload",
    [
        [SEARCH_RESPONSE],
        {"totalCount": "2", "studies": [RESULTS_STUDY]},
        {"totalCount": 1, "studies": "not-a-list"},
    ],
)
def test_aact_rejects_invalid_response_shapes(
    tmp_path: Path, payload: object
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(request, payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AACTAdapterError) as exc_info:
            AACTClinicalTrialsAdapter(cache_dir=tmp_path, client=client).run(
                aact_request()
            )

    assert exc_info.value.code == AACTErrorCode.INVALID_RESPONSE
