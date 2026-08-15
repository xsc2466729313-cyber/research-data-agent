from __future__ import annotations

from enum import Enum
from typing import Any


class RepairErrorCode(str, Enum):
    INVALID_CONFIGURATION = "invalid_configuration"
    INTERNAL_ERROR = "internal_error"


class RepairError(RuntimeError):
    def __init__(
        self,
        code: RepairErrorCode,
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
        return 500
