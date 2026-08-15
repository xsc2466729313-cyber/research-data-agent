from __future__ import annotations

import hashlib
import json
import posixpath
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from backend.app.models import SourceItem
from backend.app.sources.geo.errors import GEOAdapterError, GEOErrorCode
from backend.app.sources.geo.models import (
    GEOAdapterRequest,
    GEOAdapterResult,
    GEOCacheStatus,
    GEOResourceAvailability,
    GEOResourceRecord,
    GEOResourceType,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "geo"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attrs:
            if name.casefold() == "href" and value:
                self.hrefs.append(value)


class GEOAdapter:
    FTP_HTTPS_BASE = "https://ftp.ncbi.nlm.nih.gov/geo/series"
    PORTAL_URL = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
    RESOURCE_DIRECTORIES = {
        GEOResourceType.SERIES_MATRIX: "matrix",
        GEOResourceType.SOFT: "soft",
        GEOResourceType.SUPPLEMENT: "suppl",
    }
    ACCESSION_PATTERN = re.compile(r"^GSE[1-9]\d*$")

    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        cache_ttl_seconds: int = 86_400,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "Accept": "text/html,application/octet-stream;q=0.9,*/*;q=0.8",
                "User-Agent": "breast-research-data-agent/0.2",
            },
        )

    def run(self, request: GEOAdapterRequest) -> GEOAdapterResult:
        accession = request.options.accession
        self._validate_input(request, accession)
        bucket = self.accession_bucket(accession)
        accession_url = f"{self.FTP_HTTPS_BASE}/{bucket}/{accession}/"

        _, accession_cache_hit = self._cached_directory(
            url=accession_url,
            cache_path=self.cache_dir / "metadata" / f"{accession}_root.json",
            refresh=request.options.refresh_cache,
            not_found_code=GEOErrorCode.ACCESSION_NOT_FOUND,
        )

        availability: list[GEOResourceAvailability] = []
        resources: list[GEOResourceRecord] = []
        resource_cache_hits: dict[str, bool] = {}
        for resource_type in request.options.resource_types:
            directory_name = self.RESOURCE_DIRECTORIES[resource_type]
            directory_url = f"{accession_url}{directory_name}/"
            try:
                hrefs, cache_hit = self._cached_directory(
                    url=directory_url,
                    cache_path=(
                        self.cache_dir
                        / "metadata"
                        / f"{accession}_{resource_type.value}.json"
                    ),
                    refresh=request.options.refresh_cache,
                    not_found_code=GEOErrorCode.RESOURCE_NOT_FOUND,
                )
            except GEOAdapterError as exc:
                if exc.code != GEOErrorCode.RESOURCE_NOT_FOUND:
                    raise
                resource_cache_hits[resource_type.value] = False
                availability.append(
                    GEOResourceAvailability(
                        resource_type=resource_type,
                        directory_url=directory_url,
                        status="not_found",
                        file_count=0,
                    )
                )
                continue

            resource_cache_hits[resource_type.value] = cache_hit
            file_entries = self._file_entries(
                hrefs=hrefs,
                directory_url=directory_url,
                resource_type=resource_type,
            )[: request.options.max_files_per_type]
            availability.append(
                GEOResourceAvailability(
                    resource_type=resource_type,
                    directory_url=directory_url,
                    status="available" if file_entries else "not_found",
                    file_count=len(file_entries),
                )
            )
            resources.extend(
                self._register_resource(
                    task_id=request.search_plan.task_id,
                    accession=accession,
                    resource_type=resource_type,
                    file_name=file_name,
                    download_url=download_url,
                    download=request.options.download,
                    max_download_bytes=request.options.max_download_bytes,
                    refresh=request.options.refresh_cache,
                )
                for file_name, download_url in file_entries
            )

        if not resources:
            raise GEOAdapterError(
                GEOErrorCode.RESOURCE_NOT_FOUND,
                f"GEO accession {accession} has none of the requested resources.",
                details={
                    "accession": accession,
                    "resource_types": [
                        item.value for item in request.options.resource_types
                    ],
                },
            )

        return GEOAdapterResult(
            task_id=request.search_plan.task_id,
            accession=accession,
            portal_url=self.PORTAL_URL.format(accession=accession),
            availability=availability,
            resources=resources,
            source_items=[resource.source_item for resource in resources],
            cache_hit=GEOCacheStatus(
                accession_directory=accession_cache_hit,
                resource_directories=resource_cache_hits,
            ),
            queried_at=datetime.now(timezone.utc),
            notice=(
                "资源来自 NCBI GEO 官方 HTTPS 归档目录；默认仅发现文件。"
                "启用下载时按单文件大小上限流式获取，并记录 SHA-256。"
            ),
        )

    def _validate_input(self, request: GEOAdapterRequest, accession: str) -> None:
        if not any(
            plan.source.casefold() in {"geo", "ncbi geo", "gene expression omnibus"}
            for plan in request.search_plan.plans
        ):
            raise GEOAdapterError(
                GEOErrorCode.INVALID_PLAN,
                "SearchPlan does not contain a GEO task.",
            )
        if not self.ACCESSION_PATTERN.fullmatch(accession):
            raise GEOAdapterError(
                GEOErrorCode.INVALID_ACCESSION,
                "GEO Adapter only accepts a public GSE accession such as GSE25066.",
                details={"accession": accession},
            )

    @classmethod
    def accession_bucket(cls, accession: str) -> str:
        if not cls.ACCESSION_PATTERN.fullmatch(accession):
            raise GEOAdapterError(
                GEOErrorCode.INVALID_ACCESSION,
                "Cannot derive a GEO directory bucket from an invalid GSE accession.",
                details={"accession": accession},
            )
        digits = accession[3:]
        return f"GSE{digits[:-3]}nnn"

    def _cached_directory(
        self,
        *,
        url: str,
        cache_path: Path,
        refresh: bool,
        not_found_code: GEOErrorCode,
    ) -> tuple[list[str], bool]:
        if not refresh:
            cached = self._read_directory_cache(cache_path)
            if cached is not None:
                return cached, True
        hrefs = self._request_directory(url, not_found_code=not_found_code)
        self._write_directory_cache(cache_path, url=url, hrefs=hrefs)
        return hrefs, False

    def _request_directory(
        self, url: str, *, not_found_code: GEOErrorCode
    ) -> list[str]:
        try:
            response = self.client.get(url)
        except httpx.TimeoutException as exc:
            raise GEOAdapterError(
                GEOErrorCode.TIMEOUT,
                f"GEO directory request timed out: {url}",
                retryable=True,
                details={"url": url},
            ) from exc
        except httpx.RequestError as exc:
            raise GEOAdapterError(
                GEOErrorCode.NETWORK_ERROR,
                f"GEO directory request failed: {url}",
                retryable=True,
                details={"url": url, "error_type": type(exc).__name__},
            ) from exc

        self._raise_for_status(
            response, url=url, not_found_code=not_found_code
        )
        parser = _LinkParser()
        try:
            parser.feed(response.text)
        except (UnicodeError, ValueError) as exc:
            raise GEOAdapterError(
                GEOErrorCode.INVALID_RESPONSE,
                f"GEO returned an unreadable directory listing: {url}",
                details={"url": url},
            ) from exc
        return parser.hrefs

    def _file_entries(
        self,
        *,
        hrefs: list[str],
        directory_url: str,
        resource_type: GEOResourceType,
    ) -> list[tuple[str, str]]:
        entries: dict[str, str] = {}
        for href in hrefs:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                continue
            decoded_path = unquote(parsed.path)
            if (
                not decoded_path
                or decoded_path.startswith("/")
                or decoded_path.endswith("/")
                or any(part in {"", ".", ".."} for part in decoded_path.split("/"))
            ):
                continue
            file_name = posixpath.basename(decoded_path)
            if file_name.casefold() == "filelist.txt":
                continue
            if not self._matches_resource(file_name, resource_type):
                continue
            entries[file_name] = urljoin(
                directory_url, quote(decoded_path, safe="-._~!$&'()*+,;=:@/")
            )
        return sorted(entries.items(), key=lambda item: item[0].casefold())

    @staticmethod
    def _matches_resource(file_name: str, resource_type: GEOResourceType) -> bool:
        lowered = file_name.casefold()
        if resource_type == GEOResourceType.SERIES_MATRIX:
            return lowered.endswith("series_matrix.txt.gz")
        if resource_type == GEOResourceType.SOFT:
            return lowered.endswith(".soft.gz")
        return True

    def _register_resource(
        self,
        *,
        task_id: str,
        accession: str,
        resource_type: GEOResourceType,
        file_name: str,
        download_url: str,
        download: bool,
        max_download_bytes: int,
        refresh: bool,
    ) -> GEOResourceRecord:
        status = "discovered"
        local_path: str | None = None
        checksum: str | None = None
        file_size: int | None = None
        if download:
            path, sha256, file_size, cache_hit = self._download_file(
                accession=accession,
                resource_type=resource_type,
                file_name=file_name,
                download_url=download_url,
                max_download_bytes=max_download_bytes,
                refresh=refresh,
            )
            local_path = self._display_path(path)
            checksum = f"sha256:{sha256}"
            status = "cached" if cache_hit else "downloaded"

        source_id_hash = hashlib.sha256(download_url.encode("utf-8")).hexdigest()[:16]
        source_item = SourceItem(
            source_id=f"geo:{accession}:{source_id_hash}",
            task_id=task_id,
            source_name="NCBI GEO",
            source_type="database",
            accession=accession,
            url=download_url,
            file_type=resource_type.value,
            local_path=local_path,
            checksum=checksum,
            status=status,
        )
        return GEOResourceRecord(
            accession=accession,
            resource_type=resource_type,
            file_name=file_name,
            download_url=download_url,
            status=status,
            file_size=file_size,
            source_item=source_item,
        )

    def _download_file(
        self,
        *,
        accession: str,
        resource_type: GEOResourceType,
        file_name: str,
        download_url: str,
        max_download_bytes: int,
        refresh: bool,
    ) -> tuple[Path, str, int, bool]:
        target = (
            self.cache_dir
            / "files"
            / accession
            / resource_type.value
            / self._safe_name(file_name)
        )
        manifest_path = target.with_name(f"{target.name}.metadata.json")
        if target.is_file() and manifest_path.is_file() and not refresh:
            manifest = self._read_file_manifest(manifest_path)
            actual_size = target.stat().st_size
            actual_sha256 = self._sha256_file(target)
            if (
                manifest.get("download_url") != download_url
                or manifest.get("file_size") != actual_size
                or manifest.get("sha256") != actual_sha256
            ):
                raise GEOAdapterError(
                    GEOErrorCode.CHECKSUM_MISMATCH,
                    f"Cached GEO file failed integrity verification: {file_name}",
                    details={
                        "accession": accession,
                        "file_name": file_name,
                        "expected": manifest.get("sha256"),
                        "actual": actual_sha256,
                    },
                )
            return target, actual_sha256, actual_size, True

        temporary: Path | None = None
        try:
            with self.client.stream("GET", download_url) as response:
                self._raise_for_status(
                    response,
                    url=download_url,
                    not_found_code=GEOErrorCode.RESOURCE_NOT_FOUND,
                )
                declared_size = self._content_length(response)
                if declared_size is not None and declared_size > max_download_bytes:
                    raise GEOAdapterError(
                        GEOErrorCode.DOWNLOAD_TOO_LARGE,
                        f"GEO file exceeds the configured download limit: {file_name}",
                        details={
                            "file_name": file_name,
                            "file_size": declared_size,
                            "max_download_bytes": max_download_bytes,
                        },
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".part")
                digest = hashlib.sha256()
                downloaded = 0
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        downloaded += len(chunk)
                        if downloaded > max_download_bytes:
                            raise GEOAdapterError(
                                GEOErrorCode.DOWNLOAD_TOO_LARGE,
                                f"GEO download exceeded the configured limit: {file_name}",
                                details={
                                    "file_name": file_name,
                                    "max_download_bytes": max_download_bytes,
                                },
                            )
                        handle.write(chunk)
                        digest.update(chunk)
        except GEOAdapterError:
            self._remove_partial(temporary)
            raise
        except httpx.TimeoutException as exc:
            self._remove_partial(temporary)
            raise GEOAdapterError(
                GEOErrorCode.TIMEOUT,
                f"GEO download timed out: {file_name}",
                retryable=True,
                details={"url": download_url},
            ) from exc
        except httpx.RequestError as exc:
            self._remove_partial(temporary)
            raise GEOAdapterError(
                GEOErrorCode.NETWORK_ERROR,
                f"GEO download failed: {file_name}",
                retryable=True,
                details={
                    "url": download_url,
                    "error_type": type(exc).__name__,
                },
            ) from exc
        except OSError as exc:
            self._remove_partial(temporary)
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"Could not write GEO cache file: {file_name}",
                details={"error_type": type(exc).__name__},
            ) from exc

        if declared_size is not None and downloaded != declared_size:
            self._remove_partial(temporary)
            raise GEOAdapterError(
                GEOErrorCode.DOWNLOAD_ERROR,
                f"Downloaded GEO file has an unexpected size: {file_name}",
                details={"expected": declared_size, "actual": downloaded},
            )
        sha256 = digest.hexdigest()
        if temporary is None:
            raise GEOAdapterError(
                GEOErrorCode.DOWNLOAD_ERROR,
                f"GEO download did not create a temporary file: {file_name}",
            )
        try:
            temporary.replace(target)
            self._write_file_manifest(
                manifest_path,
                {
                    "download_url": download_url,
                    "file_size": downloaded,
                    "sha256": sha256,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except OSError as exc:
            self._remove_partial(temporary)
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"Could not finalize GEO cache file: {file_name}",
                details={"error_type": type(exc).__name__},
            ) from exc
        return target, sha256, downloaded, False

    @staticmethod
    def _raise_for_status(
        response: httpx.Response, *, url: str, not_found_code: GEOErrorCode
    ) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 404:
            raise GEOAdapterError(
                not_found_code,
                f"GEO resource was not found: {url}",
                upstream_status=status,
                details={"url": url},
            )
        if status == 429:
            raise GEOAdapterError(
                GEOErrorCode.RATE_LIMITED,
                f"GEO rate limited the request: {url}",
                retryable=True,
                upstream_status=status,
                details={"url": url},
            )
        raise GEOAdapterError(
            GEOErrorCode.REMOTE_ERROR,
            f"GEO returned HTTP {status}: {url}",
            retryable=status >= 500,
            upstream_status=status,
            details={"url": url},
        )

    @staticmethod
    def _content_length(response: httpx.Response) -> int | None:
        value = response.headers.get("content-length")
        if value is None:
            return None
        try:
            length = int(value)
        except ValueError as exc:
            raise GEOAdapterError(
                GEOErrorCode.INVALID_RESPONSE,
                "GEO returned an invalid Content-Length header.",
                details={"content_length": value},
            ) from exc
        if length < 0:
            raise GEOAdapterError(
                GEOErrorCode.INVALID_RESPONSE,
                "GEO returned a negative Content-Length header.",
                details={"content_length": value},
            )
        return length

    def _read_directory_cache(self, path: Path) -> list[str] | None:
        if not path.is_file():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(envelope["cached_at"])
            hrefs = envelope["hrefs"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"GEO directory cache is unreadable: {path.name}",
            ) from exc
        if datetime.now(timezone.utc) - cached_at > self.cache_ttl:
            return None
        if not isinstance(hrefs, list) or not all(
            isinstance(href, str) for href in hrefs
        ):
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"GEO directory cache has invalid links: {path.name}",
            )
        return hrefs

    @staticmethod
    def _write_directory_cache(path: Path, *, url: str, hrefs: list[str]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "url": url,
                        "hrefs": hrefs,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"Could not write GEO directory cache: {path.name}",
            ) from exc

    @staticmethod
    def _read_file_manifest(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"GEO file manifest is unreadable: {path.name}",
            ) from exc
        if not isinstance(payload, dict):
            raise GEOAdapterError(
                GEOErrorCode.CACHE_ERROR,
                f"GEO file manifest is invalid: {path.name}",
            )
        return payload

    @staticmethod
    def _write_file_manifest(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
        return safe or "unnamed"

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _remove_partial(path: Path | None) -> None:
        if path is not None and path.is_file():
            path.unlink()

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)
