from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.app.models import SourceItem
from backend.app.sources.depmap.errors import DepMapAdapterError, DepMapErrorCode
from backend.app.sources.depmap.models import DepMapAdapterResult, DepMapCellLineRecord


class DepMapAdapter:
    """Official DepMap portal cell-line drug sensitivity. Never patient pCR."""

    PORTAL_URL = "https://depmap.org/portal/"
    DOWNLOADS_URL = "https://depmap.org/portal/download/api/downloads"
    FIGSHARE_ARTICLE_API = "https://api.figshare.com/v2/articles/27993248"
    FIGSHARE_ARTICLE_URL = "https://plus.figshare.com/articles/dataset/DepMap_24Q4_Public/27993248"
    FIGSHARE_MODEL_FILE = "Model.csv"

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 60.0) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def search(
        self,
        *,
        task_id: str,
        query: str = "breast cancer cell line AUC IC50",
        gene: str | None = None,
        drug: str | None = None,
        max_records: int = 50,
    ) -> DepMapAdapterResult:
        del gene
        limit = min(max(int(max_records), 1), 200)
        response = self.client.get(self.DOWNLOADS_URL)
        if response.status_code >= 400:
            raise DepMapAdapterError(
                DepMapErrorCode.NETWORK_ERROR,
                f"DepMap 官方下载目录返回 HTTP {response.status_code}。",
                details={"url": self.DOWNLOADS_URL, "status": response.status_code},
            )
        payload = self._parse_payload(response)
        request_url = self.DOWNLOADS_URL
        release_source: SourceItem | None = None
        try:
            records = self._records_from_payload(task_id, payload, query=query, drug=drug, limit=limit)
        except DepMapAdapterError as exc:
            if exc.code is not DepMapErrorCode.INVALID_RESPONSE:
                raise
            model_csv, release_source = self._load_figshare_model_csv(task_id)
            records = self._from_model_csv(task_id, model_csv, drug=drug, limit=limit)
            request_url = self.FIGSHARE_ARTICLE_API
        if not records:
            raise DepMapAdapterError(
                DepMapErrorCode.NO_RECORDS,
                "DepMap 官方返回中没有乳腺癌细胞系记录。",
                details={"url": self.DOWNLOADS_URL},
            )
        source_items = [
            SourceItem(
                source_id="depmap:portal",
                task_id=task_id,
                source_name="DepMap",
                source_type="preclinical_cell_line",
                accession="DepMap",
                url=self.PORTAL_URL,
                status="retrieved",
            )
        ]
        if release_source is not None:
            source_items.append(release_source)
        for record in records[:8]:
            source_items.append(
                SourceItem(
                    source_id=record.source_id,
                    task_id=task_id,
                    source_name="DepMap",
                    source_type="preclinical_cell_line",
                    accession=record.model_id,
                    url=record.url,
                    status="retrieved",
                )
            )
        return DepMapAdapterResult(
            task_id=task_id,
            query=query,
            records=records,
            source_items=source_items,
            request_url=request_url,
            queried_at=datetime.now(timezone.utc),
            notice=(
                "DepMap 细胞系药敏的 response_domain 固定为 preclinical_cell_line；"
                "AUC/IC50 不得解释为患者 pCR 或临床疗效。"
                + (
                    "门户目录触发浏览器验证时，细胞系目录来自 Broad DepMap 在 Figshare 发布的 24Q4 Model.csv；"
                    "该回退只补充模型元数据，不补造缺失的药敏数值。"
                    if release_source is not None
                    else ""
                )
            ),
        )

    def _load_figshare_model_csv(self, task_id: str) -> tuple[str, SourceItem]:
        metadata_response = self.client.get(self.FIGSHARE_ARTICLE_API)
        if metadata_response.status_code >= 400:
            raise DepMapAdapterError(
                DepMapErrorCode.NETWORK_ERROR,
                f"DepMap Figshare 发布元数据返回 HTTP {metadata_response.status_code}。",
                details={"url": self.FIGSHARE_ARTICLE_API},
            )
        try:
            metadata = metadata_response.json()
        except ValueError as exc:
            raise DepMapAdapterError(
                DepMapErrorCode.INVALID_RESPONSE,
                "DepMap Figshare 发布元数据不是有效 JSON。",
                details={"url": self.FIGSHARE_ARTICLE_API},
            ) from exc
        files = metadata.get("files") if isinstance(metadata, dict) else None
        if not isinstance(files, list):
            raise DepMapAdapterError(
                DepMapErrorCode.INVALID_RESPONSE,
                "DepMap Figshare 发布未返回文件清单。",
                details={"url": self.FIGSHARE_ARTICLE_API},
            )
        model_file = next(
            (
                item
                for item in files
                if isinstance(item, dict)
                and str(item.get("name") or "").casefold() == self.FIGSHARE_MODEL_FILE.casefold()
            ),
            None,
        )
        if model_file is None:
            raise DepMapAdapterError(
                DepMapErrorCode.NO_RECORDS,
                f"DepMap Figshare 发布中没有 {self.FIGSHARE_MODEL_FILE}。",
                details={"url": self.FIGSHARE_ARTICLE_API},
            )
        download_url = str(model_file.get("download_url") or "")
        hostname = (urlparse(download_url).hostname or "").casefold()
        if not download_url.startswith("https://") or hostname != "ndownloader.figshare.com":
            raise DepMapAdapterError(
                DepMapErrorCode.INVALID_RESPONSE,
                "DepMap Figshare 文件下载地址不在允许的官方域名。",
                details={"url": download_url},
            )
        file_response = self.client.get(download_url)
        if file_response.status_code >= 400:
            raise DepMapAdapterError(
                DepMapErrorCode.NETWORK_ERROR,
                f"DepMap Figshare Model.csv 返回 HTTP {file_response.status_code}。",
                details={"url": download_url},
            )
        checksum = str(model_file.get("computed_md5") or "").strip()
        return file_response.text, SourceItem(
            source_id="depmap:figshare:27993248:model",
            task_id=task_id,
            source_name="Broad DepMap 24Q4 Model.csv",
            source_type="preclinical_cell_line",
            accession="DepMap",
            url=self.FIGSHARE_ARTICLE_URL,
            file_type="csv",
            checksum=f"md5:{checksum}" if checksum else None,
            status="retrieved",
        )

    def _parse_payload(self, response: httpx.Response) -> dict[str, Any] | str:
        content_type = (response.headers.get("content-type") or "").casefold()
        text = response.text
        if "json" in content_type or text.lstrip().startswith("{") or text.lstrip().startswith("["):
            try:
                return response.json()
            except ValueError as exc:
                raise DepMapAdapterError(
                    DepMapErrorCode.INVALID_RESPONSE,
                    "DepMap 目录 JSON 无法解析。",
                    details={"url": str(response.url)},
                ) from exc
        return text

    def _records_from_payload(
        self,
        task_id: str,
        payload: dict[str, Any] | str,
        *,
        query: str,
        drug: str | None,
        limit: int,
    ) -> list[DepMapCellLineRecord]:
        if isinstance(payload, dict) and (payload.get("models") or payload.get("sensitivity")):
            return self._from_json_bundle(task_id, payload, drug=drug, limit=limit)
        if isinstance(payload, str) and "ModelID" in payload:
            return self._from_model_csv(task_id, payload, drug=drug, limit=limit)
        if isinstance(payload, dict):
            csv_text = self._csv_from_index(payload)
            if csv_text:
                return self._from_model_csv(task_id, csv_text, drug=drug, limit=limit)
        raise DepMapAdapterError(
            DepMapErrorCode.INVALID_RESPONSE,
            "DepMap 响应不是可解析的细胞系目录。",
            details={"query": query},
        )

    def _csv_from_index(self, payload: dict[str, Any]) -> str | None:
        files = payload.get("files") or payload.get("releaseData") or payload.get("downloads") or []
        if isinstance(files, dict):
            files = list(files.values())
        if not isinstance(files, list):
            return None
        for item in files:
            if not isinstance(item, dict):
                continue
            name = str(item.get("fileName") or item.get("name") or item.get("filename") or "")
            url = str(item.get("downloadUrl") or item.get("url") or item.get("fileUrl") or "")
            if "model.csv" in name.casefold() and url.startswith("https://"):
                response = self.client.get(url)
                if response.status_code < 400:
                    return response.text
        return None

    def _from_json_bundle(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        drug: str | None,
        limit: int,
    ) -> list[DepMapCellLineRecord]:
        models = payload.get("models") or []
        sensitivity = {
            str(row.get("ModelID") or row.get("model_id") or ""): row
            for row in (payload.get("sensitivity") or [])
            if isinstance(row, dict)
        }
        records: list[DepMapCellLineRecord] = []
        for raw in models:
            if not isinstance(raw, dict):
                continue
            lineage = str(raw.get("OncotreeLineage") or raw.get("lineage") or "")
            if "breast" not in lineage.casefold() and "乳腺" not in lineage:
                continue
            model_id = str(raw.get("ModelID") or raw.get("model_id") or "").strip()
            name = str(raw.get("CellLineName") or raw.get("cell_line_name") or model_id).strip()
            if not model_id or not name:
                continue
            hit = sensitivity.get(model_id) or {}
            records.append(
                self._record(
                    task_id,
                    model_id=model_id,
                    name=name,
                    lineage=lineage or "Breast",
                    drug=str(hit.get("Drug") or hit.get("drug") or drug or ""),
                    auc=self._float(hit.get("AUC") or hit.get("auc")),
                    ic50=self._float(hit.get("IC50") or hit.get("ic50")),
                    raw=raw,
                )
            )
            if len(records) >= limit:
                break
        return records

    def _from_model_csv(
        self,
        task_id: str,
        text: str,
        *,
        drug: str | None,
        limit: int,
    ) -> list[DepMapCellLineRecord]:
        reader = csv.DictReader(io.StringIO(text))
        records: list[DepMapCellLineRecord] = []
        for raw in reader:
            lineage = str(raw.get("OncotreeLineage") or raw.get("lineage") or "")
            if "breast" not in lineage.casefold():
                continue
            model_id = str(raw.get("ModelID") or "").strip()
            name = str(raw.get("CellLineName") or raw.get("StrippedCellLineName") or model_id).strip()
            if not model_id or not name:
                continue
            records.append(
                self._record(
                    task_id,
                    model_id=model_id,
                    name=name,
                    lineage=lineage,
                    drug=drug or "",
                    auc=None,
                    ic50=None,
                    raw=dict(raw),
                )
            )
            if len(records) >= limit:
                break
        return records

    def _record(
        self,
        task_id: str,
        *,
        model_id: str,
        name: str,
        lineage: str,
        drug: str,
        auc: float | None,
        ic50: float | None,
        raw: dict[str, Any],
    ) -> DepMapCellLineRecord:
        return DepMapCellLineRecord(
            model_id=model_id,
            cell_line_name=name,
            lineage=lineage,
            drug=drug or None,
            auc=auc,
            ic50=ic50,
            response_domain="preclinical_cell_line",
            source_id=f"depmap:{model_id}",
            url=self.PORTAL_URL,
            raw_record=raw,
        )

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
