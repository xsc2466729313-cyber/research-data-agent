from __future__ import annotations

import re
from datetime import datetime, timezone
from xml.etree import ElementTree

from backend.app.literature.models import (
    LiteratureProviderTrace,
    LiteratureSearchRequest,
    LiteratureSearchResult,
    PaperRecord,
)
from backend.app.sources.discovery import DiscoveryAdapter, DiscoveryAdapterError


_DATASET_ACCESSION = re.compile(r"\b(?:GSE\d+|NCT\d{8}|TCGA-[A-Z0-9-]+)\b", re.IGNORECASE)
_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"


class EuropePMCProvider:
    """LiteratureProvider facade over the existing official Europe PMC adapter."""

    name = "europe_pmc"

    def __init__(
        self,
        adapter: DiscoveryAdapter | None = None,
        *,
        fetch_fulltext: bool = True,
        max_fulltext_records: int = 3,
    ) -> None:
        self.adapter = adapter or DiscoveryAdapter()
        self.fetch_fulltext = fetch_fulltext
        self.max_fulltext_records = max(0, max_fulltext_records)

    @property
    def configured(self) -> bool:
        return True

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
        started = datetime.now(timezone.utc)
        try:
            result = self.adapter.search_europe_pmc(
                task_id="literature-scan",
                query=request.query,
                max_records=request.max_records,
            )
        except DiscoveryAdapterError:
            raise

        papers: list[PaperRecord] = []
        for record_index, record in enumerate(result.records):
            title = str(getattr(record, "title", "") or "").strip()
            if not title:
                continue
            abstract = str(getattr(record, "abstract", "") or "").strip() or None
            raw = dict(getattr(record, "raw_record", {}) or {})
            authors = self._authors(raw)
            sections = {"title": title}
            if abstract:
                sections["abstract"] = abstract
            acquisition_traces: list[LiteratureProviderTrace] = []
            pmcid = str(raw.get("pmcid") or "").strip()
            if not pmcid and str(record.record_id).upper().startswith("PMC"):
                pmcid = str(record.record_id).strip()
            fulltext_available = bool(raw.get("inEPMC") or raw.get("isOpenAccess") == "Y")
            if self.fetch_fulltext and fulltext_available and pmcid and record_index < self.max_fulltext_records:
                fulltext_sections, fulltext_trace = self._fulltext_sections(pmcid)
                acquisition_traces.append(fulltext_trace)
                sections.update(fulltext_sections)
                raw["fulltext_fetch_status"] = fulltext_trace.status
            section_text = " ".join(sections.values())
            accessions = list(
                dict.fromkeys(match.group(0).upper() for match in _DATASET_ACCESSION.finditer(section_text))
            )
            papers.append(
                PaperRecord(
                    paper_id=f"europepmc:{record.record_id}",
                    source_id=f"europepmc:{record.record_id}",
                    provider=self.name,
                    title=title,
                    abstract=abstract,
                    pmid=record.pmid,
                    doi=record.doi,
                    journal=record.journal,
                    publication_year=record.publication_year,
                    authors=authors,
                    fulltext_available=fulltext_available,
                    source_url=record.url,
                    sections=sections,
                    dataset_accessions=accessions,
                    acquisition_traces=acquisition_traces,
                    raw_metadata=raw,
                )
            )
        completed = datetime.now(timezone.utc)
        return LiteratureSearchResult(
            provider=self.name,
            query=request.query,
            papers=papers,
            trace=LiteratureProviderTrace(
                provider=self.name,
                query=request.query,
                requested_at=started,
                completed_at=completed,
                status="success",
                source_url=result.request_url,
                result_count=len(papers),
            ),
        )

    def _fulltext_sections(
        self,
        pmcid: str,
    ) -> tuple[dict[str, str], LiteratureProviderTrace]:
        started = datetime.now(timezone.utc)
        url = _FULLTEXT_URL.format(pmcid=pmcid)
        try:
            response = self.adapter.client.get(url)
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            root = ElementTree.fromstring(response.content)
            sections = self._parse_sections(root)
            status = "success"
            error_type = None
        except Exception as exc:
            sections = {}
            status = "failed"
            error_type = type(exc).__name__
        completed = datetime.now(timezone.utc)
        return sections, LiteratureProviderTrace(
            provider=self.name,
            query=f"fulltext:{pmcid}",
            requested_at=started,
            completed_at=completed,
            status=status,
            source_url=url,
            result_count=len(sections),
            error_type=error_type,
        )

    @staticmethod
    def _parse_sections(root: ElementTree.Element) -> dict[str, str]:
        output: dict[str, str] = {}
        for section in root.findall(".//body//sec"):
            title_node = section.find("./title")
            title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
            category = EuropePMCProvider._section_category(title)
            if category is None:
                continue
            paragraphs = [
                " ".join("".join(paragraph.itertext()).split())
                for paragraph in section.findall("./p")
            ]
            text = " ".join(value for value in paragraphs if value).strip()
            if not text:
                continue
            previous = output.get(category)
            output[category] = f"{previous} {text}".strip() if previous else text
        return output

    @staticmethod
    def _section_category(title: str) -> str | None:
        folded = title.casefold()
        categories = (
            ("methods", ("method", "materials", "patients and methods")),
            ("data_availability", ("data availability", "data sharing", "availability of data")),
            ("supplementary", ("supplement", "supporting information")),
            ("cohort", ("cohort", "study population", "patients")),
            ("outcome_definition", ("outcome", "endpoint", "response assessment")),
            ("statistical_analysis", ("statistical", "data analysis")),
            ("results", ("result",)),
            ("limitations", ("limitation",)),
        )
        for category, tokens in categories:
            if any(token in folded for token in tokens):
                return category
        return None

    @staticmethod
    def _authors(raw: dict[str, object]) -> list[str]:
        values = raw.get("authorList")
        if isinstance(values, dict):
            values = values.get("author")
        if not isinstance(values, list):
            return []
        authors: list[str] = []
        for value in values:
            if isinstance(value, dict):
                name = str(value.get("fullName") or value.get("lastName") or "").strip()
            else:
                name = str(value or "").strip()
            if name:
                authors.append(name)
        return authors
