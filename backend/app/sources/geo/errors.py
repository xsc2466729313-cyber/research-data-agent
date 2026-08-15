from __future__ import annotations

from enum import Enum
from typing import Any


class GEOErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    INVALID_ACCESSION = "invalid_accession"
    ACCESSION_NOT_FOUND = "accession_not_found"
    RESOURCE_NOT_FOUND = "resource_not_found"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    REMOTE_ERROR = "remote_error"
    INVALID_RESPONSE = "invalid_response"
    CACHE_ERROR = "cache_error"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    DOWNLOAD_ERROR = "download_error"
    CHECKSUM_MISMATCH = "checksum_mismatch"


class GEOAdapterError(RuntimeError):
    def __init__(
        self,
        code: GEOErrorCode,
        message: str,
        *,
        retryable: bool = False,
        upstream_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.upstream_status = upstream_status
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "upstream_status": self.upstream_status,
            "details": self.details,
        }

    @property
    def http_status(self) -> int:
        if self.code in {GEOErrorCode.INVALID_PLAN, GEOErrorCode.INVALID_ACCESSION}:
            return 400
        if self.code in {
            GEOErrorCode.ACCESSION_NOT_FOUND,
            GEOErrorCode.RESOURCE_NOT_FOUND,
        }:
            return 404
        if self.code == GEOErrorCode.RATE_LIMITED:
            return 429
        if self.code == GEOErrorCode.TIMEOUT:
            return 504
        if self.code in {
            GEOErrorCode.DOWNLOAD_TOO_LARGE,
            GEOErrorCode.CHECKSUM_MISMATCH,
        }:
            return 422
        return 502
