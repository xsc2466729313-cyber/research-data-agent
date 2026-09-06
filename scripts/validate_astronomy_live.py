"""Opt-in network acceptance check; never used as a fixture or offline test."""
from __future__ import annotations

import csv
import io
import json
from zipfile import ZipFile

from backend.app.astronomy import AstronomyRequest, AstronomyService


if __name__ == "__main__":
    service = AstronomyService()
    try:
        created = service.create(AstronomyRequest(topic="我希望研究 Ia 型超新星光变曲线", sources=["cfa4", "ksp"]))
        print(f"task_id={created['task_id']}", flush=True)
        service.jobs[created["task_id"]].result(timeout=300)
        result = service.get(created["task_id"])
        csv_content, _, _ = service.export(result["task_id"], "csv")
        rows = list(csv.DictReader(io.StringIO(csv_content.decode("utf-8-sig"))))
        assert len(rows) == len(result["rows"]) > 0
        assert all(row["source_id"] and row["source_url"] and json.loads(row["raw_value"])["observation"] for row in rows)
        for format in ("xlsx", "sources"):
            content, _, _ = service.export(result["task_id"], format)
            with ZipFile(io.BytesIO(content)) as archive:
                assert archive.testzip() is None
        print(json.dumps({"task_id": result["task_id"], "status": result["status"], "rows": len(rows),
                          "sources": [{key: source.get(key) for key in ("source_id", "url", "row_count", "sha256")} for source in result["sources"]],
                          "errors": result["errors"], "workflow": result["workflow"],
                          "csv_bytes": len(csv_content)}, ensure_ascii=False), flush=True)
        assert result["status"] == "completed", "Live acquisition was not fully completed; inspect reported errors"
    finally:
        service.pool.shutdown(wait=True)
