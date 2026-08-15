from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.app.evaluation.errors import EvaluationError, EvaluationErrorCode
from backend.app.evaluation.models import (
    ErrorGoldCase,
    EvaluationStatus,
    FieldGoldCase,
    GoldSetBundle,
    GoldSetManifest,
    GoldSetTemplateInspection,
    RetrievalGoldCase,
)


REQUIRED_HEADERS = {
    "retrieval_gold.csv": [
        "question_id",
        "research_question",
        "dataset_id",
        "label",
        "label_source",
        "review_status",
        "notes",
    ],
    "field_gold.csv": [
        "case_id",
        "source_dataset",
        "raw_field",
        "raw_value",
        "canonical_field",
        "canonical_value",
        "allowed_auto_transform",
        "label_source",
        "review_status",
        "notes",
    ],
    "error_gold.csv": [
        "case_id",
        "error_type",
        "original_record",
        "expected_detection",
        "expected_repair",
        "auto_repair_allowed",
        "risk_level",
        "review_status",
        "notes",
    ],
}


def compute_gold_set_checksum(bundle: GoldSetBundle) -> str:
    payload = {
        "retrieval_gold": sorted(
            [row.model_dump(mode="json") for row in bundle.retrieval_gold],
            key=lambda row: (row["question_id"], row["dataset_id"]),
        ),
        "field_gold": sorted(
            [row.model_dump(mode="json") for row in bundle.field_gold],
            key=lambda row: row["case_id"],
        ),
        "error_gold": sorted(
            [row.model_dump(mode="json") for row in bundle.error_gold],
            key=lambda row: row["case_id"],
        ),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class GoldSetCsvLoader:
    def inspect(self, directory: Path) -> GoldSetTemplateInspection:
        rows = self._read_all(directory)
        row_counts = {filename: len(items) for filename, items in rows.items()}
        has_all_sets = all(count > 0 for count in row_counts.values())
        return GoldSetTemplateInspection(
            status=EvaluationStatus.NOT_EVALUATED,
            directory=str(directory.resolve()),
            required_headers=REQUIRED_HEADERS,
            row_counts=row_counts,
            notice=(
                "CSV 模板已包含行，仍需要冻结的 Gold Set manifest 与系统观察结果才能计算指标。"
                if has_all_sets
                else "当前仅有空 Gold Set 模板，不会生成任何评测成绩。"
            ),
        )

    def load(self, directory: Path, manifest: GoldSetManifest) -> GoldSetBundle:
        rows = self._read_all(directory)
        try:
            retrieval = [
                RetrievalGoldCase.model_validate(self._normalize_retrieval(row))
                for row in rows["retrieval_gold.csv"]
            ]
            fields = [
                FieldGoldCase.model_validate(self._normalize_field(row))
                for row in rows["field_gold.csv"]
            ]
            errors = [
                ErrorGoldCase.model_validate(self._normalize_error(row))
                for row in rows["error_gold.csv"]
            ]
        except (ValidationError, ValueError) as exc:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Gold Set CSV contains an invalid row.",
                details={"error": str(exc)},
            ) from exc
        return GoldSetBundle(
            manifest=manifest,
            retrieval_gold=retrieval,
            field_gold=fields,
            error_gold=errors,
        )

    def _read_all(self, directory: Path) -> dict[str, list[dict[str, str]]]:
        if not directory.is_dir():
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Gold Set template directory does not exist.",
                details={"directory": str(directory)},
            )
        return {
            filename: self._read_csv(directory / filename, headers)
            for filename, headers in REQUIRED_HEADERS.items()
        }

    @staticmethod
    def _read_csv(path: Path, headers: list[str]) -> list[dict[str, str]]:
        if not path.is_file():
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Required Gold Set CSV is missing.",
                details={"path": str(path)},
            )
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                actual = reader.fieldnames or []
                if actual != headers:
                    raise EvaluationError(
                        EvaluationErrorCode.INVALID_GOLD_SET,
                        "Gold Set CSV headers do not match the frozen template.",
                        details={
                            "path": str(path),
                            "expected": headers,
                            "actual": actual,
                        },
                    )
                return [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            raise EvaluationError(
                EvaluationErrorCode.INVALID_GOLD_SET,
                "Gold Set CSV must be UTF-8 encoded.",
                details={"path": str(path)},
            ) from exc

    @staticmethod
    def _boolean(value: str, field: str) -> bool:
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ValueError(f"{field} must be true/false, 1/0, or yes/no")

    @staticmethod
    def _normalize_retrieval(row: dict[str, str]) -> dict[str, Any]:
        label = row["label"].strip().casefold()
        aliases = {
            "relevant": "relevant",
            "1": "relevant",
            "true": "relevant",
            "not_relevant": "not_relevant",
            "irrelevant": "not_relevant",
            "0": "not_relevant",
            "false": "not_relevant",
        }
        if label not in aliases:
            raise ValueError("label must identify relevant or not_relevant")
        return {**row, "label": aliases[label]}

    @classmethod
    def _normalize_field(cls, row: dict[str, str]) -> dict[str, Any]:
        return {
            **row,
            "allowed_auto_transform": cls._boolean(
                row["allowed_auto_transform"], "allowed_auto_transform"
            ),
        }

    @classmethod
    def _normalize_error(cls, row: dict[str, str]) -> dict[str, Any]:
        return {
            **row,
            "expected_detection": cls._boolean(
                row["expected_detection"], "expected_detection"
            ),
            "expected_repair": row["expected_repair"] or None,
            "auto_repair_allowed": cls._boolean(
                row["auto_repair_allowed"], "auto_repair_allowed"
            ),
        }
