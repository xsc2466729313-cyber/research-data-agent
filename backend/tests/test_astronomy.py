from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.astronomy import AstronomyRequest, AstronomyService, mount_astronomy_routes, parse_votable


def table(name, fields, rows):
    root = ET.Element("VOTABLE", xmlns="http://www.ivoa.net/xml/VOTable/v1.3")
    tab = ET.SubElement(ET.SubElement(root, "RESOURCE"), "TABLE", name=name)
    for field, unit in fields:
        ET.SubElement(tab, "FIELD", name=field, unit=unit, datatype="char")
    data = ET.SubElement(ET.SubElement(tab, "DATA"), "TABLEDATA")
    for values in rows:
        tr = ET.SubElement(data, "TR")
        for value in values:
            ET.SubElement(tr, "TD").text = value
    return ET.tostring(root)


def source_responses():
    # Synthetic parser fixtures, not application data or benchmark answers.
    return {
        "J/ApJS/200/12/table1": table("J/ApJS/200/12/table1", [("SN", ""), ("z", ""), ("zCMB", "")], [["SN fixture", "0.01", "0.02"]]),
        "J/ApJS/200/12/table6": table("J/ApJS/200/12/table6", [("SN", ""), ("MJD", "d"), ("Filt", ""), ("mag", "mag"), ("e_mag", "mag")],
                                   [[" SN fixture ", "55000", "B", "14.5", "0.1"], ["SN missing", "55001", "V", "15.0", "0.2"]]),
        "J/ApJ/959/132/table1": table("J/ApJ/959/132/table1", [("MJD", "d"), ("Band", ""), ("mag", "mag"), ("emagTot", "mag")],
                                    [["59500", "i", "13.4", "0.12"]]),
        "ReadMe": b"Objects:\n SN 2020fixture = test object (z=0.003)\nFile Summary:\n",
    }


def fake_fetch(responses):
    def fetch(url):
        key = "ReadMe" if url.endswith("ReadMe") else url.split("-source=", 1)[1].split("&")[0]
        value = responses[key]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


@pytest.fixture
def service(tmp_path):
    service = AstronomyService(tmp_path, fake_fetch(source_responses()))
    yield service
    service.pool.shutdown(wait=True)


def completed(service, sources=None):
    created = service.create(AstronomyRequest(topic="我希望研究 Ia 型超新星光变曲线", sources=sources or ["cfa4"]))
    service.jobs[created["task_id"]].result(timeout=5)
    return service.get(created["task_id"])


def test_exact_join_preserves_raw_values_and_unresolved_metadata(service):
    result = completed(service)
    assert result["status"] == "completed"
    first, unmatched = result["rows"]
    assert first["redshift_heliocentric"] == .01
    assert first["redshift_cmb"] == .02
    assert first["raw_value"]["observation"]["SN"] == " SN fixture "
    assert first["raw_field"]["mjd"] == "MJD"
    assert result["sources"][1]["fields"]["MJD"]["unit"] == "d"
    assert first["metadata_source_id"].endswith("table1")
    assert unmatched["metadata_match"] == "unresolved"
    assert unmatched["redshift_cmb"] is None
    assert all(row["time_scale"] == "unspecified" and "flux" not in row for row in result["rows"])


def test_two_catalog_union_and_exports_are_task_scoped_and_survive_restart(service):
    first = completed(service)
    second = completed(service, ["cfa4", "ksp"])
    restored = AstronomyService(service.directory)
    try:
        assert len(second["rows"]) == 3
        assert second["rows"][-1]["object_id"] == "ksp:SN 2020fixture"
        assert second["rows"][-1]["redshift_heliocentric"] is None
        for result, count in ((first, 2), (second, 3)):
            content, _, _ = restored.export(result["task_id"], "csv")
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
            assert len(rows) == count
            assert "raw_value" not in rows[0]
            assert all(row["quality_status"] == "usable_observation" for row in rows)
            raw, _, _ = restored.export(result["task_id"], "sources")
            with ZipFile(io.BytesIO(raw)) as archive:
                assert archive.testzip() is None
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["task_id"] == result["task_id"]
                assert manifest["sources"][0]["sha256"]
            workbook, _, _ = restored.export(result["task_id"], "xlsx")
            with ZipFile(io.BytesIO(workbook)) as archive:
                assert archive.testzip() is None
    finally:
        restored.pool.shutdown()


