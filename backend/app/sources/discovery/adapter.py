from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from backend.app.models import SearchPlan, SourceItem
from backend.app.parsers import ParseRequest, ParserRegistry
from backend.app.sources.discovery.models import (
    BioSampleRecord,
    DiscoveryAdapterResult,
    EuropePMCRecord,
    GeoCatalogRecord,
    ZenodoDatasetRecord,
)


class DiscoveryAdapterError(RuntimeError):
    pass


class DiscoveryAdapter:
    """Fetches official discovery-layer metadata without creating patient rows."""

    BIOSAMPLE_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    BIOSAMPLE_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    BIOSAMPLE_URL = "https://www.ncbi.nlm.nih.gov/biosample/{uid}"
    GEO_PORTAL_URL = "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
    EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    EUROPE_PMC_RECORD_URL = "https://europepmc.org/article/{kind}/{value}"
    EUROPE_PMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    ZENODO_URL = "https://zenodo.org/api/records/"

    def __init__(self, *, client: httpx.Client | None = None, timeout_seconds: float = 30.0) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def search_biosample(
        self,
        *,
        task_id: str,
        query: str,
        max_records: int = 20,
        search_plan: SearchPlan | None = None,
    ) -> DiscoveryAdapterResult:
        del search_plan
        limit = min(max(int(max_records), 1), 100)
        params = {"db": "biosample", "term": query, "retmode": "json", "retmax": limit}
        response = self.client.get(self.BIOSAMPLE_ESEARCH_URL, params=params)
        payload = self._json(response, "NCBI BioSample 检索")
        ids = [str(value) for value in (payload.get("esearchresult", {}).get("idlist") or [])]
        total = int(payload.get("esearchresult", {}).get("count") or 0)
        records: list[BioSampleRecord] = []
        if ids:
            summary_response = self.client.get(
                self.BIOSAMPLE_ESUMMARY_URL,
                params={"db": "biosample", "id": ",".join(ids), "retmode": "json"},
            )
            summary = self._json(summary_response, "NCBI BioSample 摘要")
            for uid in ids:
                raw = dict((summary.get("result") or {}).get(uid) or {})
                if not raw or uid == "uids":
                    continue
                accession = self._text(raw.get("accession"))
                url = self.BIOSAMPLE_URL.format(uid=accession or uid)
                item = self._source_item(
                    task_id=task_id,
                    source_id=f"ncbi-biosample:{accession or uid}",
                    source_name="NCBI BioSample",
                    accession=accession or uid,
                    url=url,
                    raw=raw,
                )
                records.append(
                    BioSampleRecord(
                        uid=uid,
                        accession=accession,
                        title=self._text(raw.get("title")),
                        organism=self._text(raw.get("organism")),
                        attributes=dict(raw.get("attributes") or {}),
                        url=url,
                        raw_record=raw,
                        source_item=item,
                    )
                )
        return DiscoveryAdapterResult(
            task_id=task_id,
            query=query,
            source_kind="biosample",
            total_count=total,
            records=records,
            source_items=[record.source_item for record in records],
            request_url=str(response.url),
            queried_at=datetime.now(timezone.utc),
            notice="BioSample 结果用于样本元数据发现和来源核验，不代表已与患者主表完成身份对齐。",
        )

    def search_geo_catalog(
        self,
        *,
        task_id: str,
        query: str,
        max_records: int = 20,
        search_plan: SearchPlan | None = None,
    ) -> DiscoveryAdapterResult:
        del search_plan
        limit = min(max(int(max_records), 1), 100)
        params = {"db": "gds", "term": query, "retmode": "json", "retmax": limit}
        response = self.client.get(self.BIOSAMPLE_ESEARCH_URL, params=params)
        payload = self._json(response, "NCBI GEO 目录检索")
        ids = [str(value) for value in (payload.get("esearchresult", {}).get("idlist") or [])]
        total = int(payload.get("esearchresult", {}).get("count") or 0)
        records: list[GeoCatalogRecord] = []
        if ids:
            summary_response = self.client.get(
                self.BIOSAMPLE_ESUMMARY_URL,
                params={"db": "gds", "id": ",".join(ids), "retmode": "json"},
            )
            summary = self._json(summary_response, "NCBI GEO 目录摘要")
            for uid in ids:
                raw = dict((summary.get("result") or {}).get(uid) or {})
                if not raw or uid == "uids":
                    continue
                accession = (self._text(raw.get("accession")) or "").upper()
                if not accession.startswith("GSE"):
                    continue
                url = self.GEO_PORTAL_URL.format(accession=accession)
                item = self._source_item(
                    task_id=task_id,
                    source_id=f"ncbi-geo-catalog:{accession}",
                    source_name="NCBI GEO",
                    accession=accession,
                    url=url,
                    raw=raw,
                )
                n_samples = raw.get("n_samples")
                try:
                    n_samples = int(n_samples) if n_samples not in {None, ""} else None
                except (TypeError, ValueError):
                    n_samples = None
                records.append(
                    GeoCatalogRecord(
                        uid=uid,
                        accession=accession,
                        title=self._text(raw.get("title")),
                        summary=self._text(raw.get("summary")),
                        n_samples=n_samples,
                        dataset_type=self._text(raw.get("gdsType")),
                        url=url,
                        raw_record=raw,
                        source_item=item,
                    )
                )
        return DiscoveryAdapterResult(
            task_id=task_id,
            query=query,
            source_kind="geo_catalog",
            total_count=total,
            records=records,
            source_items=[record.source_item for record in records],
            request_url=str(response.url),
            queried_at=datetime.now(timezone.utc),
            notice="GEO 目录检索只发现候选 Series；必须再下载并解析 Series Matrix 后才能形成患者主表。",
        )

    def search_europe_pmc(
        self,
        *,
        task_id: str,
        query: str,
        max_records: int = 20,
        search_plan: SearchPlan | None = None,
    ) -> DiscoveryAdapterResult:
        del search_plan
        limit = min(max(int(max_records), 1), 100)
        params = {"query": query, "format": "json", "pageSize": limit, "resultType": "core"}
        response = self.client.get(self.EUROPE_PMC_URL, params=params)
        payload = self._json(response, "Europe PMC 检索")
        records: list[EuropePMCRecord] = []
        for raw_value in (payload.get("resultList", {}).get("result") or [])[:limit]:
            raw = dict(raw_value or {})
            record_id = self._text(raw.get("id")) or self._text(raw.get("pmid"))
            if not record_id:
                continue
            pmid = self._text(raw.get("pmid"))
            doi = self._text(raw.get("doi"))
            kind = "MED" if pmid else str(raw.get("source") or "MED").upper()
            value = pmid or record_id
            url = self.EUROPE_PMC_RECORD_URL.format(kind=kind, value=quote(value, safe=""))
            item = self._source_item(
                task_id=task_id,
                source_id=f"europepmc:{record_id}",
                source_name="Europe PMC",
                accession=f"PMID:{pmid}" if pmid else record_id,
                url=url,
                raw=raw,
            )
            year = raw.get("pubYear")
            try:
                year = int(year) if year else None
            except (TypeError, ValueError):
                year = None
            records.append(
                EuropePMCRecord(
                    record_id=record_id,
                    pmid=pmid,
                    doi=doi,
                    title=self._text(raw.get("title")),
                    journal=self._text(raw.get("journalTitle")),
                    publication_year=year,
                    abstract=self._text(raw.get("abstractText")),
                    url=url,
                    raw_record=raw,
                    source_item=item,
                )
            )
        total = int(payload.get("hitCount") or len(records))
        return DiscoveryAdapterResult(
            task_id=task_id,
            query=query,
            source_kind="europe_pmc",
            total_count=total,
            records=records,
            source_items=[record.source_item for record in records],
            request_url=str(response.url),
            queried_at=datetime.now(timezone.utc),
            notice="Europe PMC 结果用于文献证据发现和研究语境核验，不作为患者级疗效事实。",
        )

    def search_zenodo(
        self,
        *,
        task_id: str,
        query: str,
        max_records: int = 20,
        search_plan: SearchPlan | None = None,
    ) -> DiscoveryAdapterResult:
        """Search Zenodo's official dataset catalog and parse resource metadata.

        This deliberately stops at the catalog layer.  A Zenodo record is a
        candidate dataset until a researcher selects its files for a follow-up
        download and schema inspection.
        """
        del search_plan
        limit = min(max(int(max_records), 1), 100)
        params = {"q": query, "type": "dataset", "size": limit, "sort": "bestmatch"}
        response = self.client.get(self.ZENODO_URL, params=params)
        payload = self._json(response, "Zenodo 数据集检索")
        hits = ((payload.get("hits") or {}).get("hits") or [])
        records: list[ZenodoDatasetRecord] = []
        for raw_value in hits[:limit]:
            raw = dict(raw_value or {})
            metadata = dict(raw.get("metadata") or {})
            record_id = self._text(raw.get("id")) or self._text(metadata.get("record_id"))
            if not record_id:
                continue
            files: list[dict[str, Any]] = []
            for file_value in raw.get("files") or []:
                file_raw = dict(file_value or {})
                links = dict(file_raw.get("links") or {})
                file_item = {
                    key: value
                    for key, value in {
                        "key": self._text(file_raw.get("key")),
                        "size": file_raw.get("size"),
                        "checksum": self._text(file_raw.get("checksum")),
                        "download_url": self._text(links.get("self") or file_raw.get("self")),
                    }.items()
                    if value not in (None, "")
                }
                if file_item.get("key"):
                    files.append(file_item)
            file_formats = sorted(
                {
                    suffix.lower()
                    for item in files
                    for suffix in [str(item.get("key") or "").rsplit(".", 1)[-1]]
                    if "." in str(item.get("key") or "") and suffix
                }
            )
            record_links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
            url = str(record_links.get("self_html") or f"https://zenodo.org/records/{record_id}")
            item = self._source_item(
                task_id=task_id,
                source_id=f"zenodo:{record_id}",
                source_name="Zenodo",
                accession=self._text(metadata.get("doi")) or record_id,
                url=url,
                raw=raw,
            )
            keywords = [str(value).strip() for value in (metadata.get("keywords") or []) if str(value).strip()]
            records.append(
                ZenodoDatasetRecord(
                    record_id=record_id,
                    title=self._text(metadata.get("title") or raw.get("title")),
                    description=self._text(metadata.get("description")),
                    doi=self._text(metadata.get("doi")),
                    publication_date=self._text(metadata.get("publication_date")),
                    keywords=list(dict.fromkeys(keywords)),
                    file_count=len(files),
                    file_formats=file_formats,
                    files=files,
                    url=url,
                    raw_record=raw,
                    source_item=item,
                )
            )
        total_value = ((payload.get("hits") or {}).get("total"))
        if isinstance(total_value, dict):
            total_value = total_value.get("value")
        try:
            total = int(total_value or len(records))
        except (TypeError, ValueError):
            total = len(records)
        return DiscoveryAdapterResult(
            task_id=task_id,
            query=query,
            source_kind="zenodo",
            total_count=max(total, len(records)),
            records=records,
            source_items=[record.source_item for record in records],
            request_url=str(response.url),
            queried_at=datetime.now(timezone.utc),
            notice="Zenodo 公开数据集目录已解析元数据和资源文件清单；下载文件仍需按官方链接继续核验。",
        )

    def extract_paper_assets(
        self,
        *,
        task_id: str,
        query: str,
        pmcid: str | None = None,
        max_records: int = 5,
        search_plan: SearchPlan | None = None,
    ) -> DiscoveryAdapterResult:
        del search_plan
        chosen = (pmcid or "").strip().upper()
        search_result: DiscoveryAdapterResult | None = None
        if not chosen:
            search_result = self.search_europe_pmc(
                task_id=task_id,
                query=f"{query} OPEN_ACCESS:Y",
                max_records=max(1, min(int(max_records), 10)),
            )
            for record in search_result.records:
                raw = getattr(record, "raw_record", {}) or {}
                candidate = str(raw.get("pmcid") or raw.get("id") or "").upper()
                if candidate.startswith("PMC"):
                    chosen = candidate
                    break
        if not chosen.startswith("PMC"):
            raise DiscoveryAdapterError("未找到带 PMCID 的开放全文，无法提取表格或图注。")
        url = self.EUROPE_PMC_FULLTEXT_URL.format(pmcid=chosen)
        response = self.client.get(url)
        if response.status_code >= 400:
            raise DiscoveryAdapterError(f"Europe PMC 全文 XML 失败：HTTP {response.status_code}")
        parsed = ParserRegistry().parse(
            ParseRequest(
                source_id=f"europepmc:{chosen}",
                filename=f"{chosen}.xml",
                text=response.text,
            )
        )
        item = self._source_item(
            task_id=task_id,
            source_id=f"europepmc-fulltext:{chosen}",
            source_name="Europe PMC",
            accession=chosen,
            url=self.EUROPE_PMC_RECORD_URL.format(kind="PMC", value=chosen.replace("PMC", "")),
            raw={"pmcid": chosen, "parse_status": parsed.status, "record_count": len(parsed.records)},
        )
        records = list(search_result.records[:1]) if search_result else []
        return DiscoveryAdapterResult(
            task_id=task_id,
            query=query,
            source_kind="paper_extract",
            total_count=len(parsed.records),
            records=records,
            source_items=[item],
            request_url=url,
            queried_at=datetime.now(timezone.utc),
            pmcid=chosen,
            parse_warnings=list(parsed.warnings),
            parsed_field_count=len(parsed.records),
            notice=(
                f"已从 {chosen} 提取表格单元格与图注；图注不得当作图像素读数。"
                + (" " + " ".join(parsed.warnings[:2]) if parsed.warnings else "")
            ),
        )

    @staticmethod
    def _json(response: httpx.Response, label: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise DiscoveryAdapterError(f"{label}失败：HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DiscoveryAdapterError(f"{label}返回格式不可解析") from exc
        if not isinstance(payload, dict):
            raise DiscoveryAdapterError(f"{label}返回不是 JSON 对象")
        return payload

    @staticmethod
    def _text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _source_item(
        *,
        task_id: str,
        source_id: str,
        source_name: str,
        accession: str,
        url: str,
        raw: dict[str, Any],
    ) -> SourceItem:
        checksum = hashlib.sha256(
            json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return SourceItem(
            source_id=source_id,
            task_id=task_id,
            source_name=source_name,
            source_type="discovery",
            accession=accession,
            url=url,
            file_type="json",
            checksum=checksum,
            status="retrieved",
        )
