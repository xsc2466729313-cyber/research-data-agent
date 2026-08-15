from __future__ import annotations

from enum import Enum
from typing import Any


class EvaluationErrorCode(str, Enum):
    INVALID_GOLD_SET = "invalid_gold_set"
    OBSERVATION_MISMATCH = "observation_mismatch"
    DUPLICATE_EVALUATION = "duplicate_evaluation"
    ARTIFACT_NOT_FOUND = "artifact_not_found"
    ARTIFACT_WRITE_FAILED = "artifact_write_failed"


class EvaluationError(RuntimeError):
    def __init__(
        self,
        code: EvaluationErrorCode,
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
        if self.code == EvaluationErrorCode.DUPLICATE_EVALUATION:
            return 409
        if self.code == EvaluationErrorCode.ARTIFACT_NOT_FOUND:
            return 404
        if self.code == EvaluationErrorCode.ARTIFACT_WRITE_FAILED:
            return 500
        return 400
