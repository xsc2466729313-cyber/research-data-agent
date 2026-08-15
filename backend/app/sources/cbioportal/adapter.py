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
from backend.app.sources.cbioportal.errors import (
    CBioPortalAdapterError,
    CBioPortalErrorCode,
)
from backend.app.sources.cbioportal.models import (
    CBioPortalAdapterRequest,
    CBioPortalAdapterResult,
    CBioPortalRawTable,
    CBioPortalRequestTrace,
    CBioPortalSelection,
    CBioPortalStudyRecord,
    CBioPortalTableType,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "cbioportal"


@dataclass(frozen=True)
class _AcquiredPayload:
    payload: dict[str, Any] | list[Any]
    cache_hit: bool
    payload_path: Path
    sha256: str
    request: CBioPortalRequestTrace


class CBioPortalAdapter:
    API_BASE_URL = "https://www.cbioportal.org/api"
    PORTAL_STUDY_URL = "https://www.cbioportal.org/study/summary?id={study_id}"
    STUDY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        client: httpx.Client | None = None,
        timeout_seconds: float = 60.0,
        cache_ttl_seconds: int = 86_400,
        api_base_url: str = API_BASE_URL,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.api_base_url = api_base_url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "User-Agent": "breast-research-data-agent/0.3",
            },
        )

    def run(self, request: CBioPortalAdapterRequest) -> CBioPortalAdapterResult:
        options = request.options
        self._validate_input(request)
        study_id = options.study_id
        cache_hits: dict[str, bool] = {}
        tables: list[CBioPortalRawTable] = []

        study_acquired = self._acquire(
            method="GET",
            path=f"/studies/{study_id}",
            cache_name=f"{study_id}/study_metadata",
            refresh=options.refresh_cache,
            not_found_code=CBioPortalErrorCode.STUDY_NOT_FOUND,
        )
        study_metadata = self._dict_payload(
            study_acquired.payload, resource_name="study_metadata"
        )
        if study_metadata.get("studyId") != study_id:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                "cBioPortal study metadata returned a different studyId.",
                details={
                    "requested": study_id,
                    "returned": study_metadata.get("studyId"),
                },
            )
        study_source = self._source_item(
            task_id=request.search_plan.task_id,
            study_id=study_id,
            resource_name="study_metadata",
            acquired=study_acquired,
        )
        cache_hits["study_metadata"] = study_acquired.cache_hit
        study = CBioPortalStudyRecord(
            study_id=study_id,
            portal_url=self.PORTAL_STUDY_URL.format(study_id=study_id),
            raw_metadata=study_metadata,
            source_item=study_source,
        )

        selection = CBioPortalSelection()
        molecular_requested = any(
            table
            in {CBioPortalTableType.MUTATIONS, CBioPortalTableType.DISCRETE_CNA}
            for table in options.tables
        )
        if molecular_requested:
            profiles_acquired = self._acquire(
                method="GET",
                path=f"/studies/{study_id}/molecular-profiles",
                parameters={
                    "projection": "DETAILED",
                    "pageSize": 10_000,
                    "pageNumber": 0,
                },
                cache_name=f"{study_id}/molecular_profiles",
                refresh=options.refresh_cache,
                not_found_code=CBioPortalErrorCode.PROFILE_NOT_FOUND,
            )
            profiles = self._list_of_dicts(
                profiles_acquired.payload, resource_name="molecular_profiles"
            )
            tables.append(
                self._raw_table(
                    task_id=request.search_plan.task_id,
                    study_id=study_id,
                    table_name="molecular_profiles",
                    rows=profiles,
                    acquired=profiles_acquired,
                    upstream_row_count=len(profiles),
                    truncated=False,
                )
            )
            cache_hits["molecular_profiles"] = profiles_acquired.cache_hit

            sample_lists_acquired = self._acquire(
                method="GET",
                path=f"/studies/{study_id}/sample-lists",
                parameters={
                    "projection": "DETAILED",
                    "pageSize": 10_000,
                    "pageNumber": 0,
                },
                cache_name=f"{study_id}/sample_lists",
                refresh=options.refresh_cache,
                not_found_code=CBioPortalErrorCode.SAMPLE_LIST_NOT_FOUND,
            )
            sample_lists = self._list_of_dicts(
                sample_lists_acquired.payload, resource_name="sample_lists"
            )
            tables.append(
                self._raw_table(
                    task_id=request.search_plan.task_id,
                    study_id=study_id,
                    table_name="sample_lists",
                    rows=sample_lists,
                    acquired=sample_lists_acquired,
                    upstream_row_count=len(sample_lists),
                    truncated=False,
                )
            )
            cache_hits["sample_lists"] = sample_lists_acquired.cache_hit

            genes_acquired = self._acquire(
                method="POST",
                path="/genes/fetch",
                parameters={
                    "geneIdType": "HUGO_GENE_SYMBOL",
                    "projection": "DETAILED",
                },
                body=options.gene_symbols,
                cache_name=f"{study_id}/genes",
                refresh=options.refresh_cache,
                not_found_code=CBioPortalErrorCode.GENE_NOT_FOUND,
            )
            genes = self._list_of_dicts(
                genes_acquired.payload, resource_name="genes"
            )
            self._validate_genes(options.gene_symbols, genes)
            tables.append(
                self._raw_table(
                    task_id=request.search_plan.task_id,
                    study_id=study_id,
                    table_name="genes",
                    rows=genes,
                    acquired=genes_acquired,
                    upstream_row_count=len(genes),
                    truncated=False,
                )
            )
            cache_hits["genes"] = genes_acquired.cache_hit
            selection.genes = genes
            entrez_gene_ids = [int(gene["entrezGeneId"]) for gene in genes]

            if CBioPortalTableType.MUTATIONS in options.tables:
                mutation_profile_id = self._select_profile(
                    profiles=profiles,
                    override=options.mutation_profile_id,
                    alteration_type="MUTATION_EXTENDED",
                    datatype=None,
                    label="mutation",
                )
                mutation_sample_list_id = self._select_sample_list(
                    sample_lists=sample_lists,
                    override=options.sample_list_id,
                    preferred_category="all_cases_with_mutation_data",
                    study_id=study_id,
                    label="mutation",
                )
                selection.mutation_profile_id = mutation_profile_id
                selection.mutation_sample_list_id = mutation_sample_list_id
                mutation_acquired = self._acquire(
                    method="POST",
                    path=(
                        f"/molecular-profiles/{mutation_profile_id}/mutations/fetch"
                    ),
                    parameters={
                        "projection": "DETAILED",
                        "pageSize": options.max_records_per_table,
                        "pageNumber": 0,
                    },
                    body={
                        "sampleListId": mutation_sample_list_id,
                        "entrezGeneIds": entrez_gene_ids,
                    },
                    cache_name=f"{study_id}/mutations",
                    refresh=options.refresh_cache,
                    not_found_code=CBioPortalErrorCode.PROFILE_NOT_FOUND,
                )
                mutation_rows = self._list_of_dicts(
                    mutation_acquired.payload, resource_name="mutations"
                )
                mutation_truncated = (
                    len(mutation_rows) >= options.max_records_per_table
                )
                tables.append(
                    self._raw_table(
                        task_id=request.search_plan.task_id,
                        study_id=study_id,
                        table_name=CBioPortalTableType.MUTATIONS.value,
                        rows=mutation_rows,
                        acquired=mutation_acquired,
                        upstream_row_count=(
                            None if mutation_truncated else len(mutation_rows)
                        ),
                        truncated=mutation_truncated,
                    )
                )
                cache_hits["mutations"] = mutation_acquired.cache_hit

            if CBioPortalTableType.DISCRETE_CNA in options.tables:
                cna_profile_id = self._select_profile(
                    profiles=profiles,
                    override=options.cna_profile_id,
                    alteration_type="COPY_NUMBER_ALTERATION",
                    datatype="DISCRETE",
                    label="discrete CNA",
                )
                cna_sample_list_id = self._select_sample_list(
                    sample_lists=sample_lists,
                    override=options.sample_list_id,
                    preferred_category="all_cases_with_cna_data",
                    study_id=study_id,
                    label="CNA",
                )
                selection.cna_profile_id = cna_profile_id
                selection.cna_sample_list_id = cna_sample_list_id
                cna_acquired = self._acquire(
                    method="POST",
                    path=(
                        f"/molecular-profiles/{cna_profile_id}/"
                        "discrete-copy-number/fetch"
                    ),
                    parameters={
                        "discreteCopyNumberEventType": options.cna_event_type.value,
                        "projection": "DETAILED",
                    },
                    body={
                        "sampleListId": cna_sample_list_id,
                        "entrezGeneIds": entrez_gene_ids,
                    },
                    cache_name=f"{study_id}/discrete_cna",
                    refresh=options.refresh_cache,
                    not_found_code=CBioPortalErrorCode.PROFILE_NOT_FOUND,
                )
                all_cna_rows = self._list_of_dicts(
                    cna_acquired.payload, resource_name="discrete_cna"
                )
                cna_rows = all_cna_rows[: options.max_records_per_table]
                tables.append(
                    self._raw_table(
                        task_id=request.search_plan.task_id,
                        study_id=study_id,
                        table_name=CBioPortalTableType.DISCRETE_CNA.value,
                        rows=cna_rows,
                        acquired=cna_acquired,
                        upstream_row_count=len(all_cna_rows),
                        truncated=len(all_cna_rows) > len(cna_rows),
                    )
                )
                cache_hits["discrete_cna"] = cna_acquired.cache_hit

        for table_type, clinical_data_type in (
            (CBioPortalTableType.CLINICAL_SAMPLE, "SAMPLE"),
            (CBioPortalTableType.CLINICAL_PATIENT, "PATIENT"),
        ):
            if table_type not in options.tables:
                continue
            acquired = self._acquire(
                method="GET",
                path=f"/studies/{study_id}/clinical-data",
                parameters={
                    "clinicalDataType": clinical_data_type,
                    "projection": "DETAILED",
                    "pageSize": options.max_records_per_table,
                    "pageNumber": 0,
                },
                cache_name=f"{study_id}/{table_type.value}",
                refresh=options.refresh_cache,
                not_found_code=CBioPortalErrorCode.STUDY_NOT_FOUND,
            )
            rows = self._list_of_dicts(acquired.payload, resource_name=table_type.value)
            truncated = len(rows) >= options.max_records_per_table
            tables.append(
                self._raw_table(
                    task_id=request.search_plan.task_id,
                    study_id=study_id,
                    table_name=table_type.value,
                    rows=rows,
                    acquired=acquired,
                    upstream_row_count=None if truncated else len(rows),
                    truncated=truncated,
                )
            )
            cache_hits[table_type.value] = acquired.cache_hit

        source_items = [study.source_item] + [table.source_item for table in tables]
        return CBioPortalAdapterResult(
            task_id=request.search_plan.task_id,
            study=study,
            selection=selection,
            tables=tables,
            source_items=source_items,
            cache_hit=cache_hits,
            queried_at=datetime.now(timezone.utc),
            notice=(
                "数据来自 cBioPortal 官方公开 API；表内字段保持上游原样。"
                "离散 CNA 与临床 HER2 检测结果保持为不同语义层，本阶段不做映射或融合。"
            ),
        )

    def _validate_input(self, request: CBioPortalAdapterRequest) -> None:
        if not any(
            plan.source.casefold()
            in {"cbioportal", "cbio portal", "cbioportal/datahub", "datahub"}
            for plan in request.search_plan.plans
        ):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_PLAN,
                "SearchPlan does not contain a cBioPortal task.",
            )
        if not self.STUDY_ID_PATTERN.fullmatch(request.options.study_id):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_STUDY_ID,
                "cBioPortal study_id contains unsupported characters.",
                details={"study_id": request.options.study_id},
            )
        invalid_genes = [
            symbol
            for symbol in request.options.gene_symbols
            if not isinstance(symbol, str)
            or not symbol
            or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", symbol)
        ]
        if invalid_genes:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_SELECTION,
                "gene_symbols contains an invalid HUGO symbol.",
                details={"gene_symbols": invalid_genes},
            )

    def _acquire(
        self,
        *,
        method: str,
        path: str,
        cache_name: str,
        refresh: bool,
        not_found_code: CBioPortalErrorCode,
        parameters: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> _AcquiredPayload:
        url = f"{self.api_base_url}{path}"
        trace = CBioPortalRequestTrace(
            method=method,
            url=url,
            parameters=parameters or {},
            body=body,
        )
        request_hash = self._request_hash(trace)
        cache_directory = self.cache_dir / "responses" / self._safe_name(cache_name)
        payload_path = cache_directory / f"{request_hash}.json"
        manifest_path = cache_directory / f"{request_hash}.cache.json"
        if not refresh:
            cached = self._read_cache(
                payload_path=payload_path,
                manifest_path=manifest_path,
                trace=trace,
            )
            if cached is not None:
                return cached

        try:
            response = self.client.request(
                method, url, params=parameters or None, json=body
            )
        except httpx.TimeoutException as exc:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.TIMEOUT,
                f"cBioPortal request timed out: {path}",
                retryable=True,
                details={"url": url},
            ) from exc
        except httpx.RequestError as exc:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.NETWORK_ERROR,
                f"cBioPortal network request failed: {path}",
                retryable=True,
                details={"url": url, "error_type": type(exc).__name__},
            ) from exc

        self._raise_for_status(
            response, url=url, not_found_code=not_found_code
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                f"cBioPortal returned non-JSON content: {path}",
                details={"content_type": response.headers.get("content-type")},
            ) from exc
        if not isinstance(payload, (dict, list)):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                f"cBioPortal returned an unexpected JSON shape: {path}",
            )
        sha256 = self._write_cache(
            payload_path=payload_path,
            manifest_path=manifest_path,
            payload=payload,
            trace=trace,
        )
        return _AcquiredPayload(
            payload=payload,
            cache_hit=False,
            payload_path=payload_path,
            sha256=sha256,
            request=trace,
        )

    def _read_cache(
        self,
        *,
        payload_path: Path,
        manifest_path: Path,
        trace: CBioPortalRequestTrace,
    ) -> _AcquiredPayload | None:
        if not payload_path.exists() and not manifest_path.exists():
            return None
        if not payload_path.is_file() or not manifest_path.is_file():
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cache is incomplete: {payload_path.name}",
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(manifest["cached_at"])
            expected_sha256 = str(manifest["sha256"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cache manifest is unreadable: {manifest_path.name}",
            ) from exc
        if cached_at.tzinfo is None:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cache timestamp lacks a timezone: {manifest_path.name}",
            )
        if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
            return None
        try:
            payload_bytes = payload_path.read_bytes()
            actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            payload = json.loads(payload_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cached payload is unreadable: {payload_path.name}",
            ) from exc
        if actual_sha256 != expected_sha256:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cached payload failed SHA-256 verification: {payload_path.name}",
                details={"expected": expected_sha256, "actual": actual_sha256},
            )
        if not isinstance(payload, (dict, list)):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"cBioPortal cached payload has an invalid shape: {payload_path.name}",
            )
        return _AcquiredPayload(
            payload=payload,
            cache_hit=True,
            payload_path=payload_path,
            sha256=actual_sha256,
            request=trace,
        )

    @staticmethod
    def _write_cache(
        *,
        payload_path: Path,
        manifest_path: Path,
        payload: dict[str, Any] | list[Any],
        trace: CBioPortalRequestTrace,
    ) -> str:
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
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
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.CACHE_ERROR,
                f"Could not write cBioPortal cache: {payload_path.name}",
            ) from exc
        return sha256

    def _raw_table(
        self,
        *,
        task_id: str,
        study_id: str,
        table_name: str,
        rows: list[dict[str, Any]],
        acquired: _AcquiredPayload,
        upstream_row_count: int | None,
        truncated: bool,
    ) -> CBioPortalRawTable:
        return CBioPortalRawTable(
            table_name=table_name,
            study_id=study_id,
            raw_fields=sorted({key for row in rows for key in row}),
            rows=rows,
            row_count=len(rows),
            upstream_row_count=upstream_row_count,
            truncated=truncated,
            request=acquired.request,
            source_item=self._source_item(
                task_id=task_id,
                study_id=study_id,
                resource_name=table_name,
                acquired=acquired,
            ),
        )

    def _source_item(
        self,
        *,
        task_id: str,
        study_id: str,
        resource_name: str,
        acquired: _AcquiredPayload,
    ) -> SourceItem:
        request_hash = self._request_hash(acquired.request)[:12]
        return SourceItem(
            source_id=(
                f"cbioportal:{study_id}:{self._safe_name(resource_name)}:{request_hash}"
            ),
            task_id=task_id,
            source_name="cBioPortal",
            source_type="database",
            accession=study_id,
            url=acquired.request.url,
            file_type=f"json:{resource_name}",
            local_path=self._display_path(acquired.payload_path),
            checksum=f"sha256:{acquired.sha256}",
            status="cached" if acquired.cache_hit else "retrieved",
        )

    @staticmethod
    def _dict_payload(
        payload: dict[str, Any] | list[Any], *, resource_name: str
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                f"cBioPortal {resource_name} response is not an object.",
            )
        return payload

    @staticmethod
    def _list_of_dicts(
        payload: dict[str, Any] | list[Any], *, resource_name: str
    ) -> list[dict[str, Any]]:
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                f"cBioPortal {resource_name} response is not a list of objects.",
            )
        return payload

    @staticmethod
    def _validate_genes(
        requested_symbols: list[str], genes: list[dict[str, Any]]
    ) -> None:
        returned_symbols = {
            str(gene.get("hugoGeneSymbol", "")).upper() for gene in genes
        }
        missing = [
            symbol for symbol in requested_symbols if symbol not in returned_symbols
        ]
        if missing:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.GENE_NOT_FOUND,
                "cBioPortal could not resolve every requested HUGO gene symbol.",
                details={"missing_gene_symbols": missing},
            )
        if any(
            not isinstance(gene.get("entrezGeneId"), int)
            for gene in genes
        ):
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_RESPONSE,
                "cBioPortal gene records are missing integer Entrez IDs.",
            )

    @staticmethod
    def _select_profile(
        *,
        profiles: list[dict[str, Any]],
        override: str | None,
        alteration_type: str,
        datatype: str | None,
        label: str,
    ) -> str:
        candidates = [
            profile
            for profile in profiles
            if profile.get("molecularAlterationType") == alteration_type
            and (datatype is None or profile.get("datatype") == datatype)
        ]
        if override is not None:
            if any(
                profile.get("molecularProfileId") == override
                for profile in candidates
            ):
                return override
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_SELECTION,
                f"Requested {label} profile is not valid for this study.",
                details={"profile_id": override},
            )
        if not candidates:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.PROFILE_NOT_FOUND,
                f"cBioPortal study does not provide a {label} profile.",
            )
        candidates.sort(
            key=lambda profile: (
                0
                if str(profile.get("molecularProfileId", "")).endswith(
                    "_mutations" if alteration_type == "MUTATION_EXTENDED" else "_cna"
                )
                else 1,
                str(profile.get("molecularProfileId", "")),
            )
        )
        return str(candidates[0]["molecularProfileId"])

    @staticmethod
    def _select_sample_list(
        *,
        sample_lists: list[dict[str, Any]],
        override: str | None,
        preferred_category: str,
        study_id: str,
        label: str,
    ) -> str:
        if override is not None:
            if any(item.get("sampleListId") == override for item in sample_lists):
                return override
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.INVALID_SELECTION,
                f"Requested {label} sample list is not valid for this study.",
                details={"sample_list_id": override},
            )
        preferences = (
            lambda item: item.get("category") == preferred_category,
            lambda item: item.get("sampleListId")
            == f"{study_id}_{'sequenced' if label == 'mutation' else 'cna'}",
            lambda item: item.get("category") == "all_cases_in_study",
        )
        for predicate in preferences:
            matches = [item for item in sample_lists if predicate(item)]
            if matches:
                return str(sorted(matches, key=lambda item: item["sampleListId"])[0]["sampleListId"])
        raise CBioPortalAdapterError(
            CBioPortalErrorCode.SAMPLE_LIST_NOT_FOUND,
            f"cBioPortal study does not provide a usable {label} sample list.",
        )

    @staticmethod
    def _raise_for_status(
        response: httpx.Response,
        *,
        url: str,
        not_found_code: CBioPortalErrorCode,
    ) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 404:
            raise CBioPortalAdapterError(
                not_found_code,
                f"cBioPortal resource was not found: {url}",
                upstream_status=status,
                details={"url": url},
            )
        if status in {401, 403}:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.AUTH_REQUIRED,
                f"cBioPortal requires authorization: {url}",
                upstream_status=status,
                details={"url": url},
            )
        if status == 429:
            raise CBioPortalAdapterError(
                CBioPortalErrorCode.RATE_LIMITED,
                f"cBioPortal rate limited the request: {url}",
                retryable=True,
                upstream_status=status,
                details={"url": url},
            )
        raise CBioPortalAdapterError(
            CBioPortalErrorCode.REMOTE_ERROR,
            f"cBioPortal returned HTTP {status}: {url}",
            retryable=status >= 500,
            upstream_status=status,
            details={"url": url},
        )

    @staticmethod
    def _request_hash(trace: CBioPortalRequestTrace) -> str:
        encoded = json.dumps(
            trace.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:24]

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
        return safe or "unnamed"

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)
