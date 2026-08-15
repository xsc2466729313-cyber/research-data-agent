from __future__ import annotations

from enum import Enum
from typing import Any


class CIViCErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    INVALID_QUERY = "invalid_query"
    NO_EVIDENCE = "no_evidence"
    GRAPHQL_ERROR = "graphql_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_ERROR = "authentication_error"
    REMOTE_ERROR = "remote_error"
    INVALID_RESPONSE = "invalid_response"
    CACHE_ERROR = "cache_error"


class CIViCAdapterError(RuntimeError):
    def __init__(
        self,
        code: CIViCErrorCode,
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
        if self.code in {CIViCErrorCode.INVALID_PLAN, CIViCErrorCode.INVALID_QUERY}:
            return 400
        if self.code == CIViCErrorCode.NO_EVIDENCE:
            return 404
        if self.code == CIViCErrorCode.RATE_LIMITED:
            return 429
        if self.code == CIViCErrorCode.TIMEOUT:
            return 504
        return 502
