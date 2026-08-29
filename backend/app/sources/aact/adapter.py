from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.app.models import SourceItem
from backend.app.sources.aact.errors import AACTAdapterError, AACTErrorCode
from backend.app.sources.aact.models import (
    AACTAdapterRequest,
    AACTAdapterResult,
    AACTRawTable,
    AACTRequestTrace,
    AACTTableName,
    AACTUnifiedTrial,
    TrialResultsStatus,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "aact"


@dataclass(frozen=True)
class _SearchPayload:
    payload: dict[str, Any]
    cache_hit: bool
    payload_path: Path
    sha256: str
    request: AACTRequestTrace


class AACTClinicalTrialsAdapter:
    API_BASE_URL = "https://clinicaltrials.gov/api/v2"
    STUDY_API_URL = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    STUDY_PAGE_URL = "https://clinicaltrials.gov/study/{nct_id}"
    NCT_ID_PATTERN = re.compile(r"^NCT\d{8}$")

    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        client: httpx.Client | None = None,
        timeout_seconds: float = 90.0,
        cache_ttl_seconds: int = 86_400,
        api_base_url: str = API_BASE_URL,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.api_base_url = api_base_url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

    def run(self, request: AACTAdapterRequest) -> AACTAdapterResult:
        self._validate_input(request)
        options = request.options
        if options.nct_id:
            return self._run_nct(request, options.nct_id)
        parameters: dict[str, Any] = {
            "query.cond": options.condition,
            "pageSize": options.max_trials,
            "format": "json",
            "countTotal": "true",
        }
        if options.query_terms:
            parameters["query.term"] = options.query_terms
        if options.page_token:
            parameters["pageToken"] = options.page_token

        search = self._acquire_search(
            parameters=parameters,
            refresh=options.refresh_cache,
        )
        studies = search.payload.get("studies")
        total_count = search.payload.get("totalCount")
        next_page_token = search.payload.get("nextPageToken")
        if not isinstance(studies, list) or not all(
            isinstance(study, dict) for study in studies
        ):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov response does not contain a studies list.",
            )
        if not isinstance(total_count, int) or total_count < 0:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov response has an invalid totalCount.",
            )
        if next_page_token is not None and not isinstance(next_page_token, str):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov response has an invalid nextPageToken.",
            )
        if len(studies) > options.max_trials:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov returned more studies than requested.",
                details={
                    "requested": options.max_trials,
                    "returned": len(studies),
                },
            )
        if not studies:
            raise AACTAdapterError(
                AACTErrorCode.NO_STUDIES,
                "ClinicalTrials.gov returned no trials for the requested query.",
                details={
                    "condition": options.condition,
                    "query_terms": options.query_terms,
                },
            )

        trials: list[AACTUnifiedTrial] = []
        table_rows: dict[AACTTableName, list[dict[str, Any]]] = {
            name: [] for name in AACTTableName
        }
        for raw_study in studies:
            trial = self._build_trial(
                task_id=request.search_plan.task_id,
                raw_study=raw_study,
                cache_hit=search.cache_hit,
                refresh=options.refresh_cache,
            )
            trials.append(trial)
            self._append_study_rows(
                raw_study=raw_study,
                trial=trial,
                table_rows=table_rows,
            )

        tables = [
            self._table(
                table_name=table_name,
                rows=table_rows[table_name],
                max_rows=options.max_rows_per_table,
            )
            for table_name in AACTTableName
        ]
        return AACTAdapterResult(
            task_id=request.search_plan.task_id,
            condition=options.condition,
            total_count=total_count,
            next_page_token=next_page_token,
            search_request=search.request,
            trials=trials,
            tables=tables,
            source_items=[trial.source_item for trial in trials],
            cache_hit=search.cache_hit,
            queried_at=datetime.now(timezone.utc),
            notice=(
                "原始记录来自 ClinicalTrials.gov v2 官方 API，并按 AACT 关系表语义拆分。"
                "results_status=not_reported 仅表示未发现结果区，绝不表示阴性结果或无疗效。"
            ),
        )

    def _validate_input(self, request: AACTAdapterRequest) -> None:
        if not any(
            plan.source.casefold()
            in {
                "aact",
                "clinicaltrials.gov",
                "clinicaltrials",
                "aact/clinicaltrials.gov",
            }
            for plan in request.search_plan.plans
        ):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_PLAN,
                "SearchPlan does not contain an AACT/ClinicalTrials.gov task.",
            )
        values = {
            "condition": request.options.condition,
            "query_terms": request.options.query_terms,
            "page_token": request.options.page_token,
        }
        invalid = {
            name: value
            for name, value in values.items()
            if value is not None
            and (
                not value
                or any(ord(character) < 32 for character in value)
            )
        }
        if invalid:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_QUERY,
                "AACT/ClinicalTrials.gov query contains invalid control characters.",
                details={"fields": sorted(invalid)},
            )

    def _acquire_search(
        self, *, parameters: dict[str, Any], refresh: bool
    ) -> _SearchPayload:
        url = f"{self.api_base_url}/studies"
        trace = AACTRequestTrace(method="GET", url=url, parameters=parameters)
        request_hash = self._request_hash(trace)
        payload_path = self.cache_dir / "responses" / f"{request_hash}.json"
        manifest_path = self.cache_dir / "responses" / f"{request_hash}.cache.json"
        if not refresh:
            cached = self._read_search_cache(
                payload_path=payload_path,
                manifest_path=manifest_path,
                trace=trace,
            )
            if cached is not None:
                return cached

        try:
            response = self.client.get(url, params=parameters)
        except httpx.TimeoutException as exc:
            raise AACTAdapterError(
                AACTErrorCode.TIMEOUT,
                "ClinicalTrials.gov search timed out.",
                retryable=True,
                details={"url": url},
            ) from exc
        except httpx.RequestError as exc:
            raise AACTAdapterError(
                AACTErrorCode.NETWORK_ERROR,
                "ClinicalTrials.gov network request failed.",
                retryable=True,
                details={"url": url, "error_type": type(exc).__name__},
            ) from exc
        self._raise_for_status(response, url=url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov returned non-JSON content.",
                details={"content_type": response.headers.get("content-type")},
            ) from exc
        if not isinstance(payload, dict):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov search response is not an object.",
            )
        sha256 = self._write_search_cache(
            payload_path=payload_path,
            manifest_path=manifest_path,
            payload=payload,
            trace=trace,
        )
        return _SearchPayload(
            payload=payload,
            cache_hit=False,
            payload_path=payload_path,
            sha256=sha256,
            request=trace,
        )

    def _build_trial(
        self,
        *,
        task_id: str,
        raw_study: dict[str, Any],
        cache_hit: bool,
        refresh: bool,
    ) -> AACTUnifiedTrial:
        protocol = self._required_dict(raw_study, "protocolSection", context="study")
        identification = self._required_dict(
            protocol, "identificationModule", context="protocolSection"
        )
        nct_id = identification.get("nctId")
        brief_title = identification.get("briefTitle")
        if not isinstance(nct_id, str) or not self.NCT_ID_PATTERN.fullmatch(nct_id):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                "ClinicalTrials.gov study has an invalid NCT ID.",
                details={"nct_id": nct_id},
            )
        if not isinstance(brief_title, str) or not brief_title:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov study {nct_id} has no brief title.",
            )

        raw_path, sha256 = self._write_trial_payload(
            nct_id=nct_id,
            raw_study=raw_study,
            refresh=refresh,
        )
        source_item = SourceItem(
            source_id=f"clinicaltrials:{nct_id}",
            task_id=task_id,
            source_name="ClinicalTrials.gov",
            source_type="database",
            accession=nct_id,
            url=self.STUDY_API_URL.format(nct_id=nct_id),
            file_type="json:study",
            local_path=self._display_path(raw_path),
            checksum=f"sha256:{sha256}",
            status="cached" if cache_hit else "retrieved",
        )
        status_module = self._optional_dict(protocol, "statusModule")
        design_module = self._optional_dict(protocol, "designModule")
        enrollment = self._optional_dict(design_module, "enrollmentInfo")
        phases = design_module.get("phases")
        if not isinstance(phases, list) or not all(
            isinstance(phase, str) for phase in phases
        ):
            phases = []
        enrollment_count = enrollment.get("count")
        if not isinstance(enrollment_count, int) or enrollment_count < 0:
            enrollment_count = None
        has_results = raw_study.get("hasResults")
        if not isinstance(has_results, bool):
            has_results = None
        return AACTUnifiedTrial(
            nct_id=nct_id,
            trial_id=nct_id,
            brief_title=brief_title,
            official_title=(
                identification.get("officialTitle")
                if isinstance(identification.get("officialTitle"), str)
                else None
            ),
            overall_status=(
                status_module.get("overallStatus")
                if isinstance(status_module.get("overallStatus"), str)
                else None
            ),
            study_type=(
                design_module.get("studyType")
                if isinstance(design_module.get("studyType"), str)
                else None
            ),
            phases=phases,
            enrollment_count=enrollment_count,
            has_results=has_results,
            results_status=self._results_status(raw_study),
            study_url=self.STUDY_PAGE_URL.format(nct_id=nct_id),
            raw_study=raw_study,
            source_item=source_item,
        )

    def _append_study_rows(
        self,
        *,
        raw_study: dict[str, Any],
        trial: AACTUnifiedTrial,
        table_rows: dict[AACTTableName, list[dict[str, Any]]],
    ) -> None:
        base = {
            "nct_id": trial.nct_id,
            "trial_id": trial.trial_id,
            "source_id": trial.source_item.source_id,
        }
        table_rows[AACTTableName.STUDIES].append(
            {
                **raw_study,
                **base,
                "results_status": trial.results_status.value,
            }
        )
        protocol = self._required_dict(raw_study, "protocolSection", context=trial.nct_id)

        conditions_module = self._optional_dict(protocol, "conditionsModule")
        conditions = self._value_list(
            conditions_module, "conditions", context=f"{trial.nct_id}.conditions"
        )
        for condition_index, condition in enumerate(conditions):
            table_rows[AACTTableName.CONDITIONS].append(
                {
                    **base,
                    "condition_index": condition_index,
                    "name": condition,
                    "condition": condition,
                }
            )

        arms_module = self._optional_dict(protocol, "armsInterventionsModule")
        interventions = self._object_list(
            arms_module,
            "interventions",
            context=f"{trial.nct_id}.interventions",
        )
        for intervention_index, intervention in enumerate(interventions):
            table_rows[AACTTableName.INTERVENTIONS].append(
                {**intervention, **base, "intervention_index": intervention_index}
            )

        eligibility = protocol.get("eligibilityModule")
        if eligibility is not None:
            if not isinstance(eligibility, dict):
                raise AACTAdapterError(
                    AACTErrorCode.INVALID_RESPONSE,
                    f"ClinicalTrials.gov {trial.nct_id} eligibilityModule is invalid.",
                )
            table_rows[AACTTableName.ELIGIBILITIES].append(
                {**eligibility, **base}
            )

        outcomes_module = self._optional_dict(protocol, "outcomesModule")
        for outcome_type, key in (
            ("primary", "primaryOutcomes"),
            ("secondary", "secondaryOutcomes"),
            ("other", "otherOutcomes"),
        ):
            outcomes = self._object_list(
                outcomes_module,
                key,
                context=f"{trial.nct_id}.{key}",
            )
            for outcome_index, outcome in enumerate(outcomes):
                table_rows[AACTTableName.OUTCOMES].append(
                    {
                        **outcome,
                        **base,
                        "outcome_type": outcome_type,
                        "outcome_index": outcome_index,
                    }
                )

        results_section = raw_study.get("resultsSection")
        if not isinstance(results_section, dict):
            return
        outcome_module = self._optional_dict(
            results_section, "outcomeMeasuresModule"
        )
        outcome_measures = self._object_list(
            outcome_module,
            "outcomeMeasures",
            context=f"{trial.nct_id}.outcomeMeasures",
        )
        for measure_index, measure in enumerate(outcome_measures):
            classes = self._object_list(
                measure,
                "classes",
                context=f"{trial.nct_id}.outcomeMeasures[{measure_index}].classes",
                allow_empty_string=True,
            )
            measure_metadata = {
                key: value for key, value in measure.items() if key != "classes"
            }
            for class_index, measure_class in enumerate(classes):
                categories = self._object_list(
                    measure_class,
                    "categories",
                    context=(
                        f"{trial.nct_id}.outcomeMeasures[{measure_index}]"
                        f".classes[{class_index}].categories"
                    ),
                    allow_empty_string=True,
                )
                class_metadata = {
                    key: value
                    for key, value in measure_class.items()
                    if key != "categories"
                }
                for category_index, category in enumerate(categories):
                    measurements = self._object_list(
                        category,
                        "measurements",
                        context=(
                            f"{trial.nct_id}.outcomeMeasures[{measure_index}]"
                            f".classes[{class_index}].categories[{category_index}]"
                            ".measurements"
                        ),
                        allow_empty_string=True,
                    )
                    category_metadata = {
                        key: value
                        for key, value in category.items()
                        if key != "measurements"
                    }
                    for measurement_index, measurement in enumerate(measurements):
                        table_rows[AACTTableName.OUTCOME_MEASUREMENTS].append(
                            {
                                **base,
                                "outcome_measure_index": measure_index,
                                "class_index": class_index,
                                "category_index": category_index,
                                "measurement_index": measurement_index,
                                "outcome_type": measure.get("type"),
                                "outcome_title": measure.get("title"),
                                "outcome_measure": measure_metadata,
                                "measure_class": class_metadata,
                                "category": category_metadata,
                                "measurement": measurement,
                            }
                        )

    @staticmethod
    def _results_status(raw_study: dict[str, Any]) -> TrialResultsStatus:
        has_results = raw_study.get("hasResults")
        has_results_section = isinstance(raw_study.get("resultsSection"), dict)
        if has_results is True and has_results_section:
            return TrialResultsStatus.AVAILABLE
        if has_results is False and not has_results_section:
            return TrialResultsStatus.NOT_REPORTED
        return TrialResultsStatus.INCONSISTENT

    @staticmethod
    def _table(
        *, table_name: AACTTableName, rows: list[dict[str, Any]], max_rows: int
    ) -> AACTRawTable:
        visible_rows = rows[:max_rows]
        return AACTRawTable(
            table_name=table_name,
            raw_fields=sorted({key for row in rows for key in row}),
            rows=visible_rows,
            row_count=len(visible_rows),
            upstream_row_count=len(rows),
            truncated=len(rows) > len(visible_rows),
        )

    def _run_nct(self, request: AACTAdapterRequest, nct_id: str) -> AACTAdapterResult:
        options = request.options
        url = self.STUDY_API_URL.format(nct_id=nct_id)
        try:
            response = self.client.get(url)
        except httpx.TimeoutException as exc:
            raise AACTAdapterError(
                AACTErrorCode.TIMEOUT,
                f"ClinicalTrials.gov study {nct_id} timed out.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise AACTAdapterError(
                AACTErrorCode.NETWORK_ERROR,
                f"ClinicalTrials.gov study {nct_id} request failed.",
                retryable=True,
            ) from exc
        if response.status_code >= 400:
            raise AACTAdapterError(
                AACTErrorCode.REMOTE_ERROR,
                f"ClinicalTrials.gov study {nct_id} returned HTTP {response.status_code}.",
                upstream_status=response.status_code,
            )
        try:
            raw_study = response.json()
        except ValueError as exc:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov study {nct_id} is not JSON.",
            ) from exc
        if not isinstance(raw_study, dict) or "protocolSection" not in raw_study:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov study {nct_id} has no protocolSection.",
            )
        trace = AACTRequestTrace(method="GET", url=url, parameters={"nctId": nct_id})
        trial = self._build_trial(
            task_id=request.search_plan.task_id,
            raw_study=raw_study,
            cache_hit=False,
            refresh=options.refresh_cache,
        )
        table_rows: dict[AACTTableName, list[dict[str, Any]]] = {name: [] for name in AACTTableName}
        self._append_study_rows(raw_study=raw_study, trial=trial, table_rows=table_rows)
        tables = [
            self._table(table_name=table_name, rows=table_rows[table_name], max_rows=options.max_rows_per_table)
            for table_name in AACTTableName
        ]
        return AACTAdapterResult(
            task_id=request.search_plan.task_id,
            condition=options.condition,
            total_count=1,
            next_page_token=None,
            search_request=trace,
            trials=[trial],
            tables=tables,
            source_items=[trial.source_item],
            cache_hit=False,
            queried_at=datetime.now(timezone.utc),
            notice=(
                f"已按官方 NCT 编号 {nct_id} 读取 ClinicalTrials.gov v2 研究记录。"
                "results_status=not_reported 仅表示未发现结果区。"
            ),
        )

    def _write_trial_payload(
        self,
        *,
        nct_id: str,
        raw_study: dict[str, Any],
        refresh: bool,
    ) -> tuple[Path, str]:
        payload_bytes = self._json_bytes(raw_study)
        sha256 = hashlib.sha256(payload_bytes).hexdigest()
        target = self.cache_dir / "trials" / nct_id / f"{sha256[:24]}.json"
        if target.is_file() and not refresh:
            actual_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_sha256 != sha256:
                raise AACTAdapterError(
                    AACTErrorCode.CACHE_ERROR,
                    f"Cached ClinicalTrials.gov study failed SHA-256 verification: {nct_id}",
                    details={"expected": sha256, "actual": actual_sha256},
                )
            return target, sha256
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload_bytes)
            temporary.replace(target)
        except OSError as exc:
            if temporary.is_file():
                temporary.unlink()
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"Could not write ClinicalTrials.gov study cache: {nct_id}",
            ) from exc
        return target, sha256

    def _read_search_cache(
        self,
        *,
        payload_path: Path,
        manifest_path: Path,
        trace: AACTRequestTrace,
    ) -> _SearchPayload | None:
        if not payload_path.exists() and not manifest_path.exists():
            return None
        if not payload_path.is_file() or not manifest_path.is_file():
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cache is incomplete: {payload_path.name}",
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(manifest["cached_at"])
            expected_sha256 = str(manifest["sha256"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cache manifest is unreadable: {manifest_path.name}",
            ) from exc
        if cached_at.tzinfo is None:
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cache timestamp lacks a timezone: {manifest_path.name}",
            )
        if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
            return None
        try:
            payload_bytes = payload_path.read_bytes()
            actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            payload = json.loads(payload_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cached response is unreadable: {payload_path.name}",
            ) from exc
        if actual_sha256 != expected_sha256:
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cached response failed SHA-256 verification: {payload_path.name}",
                details={"expected": expected_sha256, "actual": actual_sha256},
            )
        if not isinstance(payload, dict):
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"ClinicalTrials.gov cached response has an invalid shape: {payload_path.name}",
            )
        return _SearchPayload(
            payload=payload,
            cache_hit=True,
            payload_path=payload_path,
            sha256=actual_sha256,
            request=trace,
        )

    def _write_search_cache(
        self,
        *,
        payload_path: Path,
        manifest_path: Path,
        payload: dict[str, Any],
        trace: AACTRequestTrace,
    ) -> str:
        payload_bytes = self._json_bytes(payload)
        sha256 = hashlib.sha256(payload_bytes).hexdigest()
        payload_temporary = payload_path.with_suffix(payload_path.suffix + ".tmp")
        manifest_temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        try:
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_temporary.write_bytes(payload_bytes)
            manifest_temporary.write_text(
                json.dumps(
                    {
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": sha256,
                        "request": trace.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            payload_temporary.replace(payload_path)
            manifest_temporary.replace(manifest_path)
        except OSError as exc:
            for temporary in (payload_temporary, manifest_temporary):
                if temporary.is_file():
                    temporary.unlink()
            if payload_path.is_file() and not manifest_path.is_file():
                payload_path.unlink()
            raise AACTAdapterError(
                AACTErrorCode.CACHE_ERROR,
                f"Could not write ClinicalTrials.gov search cache: {payload_path.name}",
            ) from exc
        return sha256

    @staticmethod
    def _required_dict(
        payload: dict[str, Any], key: str, *, context: str
    ) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov {context}.{key} is missing or invalid.",
            )
        return value

    @staticmethod
    def _optional_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _value_list(
        payload: dict[str, Any], key: str, *, context: str
    ) -> list[Any]:
        value = payload.get(key)
        if value is None or value == "":
            return []
        if not isinstance(value, list):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov {context} is not a list.",
            )
        return value

    @classmethod
    def _object_list(
        cls,
        payload: dict[str, Any],
        key: str,
        *,
        context: str,
        allow_empty_string: bool = False,
    ) -> list[dict[str, Any]]:
        value = payload.get(key)
        if value is None or (allow_empty_string and value == ""):
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise AACTAdapterError(
                AACTErrorCode.INVALID_RESPONSE,
                f"ClinicalTrials.gov {context} is not a list of objects.",
            )
        return value

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, url: str) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 400:
            raise AACTAdapterError(
                AACTErrorCode.INVALID_QUERY,
                "ClinicalTrials.gov rejected the search query.",
                upstream_status=status,
                details={"url": url},
            )
        if status == 429:
            raise AACTAdapterError(
                AACTErrorCode.RATE_LIMITED,
                "ClinicalTrials.gov rate limited the request.",
                retryable=True,
                upstream_status=status,
                details={"url": url},
            )
        raise AACTAdapterError(
            AACTErrorCode.REMOTE_ERROR,
            f"ClinicalTrials.gov returned HTTP {status}.",
            retryable=status >= 500,
            upstream_status=status,
            details={"url": url},
        )

    @staticmethod
    def _request_hash(trace: AACTRequestTrace) -> str:
        encoded = json.dumps(
            trace.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:24]

    @staticmethod
    def _json_bytes(payload: Any) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)
