"""Observed light curves, separate from the frozen patient schema.

Bindings describe published tables, never expected answers or row counts.
Every run fetches the source again and retains the response used to build it.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi import FastAPI, HTTPException, Response
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from pydantic import BaseModel, Field
from .astronomy_quality import clean_observations
from .astronomy_export import workbook_bytes, ANALYSIS_FIELDS


BINDINGS = {
    "cfa4": {"catalog": "J/ApJS/200/12", "table": "table6", "band": "Filt", "error": "e_mag"},
    "ksp": {"catalog": "J/ApJ/959/132", "table": "table1", "band": "Band", "error": "emagTot"},
}
FIELDS = ["observation_id", "object_id", "mjd", "time_unit", "time_scale", "band",
          "magnitude", "magnitude_error", "magnitude_system", "redshift_heliocentric",
          "redshift_cmb", "source_id", "source_url", "source_row", "metadata_source_id",
          "metadata_source_url", "metadata_match", "raw_field", "raw_value"]
LIMITATIONS = [
    "这是已接入目录范围内的观测汇编，不是全网穷尽检索；未执行光变拟合或科学结论推断。",
    "星等、滤镜及原始测光系统分别保留；未统一零点、消光或 K 修正，不生成无依据的 flux。",
    "MJD 单位为天；来源未明确给出时间尺度，不推定 UTC/TDB。不同目录只纵向拼接，不跨目录认定同一对象。",
    "本次使用已发表的机器可读观测表，未从论文图片提取坐标；图像数字化和人工校验尚未接入。",
]


class AstronomyRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=2000)
    sources: list[str] = Field(default_factory=lambda: ["cfa4"], min_length=1, max_length=2)


def parse_votable(content: bytes, table_name: str) -> tuple[dict, list[dict]]:
    root = ET.fromstring(content)
    for info in root.findall(".//{*}INFO"):
        if info.get("name", "").upper() == "QUERY_STATUS" and info.get("value", "").upper() in {"ERROR", "OVERFLOW"}:
            raise ValueError(f"VizieR {info.get('value')}: {info.text or ''}")
    table = next((t for t in root.findall(".//{*}TABLE") if t.get("name") == table_name), None)
    if table is None or table.find("./{*}DATA/{*}TABLEDATA") is None:
        raise ValueError(f"缺少预期 TABLEDATA：{table_name}")
    fields = {f.get("name"): {**f.attrib, "description": f.findtext("{*}DESCRIPTION", "")}
              for f in table.findall("{*}FIELD")}
    rows = []
    for tr in table.findall("./{*}DATA/{*}TABLEDATA/{*}TR"):
        cells = [td.text or "" for td in tr.findall("{*}TD")]
        if len(cells) != len(fields):
            raise ValueError("VOTable 列数不一致，不能静默错位")
        rows.append(dict(zip(fields, cells)))
    return fields, rows


def number(value: str) -> float | None:
    if not value.strip():
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("非有限数值")
    return result


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


class AstronomyService:
    def __init__(self, directory: Path | None = None, fetch=None):
        self.directory = directory or Path(__file__).resolve().parents[1] / "data" / "astronomy"
        self.fetch = fetch or self._fetch
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="astronomy")
        self.jobs = {}

    @staticmethod
    def _fetch(url: str) -> bytes:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content

    def _path(self, task_id: str) -> Path:
        if not re.fullmatch(r"astro-[0-9a-f]{32}", task_id):
            raise KeyError(task_id)
        return self.directory / task_id

    def _save(self, result):
        directory = self._path(result["task_id"])
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "result.tmp"
        temporary.write_bytes(json_bytes(result))
        temporary.replace(directory / "result.json")

    def create(self, request: AstronomyRequest) -> dict:
        if any(source not in BINDINGS for source in request.sources):
            raise ValueError("未接入的天文来源")
        if not re.search(r"(?:[il]a\s*型\s*(?:超新星|光变|曲线)|(?:type\s*ia|sn\s*ia).*?(?:light\s*curve|photometr))", request.topic, re.I):
            raise ValueError("此接口仅支持 Ia 型超新星光变观测，不会把其他研究对象替换为示例数据。")
        result = {"task_id": f"astro-{uuid4().hex}", "topic": request.topic, "status": "running",
                  "requested_sources": list(dict.fromkeys(request.sources)), "rows": [], "sources": [],
                  "workflow": [], "errors": [], "rejected_rows": [], "limitations": LIMITATIONS,
                  "created_at": datetime.now(timezone.utc).isoformat(), "schema": FIELDS}
        self._save(result)
        self.jobs[result["task_id"]] = self.pool.submit(self._execute, result)
        return self.summary(result)

    def clean_existing(self, task_id: str) -> dict:
        """Create a new immutable version from the saved parsed/raw evidence."""
        parent = self.get(task_id)
        if parent["status"] == "running":
            raise ValueError("任务仍在获取中，完成后再执行清洗")
        child = {"task_id": f"astro-{uuid4().hex}", "parent_task_id": task_id,
                 "topic": parent["topic"], "status": "running", "requested_sources": parent["requested_sources"],
                 "rows": json.loads(json.dumps(parent.get("rows", []))), "sources": json.loads(json.dumps(parent.get("sources", []))),
                 "workflow": json.loads(json.dumps(parent.get("workflow", []))), "errors": list(parent.get("errors", [])),
                 "rejected_rows": json.loads(json.dumps(parent.get("rejected_rows", []))), "limitations": parent["limitations"],
                 "created_at": datetime.now(timezone.utc).isoformat(), "schema": FIELDS, "acquisition_mode": "saved_evidence"}
        self._save(child)
        source_dir, child_dir = self._path(task_id), self._path(child["task_id"])
        for source in child["sources"]:
            source_file = source_dir / source["file"]
            if source_file.exists():
                shutil.copy2(source_file, child_dir / source["file"])
        def run():
            clean_observations(child)
            child["status"] = "completed" if child["rows"] else "failed"
            child["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(child)
        self.jobs[child["task_id"]] = self.pool.submit(run)
        return self.summary(child)

    def _download(self, result: dict, name: str, url: str, table: str | None = None):
        content = self.fetch(url)
        (self._path(result["task_id"]) / name).write_bytes(content)
        source = {"source_id": table or name, "url": url, "file": name,
                  "retrieved_at": datetime.now(timezone.utc).isoformat(),
                  "sha256": hashlib.sha256(content).hexdigest()}
        result["sources"].append(source)
        if table:
            fields, rows = parse_votable(content, table)
            source.update(fields=fields, row_count=len(rows))
            root = ET.fromstring(content)
            source["publication"] = {info.get("name"): info.get("value") for info in root.findall(".//{*}INFO")
                                     if info.get("name") in {"cites", "citation", "reference_url", "creator"}}
            return fields, rows, source
        return content, source

    def _table(self, result, family, table):
        name = f"{BINDINGS[family]['catalog']}/{table}"
        url = f"https://vizier.cds.unistra.fr/viz-bin/votable?-source={name}&-out.all&-out.max=100000"
        return self._download(result, f"{family}-{table}.xml", url, name)

    def _family(self, result, family):
        binding = BINDINGS[family]
        metadata, metadata_source = {}, None
        single_object = None
        if family == "cfa4":
            try:
                _, records, metadata_source = self._table(result, family, "table1")
                for record in records:
                    key = record.get("SN", "").strip()
                    if not key or key in metadata:
                        raise ValueError("元数据 SN 主键缺失或不唯一")
                    metadata[key] = record
            except Exception as exc:
                metadata = {}
                result["errors"].append(f"{family} 元数据关联未执行：{exc}")
        else:
            url = f"https://cdsarc.cds.unistra.fr/ftp/cats/{binding['catalog']}/ReadMe"
            content, metadata_source = self._download(result, "ksp-ReadMe.txt", url)
            readme = content.decode("utf-8")
            objects = readme.split("Objects:", 1)[-1].split("File Summary:", 1)[0]
            names = re.findall(r"\bSN\s+(\d{4}[a-z]+)\s*=", objects)
            if len(names) != 1:
                raise ValueError("ReadMe 未提供唯一单对象身份，不能给观测行猜测名称")
            single_object = f"SN {names[0]}"
            # The object's redshift frame is not specified here; do not populate heliocentric/CMB.
        fields, records, source = self._table(result, family, binding["table"])
        required = {"MJD": "d", "mag": "mag", binding["error"]: "mag", binding["band"]: None}
        if family == "cfa4":
            required["SN"] = None
        for field, unit in required.items():
            if field not in fields or (unit and fields[field].get("unit") != unit):
                raise ValueError(f"字段或单位不符：{field}，预期 {unit}")
        matched = 0
        accepted = []
        for index, raw in enumerate(records, 1):
            try:
                mjd, magnitude, error = (number(raw[key]) for key in ("MJD", "mag", binding["error"]))
                band = raw[binding["band"]].strip()
                object_name = single_object or raw["SN"].strip()
                if mjd is None or magnitude is None or error is None or error < 0 or not band or not object_name:
                    raise ValueError("必要字段缺失或星等误差为负")
                meta = metadata.get(object_name, {})
                redshifts = {}
                for target, field in (("redshift_heliocentric", "z"), ("redshift_cmb", "zCMB")):
                    try:
                        redshifts[target] = number(meta.get(field, ""))
                    except ValueError:
                        redshifts[target] = None
                        result["errors"].append(f"{family} 元数据 {object_name}/{field} 无效，保留空值")
                matched += bool(meta)
                # Full field definitions live once in the source manifest; original strings remain per row.
                accepted.append({"observation_id": f"{source['source_id']}:{index}",
                    "object_id": f"{family}:{object_name}", "mjd": mjd, "time_unit": "d",
                    "time_scale": "unspecified", "band": band, "magnitude": magnitude,
                    "magnitude_error": error, "magnitude_system": "source_native",
                    **redshifts, "source_id": source["source_id"], "source_url": source["url"],
                    "source_row": index, "metadata_source_id": metadata_source["source_id"] if (meta or single_object) else None,
                    "metadata_source_url": metadata_source["url"] if (meta or single_object) else None,
                    "metadata_match": "catalog_exact_SN" if meta else "ReadMe_single_object" if single_object else "unresolved",
                    "raw_field": {"object_id": "SN" if family == "cfa4" else "ReadMe.Objects",
                                  "mjd": "MJD", "band": binding["band"], "magnitude": "mag",
                                  "magnitude_error": binding["error"], "redshift_heliocentric": "table1.z",
                                  "redshift_cmb": "table1.zCMB"} if family == "cfa4" else
                                 {"object_id": "ReadMe.Objects", "mjd": "MJD", "band": binding["band"],
                                  "magnitude": "mag", "magnitude_error": binding["error"]},
                    "raw_value": {"observation": raw, "metadata": meta or ({"Objects": objects.strip()} if single_object else {})}})
            except (ValueError, KeyError) as exc:
                result["rejected_rows"].append({"source_id": source["source_id"], "source_row": index,
                                                "reason": str(exc), "raw_value": raw})
        result["rows"].extend(accepted)
        result["workflow"].append({"source": family, "operation": "parse_and_align",
            "input_rows": len(records), "output_rows": len(accepted), "metadata_matched_rows": matched,
            "identity_rule": "catalog-local exact SN, many-to-one" if family == "cfa4" else "ReadMe single object only",
            "field_mapping": {"mjd": "MJD", "band": binding["band"], "magnitude": "mag", "magnitude_error": binding["error"]}})

    def _execute(self, result):
        try:
            for family in result["requested_sources"]:
                try:
                    self._family(result, family)
                except Exception as exc:
                    result["errors"].append(f"{family} 获取/解析失败：{exc}")
                self._save(result)
            result["workflow"].append({"operation": "union_by_column_name", "output_rows": len(result["rows"]),
                                       "cross_catalog_identity_join": False})
            clean_observations(result)
            result["status"] = ("partial" if result["errors"] or result["rejected_rows"] else "completed") if result["rows"] else "failed"
        except Exception as exc:
            result["errors"].append(str(exc))
            result["status"] = "failed"
        finally:
            result["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(result)

    def get(self, task_id):
        try:
            result = json.loads((self._path(task_id) / "result.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KeyError(task_id) from exc
        if result["status"] == "running" and task_id not in self.jobs:
            result["status"] = "interrupted"
            result["errors"].append("后端重启中断本次获取，可重新运行；已完成内容仍可下载。")
        return result

    @staticmethod
    def summary(result):
        return {**{k: v for k, v in result.items() if k not in {"rows", "rejected_rows"}},
                "row_count": len(result["rows"]), "rejected_count": len(result["rejected_rows"]),
                "preview": [{k: v for k, v in row.items() if k not in {"raw_field", "raw_value"}} for row in result["rows"][:12]]}

    def export(self, task_id, file_format):
        result = self.get(task_id)
        if file_format in {"csv", "xlsx"} and not result["rows"]:
            raise ValueError("尚无可导出的观测数据；可下载质量报告查看原因。")
        if file_format == "quality_report":
            return json_bytes({**self.summary(result), "cleaning_report": result.get("cleaning_report", {}),
                               "quality_gate": result.get("quality_gate", {}), "rejected_rows": result["rejected_rows"],
                               "review_rows": result.get("review_rows", []), "duplicate_rows": result.get("duplicate_rows", [])}), "application/json", "json"
        if file_format == "sources":
            stream = io.BytesIO()
            with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json_bytes(self.summary(result)))
                archive.writestr("canonical_audit.json", json_bytes({
                    "task_id": task_id, "pipeline_version": result.get("pipeline_version"),
                    "cleaning_report": result.get("cleaning_report", {}),
                    "cleaning_events": result.get("cleaning_events", []),
                    "rows": result.get("rows", []), "review_rows": result.get("review_rows", []),
                    "duplicate_rows": result.get("duplicate_rows", []),
                }))
                for source in result["sources"]:
                    archive.write(self._path(task_id) / source["file"], source["file"])
            return stream.getvalue(), "application/zip", "zip"
        rows = [[row.get(key) for key in ANALYSIS_FIELDS] for row in result["rows"]]
        if file_format == "csv":
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(ANALYSIS_FIELDS)
            writer.writerows([["'" + cell if isinstance(cell, str) and cell.startswith(("=", "+", "-", "@", "\t", "\r")) else cell for cell in row] for row in rows])
            return stream.getvalue().encode("utf-8-sig"), "text/csv", "csv"
        if file_format == "xlsx":
            raw_tables = []
            for source in result["sources"]:
                if not source.get("file", "").endswith(".xml"):
                    continue
                try:
                    raw_fields, raw_records = parse_votable((self._path(task_id) / source["file"]).read_bytes(), source["source_id"])
                    raw_tables.append((source["source_id"].replace("/", "_"), source["source_id"], list(raw_fields), raw_records))
                except (OSError, ValueError):
                    continue
            return workbook_bytes(result, raw_tables), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
        raise ValueError("不支持的导出格式")


def mount_astronomy_routes(app: FastAPI):
    app.state.astronomy_service = AstronomyService()

    @app.post("/api/astronomy/tasks", status_code=202)
    def create(request: AstronomyRequest):
        try:
            return app.state.astronomy_service.create(request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/astronomy/tasks/{task_id}")
    def get(task_id: str):
        try:
            return app.state.astronomy_service.summary(app.state.astronomy_service.get(task_id))
        except KeyError as exc:
            raise HTTPException(404, "未找到该对话的天文任务") from exc

    @app.post("/api/astronomy/tasks/{task_id}/clean", status_code=202)
    def clean(task_id: str):
        try:
            return app.state.astronomy_service.clean_existing(task_id)
        except KeyError as exc:
            raise HTTPException(404, "未找到该对话的天文任务") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/astronomy/tasks/{task_id}/export/{file_format}")
    def export(task_id: str, file_format: str):
        try:
            content, media, extension = app.state.astronomy_service.export(task_id, file_format)
            return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{task_id}.{extension}"'})
        except KeyError as exc:
            raise HTTPException(404, "未找到该对话的天文任务") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
