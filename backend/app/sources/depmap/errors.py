from __future__ import annotations

from enum import Enum
from typing import Any


class DepMapErrorCode(str, Enum):
    INVALID_QUERY = "invalid_query"
    NETWORK_ERROR = "network_error"
    INVALID_RESPONSE = "invalid_response"
    NO_RECORDS = "no_records"


class DepMapAdapterError(RuntimeError):
    def __init__(
        self,
        code: DepMapErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
