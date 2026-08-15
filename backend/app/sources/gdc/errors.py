from __future__ import annotations

from enum import Enum
from typing import Any


class GDCErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    RATE_LIMITED = "rate_limited"
    API_ERROR = "api_error"
    INVALID_RESPONSE = "invalid_response"
    PROJECT_NOT_FOUND = "project_not_found"
    NO_FILES = "no_files"
    CACHE_ERROR = "cache_error"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    DOWNLOAD_ERROR = "download_error"
    CHECKSUM_MISMATCH = "checksum_mismatch"


class GDCAdapterError(RuntimeError):
    def __init__(
        self,
        code: GDCErrorCode,
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
        if self.code == GDCErrorCode.INVALID_PLAN:
            return 400
        if self.code in {GDCErrorCode.PROJECT_NOT_FOUND, GDCErrorCode.NO_FILES}:
            return 404
        if self.code == GDCErrorCode.AUTH_REQUIRED:
            return 401
        if self.code == GDCErrorCode.RATE_LIMITED:
            return 429
        if self.code == GDCErrorCode.TIMEOUT:
            return 504
        if self.code in {
            GDCErrorCode.DOWNLOAD_TOO_LARGE,
            GDCErrorCode.CHECKSUM_MISMATCH,
        }:
            return 422
        return 502

