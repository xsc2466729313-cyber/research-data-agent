from __future__ import annotations

import csv
import io
from enum import Enum

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.models import CanonicalRecord, MockPipelineResult


class DatasetExportFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"


class DatasetExport:
    def __init__(self, *, content: bytes, media_type: str, filename: str) -> None:
        self.content = content
        self.media_type = media_type
        self.filename = filename


class MockDatasetExportService:
    """Serialize the reviewed mock CanonicalRecord output without altering values."""

    def export(
        self,
        result: MockPipelineResult,
        file_format: DatasetExportFormat,
    ) -> DatasetExport:
        rows = [record.model_dump(mode="json") for record in result.canonical_dataset]
        filename_base = f"{result.research_spec.task_id}-canonical-dataset"
        if file_format == DatasetExportFormat.CSV:
            return DatasetExport(
                content=self._csv(rows),
                media_type="text/csv; charset=utf-8",
                filename=f"{filename_base}.csv",
            )
        return DatasetExport(
            content=self._parquet(rows),
            media_type="application/vnd.apache.parquet",
            filename=f"{filename_base}.parquet",
        )

    @staticmethod
    def _csv(rows: list[dict[str, object]]) -> bytes:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=list(CanonicalRecord.model_fields),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return ("\ufeff" + stream.getvalue()).encode("utf-8")

    @staticmethod
    def _parquet(rows: list[dict[str, object]]) -> bytes:
        schema = pa.schema(
            [
                pa.field(name, pa.float64() if name == "confidence" else pa.string())
                for name in CanonicalRecord.model_fields
            ]
        )
        table = pa.Table.from_pylist(rows, schema=schema)
        stream = io.BytesIO()
        pq.write_table(table, stream, compression="snappy")
        return stream.getvalue()
