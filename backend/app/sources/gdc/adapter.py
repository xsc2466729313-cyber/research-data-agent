from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from backend.app.models import SourceItem
from backend.app.sources.gdc.errors import GDCAdapterError, GDCErrorCode
from backend.app.sources.gdc.models import (
    GDCAdapterRequest,
    GDCAdapterResult,
    GDCCacheStatus,
    GDCFileRecord,
    GDCProjectRecord,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "gdc"


class GDCAdapter:
    API_BASE_URL = "https://api.gdc.cancer.gov"
    PORTAL_PROJECT_URL = "https://portal.gdc.cancer.gov/projects/{project_id}"
    PROJECT_FIELDS = (
        "project_id,name,state,released,primary_site,disease_type,summary.case_count"
    )
    FILE_FIELDS = (
        "file_id,file_name,md5sum,file_size,state,access,data_category,data_type,"
        "data_format,experimental_strategy"
    )

    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        cache_ttl_seconds: int = 86_400,
        auth_token: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        token = auth_token if auth_token is not None else os.getenv("GDC_AUTH_TOKEN")
        headers = {
            "Accept": "application/json",
            "User-Agent": "breast-research-data-agent/0.1",
        }
        if token:
            headers["X-Auth-Token"] = token
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
        )

    def run(self, request: GDCAdapterRequest) -> GDCAdapterResult:
        self._validate_input(request)
        options = request.options

        project_payload, project_cache_hit = self._cached_json_request(
            cache_path=self.cache_dir
            / "metadata"
            / f"project_{self._safe_name(options.project_id)}.json",
            endpoint="/projects",
            payload=self._project_payload(options.project_id),
            refresh=options.refresh_cache,
        )
        project = self._parse_project(options.project_id, project_payload)

        files_payload = self._files_payload(
            project_id=options.project_id,
            data_types=options.data_types,
            max_files=options.max_files,
            open_access_only=options.open_access_only,
        )
        files_cache_path = (
            self.cache_dir
            / "metadata"
            / f"files_{self._payload_hash(files_payload)}.json"
        )
        file_payload, files_cache_hit = self._cached_json_request(
            cache_path=files_cache_path,
            endpoint="/files",
            payload=files_payload,
            refresh=options.refresh_cache,
        )
        hits = self._extract_hits(file_payload, endpoint="files")
        if not hits:
            raise GDCAdapterError(
                GDCErrorCode.NO_FILES,
                f"GDC returned no files for project {options.project_id}.",
                details={"project_id": options.project_id, "data_types": options.data_types},
            )

        files = [
            self._register_file(
                task_id=request.research_spec.task_id,
                project_id=options.project_id,
                hit=hit,
                download=options.download,
                max_download_bytes=options.max_download_bytes,
                refresh=options.refresh_cache,
            )
            for hit in hits
        ]
        return GDCAdapterResult(
            task_id=request.research_spec.task_id,
            project=project,
            files=files,
            source_items=[file.source_item for file in files],
            cache_hit=GDCCacheStatus(
                project_metadata=project_cache_hit,
                file_metadata=files_cache_hit,
            ),
            queried_at=datetime.now(timezone.utc),
            notice=(
                "GDC 官方 API 实时元数据；下载默认关闭。受控数据需要 GDC_AUTH_TOKEN，"
                "且不会把令牌写入缓存或响应。"
            ),
        )

    def _validate_input(self, request: GDCAdapterRequest) -> None:
        if request.research_spec.task_id != request.search_plan.task_id:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_PLAN,
                "ResearchSpec and SearchPlan task_id values do not match.",
            )
        has_gdc_plan = any(
            plan.source.casefold() in {"gdc", "gdc/tcga", "tcga"}
            for plan in request.search_plan.plans
        )
        if not has_gdc_plan:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_PLAN,
                "SearchPlan does not contain a GDC task.",
            )

    def _cached_json_request(
        self,
        *,
        cache_path: Path,
        endpoint: str,
        payload: dict[str, Any],
        refresh: bool,
    ) -> tuple[dict[str, Any], bool]:
        if not refresh:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached, True

        result = self._request_json(endpoint, payload)
        self._write_cache(cache_path, result)
        return result, False

    def _request_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.API_BASE_URL}{endpoint}"
        try:
            response = self.client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise GDCAdapterError(
                GDCErrorCode.TIMEOUT,
                f"GDC request timed out at {endpoint}.",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise GDCAdapterError(
                GDCErrorCode.NETWORK_ERROR,
                f"GDC network request failed at {endpoint}.",
                retryable=True,
                details={"error_type": type(exc).__name__},
            ) from exc

        self._raise_for_status(response, endpoint)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                f"GDC returned non-JSON content from {endpoint}.",
                details={"content_type": response.headers.get("content-type")},
            ) from exc
        if not isinstance(payload, dict):
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                f"GDC returned an unexpected JSON shape from {endpoint}.",
            )
        return payload

    @staticmethod
    def _project_payload(project_id: str) -> dict[str, Any]:
        return {
            "filters": {
                "op": "in",
                "content": {"field": "project_id", "value": [project_id]},
            },
            "fields": GDCAdapter.PROJECT_FIELDS,
            "format": "JSON",
            "size": 1,
        }

    @staticmethod
    def _files_payload(
        *,
        project_id: str,
        data_types: list[str],
        max_files: int,
        open_access_only: bool,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = [
            {
                "op": "in",
                "content": {
                    "field": "cases.project.project_id",
                    "value": [project_id],
                },
            }
        ]
        if open_access_only:
            filters.append(
                {
                    "op": "in",
                    "content": {"field": "files.access", "value": ["open"]},
                }
            )
        if data_types:
            filters.append(
                {
                    "op": "in",
                    "content": {"field": "files.data_type", "value": data_types},
                }
            )
        return {
            "filters": {"op": "and", "content": filters},
            "fields": GDCAdapter.FILE_FIELDS,
            "format": "JSON",
            "size": max_files,
            "sort": "file_size:asc",
        }

    def _parse_project(
        self, project_id: str, payload: dict[str, Any]
    ) -> GDCProjectRecord:
        hits = self._extract_hits(payload, endpoint="projects")
        if not hits:
            raise GDCAdapterError(
                GDCErrorCode.PROJECT_NOT_FOUND,
                f"GDC project {project_id} was not found.",
                details={"project_id": project_id},
            )
        hit = hits[0]
        try:
            return GDCProjectRecord(
                project_id=hit["project_id"],
                name=hit["name"],
                state=hit["state"],
                released=hit["released"],
                primary_site=hit.get("primary_site") or [],
                disease_type=hit.get("disease_type") or [],
                case_count=(hit.get("summary") or {}).get("case_count", 0),
                api_url=f"{self.API_BASE_URL}/projects/{hit['project_id']}",
                portal_url=self.PORTAL_PROJECT_URL.format(project_id=hit["project_id"]),
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                "GDC project metadata is missing required fields.",
                details={"project_id": project_id},
            ) from exc

    def _register_file(
        self,
        *,
        task_id: str,
        project_id: str,
        hit: dict[str, Any],
        download: bool,
        max_download_bytes: int,
        refresh: bool,
    ) -> GDCFileRecord:
        try:
            file_id = str(hit["file_id"])
            file_name = str(hit["file_name"])
            md5sum = str(hit["md5sum"]).lower()
            file_size = int(hit["file_size"])
            download_url = f"{self.API_BASE_URL}/data/{file_id}"
            local_path: str | None = None
            status = "discovered"
            if download:
                downloaded_path, cache_hit = self._download_file(
                    file_id=file_id,
                    file_name=file_name,
                    expected_md5=md5sum,
                    expected_size=file_size,
                    max_download_bytes=max_download_bytes,
                    refresh=refresh,
                )
                local_path = self._display_path(downloaded_path)
                status = "cached" if cache_hit else "downloaded"

            source_item = SourceItem(
                source_id=f"gdc:{file_id}",
                task_id=task_id,
                source_name="GDC",
                source_type="database",
                accession=project_id,
                url=download_url,
                file_type=str(hit["data_format"]),
                local_path=local_path,
                checksum=f"md5:{md5sum}",
                status=status,
            )
            return GDCFileRecord(
                file_id=file_id,
                project_id=project_id,
                file_name=file_name,
                md5sum=md5sum,
                file_size=file_size,
                state=str(hit["state"]),
                access=str(hit["access"]),
                data_category=str(hit["data_category"]),
                data_type=str(hit["data_type"]),
                data_format=str(hit["data_format"]),
                experimental_strategy=hit.get("experimental_strategy"),
                download_url=download_url,
                source_item=source_item,
            )
        except GDCAdapterError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                "GDC file metadata is missing or invalid.",
                details={"file_id": hit.get("file_id")},
            ) from exc

    def _download_file(
        self,
        *,
        file_id: str,
        file_name: str,
        expected_md5: str,
        expected_size: int,
        max_download_bytes: int,
        refresh: bool,
    ) -> tuple[Path, bool]:
        if expected_size > max_download_bytes:
            raise GDCAdapterError(
                GDCErrorCode.DOWNLOAD_TOO_LARGE,
                f"GDC file {file_id} exceeds the configured download limit.",
                details={
                    "file_id": file_id,
                    "file_size": expected_size,
                    "max_download_bytes": max_download_bytes,
                },
            )
        target = self.cache_dir / "files" / file_id / self._safe_name(file_name)
        if target.is_file() and not refresh:
            actual_md5 = self._md5_file(target)
            if actual_md5 != expected_md5:
                raise GDCAdapterError(
                    GDCErrorCode.CHECKSUM_MISMATCH,
                    f"Cached GDC file {file_id} failed MD5 verification.",
                    details={"expected": expected_md5, "actual": actual_md5},
                )
            return target, True

        url = f"{self.API_BASE_URL}/data/{file_id}"
        try:
            with self.client.stream("GET", url) as response:
                self._raise_for_status(response, f"/data/{file_id}")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".part")
                digest = hashlib.md5(usedforsecurity=False)
                downloaded = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        downloaded += len(chunk)
                        if downloaded > max_download_bytes:
                            raise GDCAdapterError(
                                GDCErrorCode.DOWNLOAD_TOO_LARGE,
                                f"GDC download {file_id} exceeded the configured limit.",
                                details={"max_download_bytes": max_download_bytes},
                            )
                        handle.write(chunk)
                        digest.update(chunk)
        except GDCAdapterError:
            self._remove_partial(locals().get("temporary"))
            raise
        except httpx.TimeoutException as exc:
            self._remove_partial(locals().get("temporary"))
            raise GDCAdapterError(
                GDCErrorCode.TIMEOUT,
                f"GDC download timed out for file {file_id}.",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            self._remove_partial(locals().get("temporary"))
            raise GDCAdapterError(
                GDCErrorCode.DOWNLOAD_ERROR,
                f"GDC download failed for file {file_id}.",
                retryable=True,
                details={"error_type": type(exc).__name__},
            ) from exc
        except OSError as exc:
            self._remove_partial(locals().get("temporary"))
            raise GDCAdapterError(
                GDCErrorCode.CACHE_ERROR,
                f"Could not write GDC cache file {file_id}.",
                details={"error_type": type(exc).__name__},
            ) from exc

        actual_md5 = digest.hexdigest()
        if actual_md5 != expected_md5:
            self._remove_partial(temporary)
            raise GDCAdapterError(
                GDCErrorCode.CHECKSUM_MISMATCH,
                f"Downloaded GDC file {file_id} failed MD5 verification.",
                details={"expected": expected_md5, "actual": actual_md5},
            )
        if downloaded != expected_size:
            self._remove_partial(temporary)
            raise GDCAdapterError(
                GDCErrorCode.DOWNLOAD_ERROR,
                f"Downloaded GDC file {file_id} has an unexpected size.",
                details={"expected": expected_size, "actual": downloaded},
            )
        temporary.replace(target)
        return target, False

    @staticmethod
    def _raise_for_status(response: httpx.Response, endpoint: str) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in {401, 403}:
            raise GDCAdapterError(
                GDCErrorCode.AUTH_REQUIRED,
                f"GDC requires authorization for {endpoint}.",
                upstream_status=status,
            )
        if status == 429:
            raise GDCAdapterError(
                GDCErrorCode.RATE_LIMITED,
                f"GDC rate limited the request to {endpoint}.",
                retryable=True,
                upstream_status=status,
            )
        raise GDCAdapterError(
            GDCErrorCode.API_ERROR,
            f"GDC returned HTTP {status} from {endpoint}.",
            retryable=status >= 500,
            upstream_status=status,
        )

    @staticmethod
    def _extract_hits(payload: dict[str, Any], *, endpoint: str) -> list[dict[str, Any]]:
        try:
            hits = payload["data"]["hits"]
        except (KeyError, TypeError) as exc:
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                f"GDC {endpoint} response does not contain data.hits.",
            ) from exc
        if not isinstance(hits, list) or not all(isinstance(hit, dict) for hit in hits):
            raise GDCAdapterError(
                GDCErrorCode.INVALID_RESPONSE,
                f"GDC {endpoint} data.hits is not a list of objects.",
            )
        return hits

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(envelope["cached_at"])
            payload = envelope["payload"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise GDCAdapterError(
                GDCErrorCode.CACHE_ERROR,
                f"GDC metadata cache is unreadable: {path.name}.",
            ) from exc
        if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
            return None
        if not isinstance(payload, dict):
            raise GDCAdapterError(
                GDCErrorCode.CACHE_ERROR,
                f"GDC metadata cache has an invalid payload: {path.name}.",
            )
        return payload

    @staticmethod
    def _write_cache(path: Path, payload: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            raise GDCAdapterError(
                GDCErrorCode.CACHE_ERROR,
                f"Could not write GDC metadata cache: {path.name}.",
            ) from exc

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
        return safe or "unnamed"

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:20]

    @staticmethod
    def _md5_file(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _remove_partial(path: Path | None) -> None:
        if path and path.is_file():
            path.unlink()

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)

