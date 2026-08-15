from __future__ import annotations

from enum import Enum
from typing import Any


class IntegrationErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNREGISTERED_SOURCE = "unregistered_source"
    DUPLICATE_ID = "duplicate_id"
    INTERNAL_ERROR = "internal_error"


class IntegrationError(RuntimeError):
    def __init__(
        self,
        code: IntegrationErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": False,
            "details": self.details,
        }

    @property
    def http_status(self) -> int:
        return 400 if self.code != IntegrationErrorCode.INTERNAL_ERROR else 500
