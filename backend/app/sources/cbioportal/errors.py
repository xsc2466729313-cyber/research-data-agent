from __future__ import annotations

from enum import Enum
from typing import Any


class CBioPortalErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    INVALID_STUDY_ID = "invalid_study_id"
    INVALID_SELECTION = "invalid_selection"
    STUDY_NOT_FOUND = "study_not_found"
    PROFILE_NOT_FOUND = "profile_not_found"
    SAMPLE_LIST_NOT_FOUND = "sample_list_not_found"
    GENE_NOT_FOUND = "gene_not_found"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    RATE_LIMITED = "rate_limited"
    REMOTE_ERROR = "remote_error"
    INVALID_RESPONSE = "invalid_response"
    CACHE_ERROR = "cache_error"


class CBioPortalAdapterError(RuntimeError):
    def __init__(
        self,
        code: CBioPortalErrorCode,
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
        if self.code in {
            CBioPortalErrorCode.INVALID_PLAN,
            CBioPortalErrorCode.INVALID_STUDY_ID,
            CBioPortalErrorCode.INVALID_SELECTION,
        }:
            return 400
        if self.code in {
            CBioPortalErrorCode.STUDY_NOT_FOUND,
            CBioPortalErrorCode.PROFILE_NOT_FOUND,
            CBioPortalErrorCode.SAMPLE_LIST_NOT_FOUND,
            CBioPortalErrorCode.GENE_NOT_FOUND,
        }:
            return 404
        if self.code == CBioPortalErrorCode.AUTH_REQUIRED:
            return 401
        if self.code == CBioPortalErrorCode.RATE_LIMITED:
            return 429
        if self.code == CBioPortalErrorCode.TIMEOUT:
            return 504
        return 502
