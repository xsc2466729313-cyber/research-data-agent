from __future__ import annotations

from enum import Enum
from typing import Any


class AACTErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    INVALID_QUERY = "invalid_query"
    NO_STUDIES = "no_studies"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    REMOTE_ERROR = "remote_error"
    INVALID_RESPONSE = "invalid_response"
    CACHE_ERROR = "cache_error"


class AACTAdapterError(RuntimeError):
    def __init__(
        self,
        code: AACTErrorCode,
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
        if self.code in {AACTErrorCode.INVALID_PLAN, AACTErrorCode.INVALID_QUERY}:
            return 400
        if self.code == AACTErrorCode.NO_STUDIES:
            return 404
        if self.code == AACTErrorCode.RATE_LIMITED:
            return 429
        if self.code == AACTErrorCode.TIMEOUT:
            return 504
        return 502
