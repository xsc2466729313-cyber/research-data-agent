from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from backend.app.models import SearchPlan, SourceItem
from backend.app.sources.discovery.models import (
    BioSampleRecord,
    DiscoveryAdapterResult,
    EuropePMCRecord,
)


class DiscoveryAdapterError(RuntimeError):
    pass


class DiscoveryAdapter:
    """Fetches official discovery-layer metadata without creating patient rows."""

    BIOSAMPLE_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    BIOSAMPLE_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    BIOSAMPLE_URL = "https://www.ncbi.nlm.nih.gov/biosample/{uid}"
    EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    EUROPE_PMC_RECORD_URL = "https://europepmc.org/article/{kind}/{value}"

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
