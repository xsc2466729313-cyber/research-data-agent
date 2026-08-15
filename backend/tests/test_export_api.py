from __future__ import annotations

import csv
import io

import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)
QUESTION = "研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应的关系"


def test_csv_export_contains_frozen_fields_and_business_values() -> None:
    response = client.post(
        "/api/tasks/mock/export/csv",
        json={"question": QUESTION},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].endswith(
        'task_mock_001-canonical-dataset.csv"'
    )
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 2
    assert rows[0]["study_id"] == "GSE25066"
    assert rows[0]["her2_status"] == "Positive"
    assert rows[1]["her2_status"] == "Equivocal"
    assert rows[1]["her2_raw_value"] == "2+"


def test_parquet_export_is_valid_and_preserves_medical_values() -> None:
    response = client.post(
        "/api/tasks/mock/export/parquet",
        json={"question": QUESTION},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apache.parquet"
    assert response.content[:4] == b"PAR1"
    assert response.content[-4:] == b"PAR1"
    table = pq.read_table(io.BytesIO(response.content))
    rows = table.to_pylist()
    assert table.num_rows == 2
    assert rows[0]["gene"] == "PIK3CA"
    assert rows[1]["her2_assay"] == "IHC"
    assert rows[1]["raw_value"] == "2+"


def test_export_rejects_unknown_format_and_unsupported_question() -> None:
    unknown_format = client.post(
        "/api/tasks/mock/export/xlsx",
        json={"question": QUESTION},
    )
    unsupported = client.post(
        "/api/tasks/mock/export/csv",
        json={"question": "研究肺癌中 EGFR 与总生存期"},
    )

    assert unknown_format.status_code == 422
    assert unsupported.status_code == 422
    assert "仅提供预置" in unsupported.json()["detail"]