@pytest.mark.parametrize("bad", [b"<html>error</html>", b'<VOTABLE><INFO name="QUERY_STATUS" value="OVERFLOW"/></VOTABLE>', b'<VOTABLE><INFO name="QUERY_STATUS" value="ERROR"/></VOTABLE>'])
def test_rejects_invalid_or_truncated_source(bad):
    with pytest.raises(ValueError):
        parse_votable(bad, "test")


def test_failure_is_reported_without_fabricating_rows(service):
    responses = source_responses()
    responses["J/ApJS/200/12/table6"] = RuntimeError("offline")
    service.fetch = fake_fetch(responses)
    failed = completed(service)
    assert failed["status"] == "failed" and not failed["rows"]
    with pytest.raises(ValueError, match="尚无"):
        service.export(failed["task_id"], "csv")
    partial = completed(service, ["cfa4", "ksp"])
    assert partial["status"] == "partial"
    assert len(partial["rows"]) == 1
    assert "offline" in partial["errors"][0]


def test_units_negative_uncertainty_and_duplicate_metadata(service):
    responses = source_responses()
    responses["J/ApJS/200/12/table6"] = responses["J/ApJS/200/12/table6"].replace(b'unit="d"', b'unit="s"')
    service.fetch = fake_fetch(responses)
    assert completed(service)["status"] == "failed"
    responses = source_responses()
    responses["J/ApJS/200/12/table6"] = responses["J/ApJS/200/12/table6"].replace(b">0.1<", b">-0.1<")
    responses["J/ApJS/200/12/table1"] = responses["J/ApJS/200/12/table1"].replace(b"</TABLEDATA>", b"<TR><TD>SN fixture</TD><TD>0.9</TD><TD>0.8</TD></TR></TABLEDATA>")
    service.fetch = fake_fetch(responses)
    result = completed(service)
    assert result["status"] == "partial"
    assert len(result["rejected_rows"]) == 1
    assert len(result["rows"]) == 1
    assert result["rows"][0]["redshift_heliocentric"] is None


def test_api_routes_and_missing_tasks(service):
    app = FastAPI()
    mount_astronomy_routes(app)
    app.state.astronomy_service.pool.shutdown()
    app.state.astronomy_service = service
    client = TestClient(app)
    created = client.post("/api/astronomy/tasks", json={"topic": "研究 Ia 型超新星光变曲线"})
    assert created.status_code == 202
    task_id = created.json()["task_id"]
    service.jobs[task_id].result(timeout=5)
    result = client.get(f"/api/astronomy/tasks/{task_id}").json()
    assert result["row_count"] == 2 and "rows" not in result
    assert len(list(csv.DictReader(io.StringIO(client.get(f"/api/astronomy/tasks/{task_id}/export/csv").content.decode("utf-8-sig"))))) == 2
    assert client.get("/api/astronomy/tasks/astro-missing/export/csv").status_code == 404
    assert client.post("/api/astronomy/tasks", json={"topic": "test", "sources": ["unknown"]}).status_code == 422
    assert client.post("/api/astronomy/tasks", json={"topic": "研究 II 型超新星光变曲线"}).status_code == 422


def test_interrupted_task_can_be_read_after_restart(service):
    result = completed(service)
    result["status"] = "running"
    service._save(result)
    restarted = AstronomyService(service.directory)
    try:
        restored = restarted.get(result["task_id"])
        assert restored["status"] == "interrupted"
        assert len(restored["rows"]) == 2
    finally:
        restarted.pool.shutdown()


def test_cleaning_creates_a_new_auditable_version_and_separates_analysis_export(service):
    parent = completed(service)
    child_summary = service.clean_existing(parent["task_id"])
    service.jobs[child_summary["task_id"]].result(timeout=5)
    child = service.get(child_summary["task_id"])
    assert child["parent_task_id"] == parent["task_id"]
    assert child["pipeline_version"] == "observation-cleaning-v1"
    assert child["cleaning_report"]["reconciled"]
    assert child["quality_gate"]["overall"] == "REVIEW"
    workbook, _, _ = service.export(child["task_id"], "xlsx")
    with ZipFile(io.BytesIO(workbook)) as archive:
        xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert "raw_value" not in xml
        assert archive.testzip() is None
