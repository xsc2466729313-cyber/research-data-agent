from __future__ import annotations

import re
from typing import Any

from backend.app.models import ResearchSpec


GSE_PATTERN = re.compile(r"\b(GSE[1-9]\d{2,6})\b", re.IGNORECASE)
NCT_PATTERN = re.compile(r"\b(NCT\d{8})\b", re.IGNORECASE)


def extract_gse_accessions(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in GSE_PATTERN.finditer(text or ""):
        accession = match.group(1).upper()
        if accession not in seen:
            seen.add(accession)
            ordered.append(accession)
    return ordered


def extract_nct_ids(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in NCT_PATTERN.finditer(text or ""):
        nct_id = match.group(1).upper()
        if nct_id not in seen:
            seen.add(nct_id)
            ordered.append(nct_id)
    return ordered


def catalog_query(spec: ResearchSpec) -> str:
    parts = [spec.disease or "breast cancer", spec.subtype or ""]
    parts.extend(spec.genes)
    parts.extend(spec.drugs)
    if "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types:
        parts.append("response OR pCR OR trastuzumab")
    if any(item.endswith("mutation") or item == "mutation" for item in spec.required_data_types) or spec.genes:
        parts.append("mutation OR sequencing")
    return " ".join(part for part in parts if part).strip()


def literature_query(spec: ResearchSpec) -> str:
    parts = [spec.disease or "breast cancer", "GSE"]
    parts.extend(spec.genes)
    parts.extend(spec.drugs)
    if "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types:
        parts.append("pathological complete response OR treatment response")
    return " ".join(part for part in parts if part).strip()


def score_geo_text(text: str, spec: ResearchSpec) -> int:
    blob = (text or "").casefold()
    score = 0
    for gene in spec.genes:
        if gene.casefold() in blob:
            score += 3
    for drug in spec.drugs:
        if drug.casefold() in blob:
            score += 2
    for token in ("her2", "erbb2", "pcr", "response", "trastuzumab", "neoadjuvant", "pik3ca"):
        if token in blob:
            score += 1
    if "breast" in blob:
        score += 1
    return score


def harvest_from_raw_results(raw_results: list[tuple[str, Any]], spec: ResearchSpec) -> list[str]:
    """Collect GSE accessions mentioned by catalog or literature tools."""
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for name, result in raw_results:
        records = list(getattr(result, "records", None) or [])
        if name == "search_geo_catalog":
            for record in records:
                accession = str(getattr(record, "accession", "") or "").upper()
                if not accession.startswith("GSE") or accession in seen:
                    continue
                text = f"{getattr(record, 'title', '')} {getattr(record, 'summary', '')}"
                seen.add(accession)
                ranked.append((score_geo_text(text, spec), accession))
            continue
        texts = [str(getattr(result, "query", "") or "")]
        if name == "search_europe_pmc":
            for record in records:
                texts.append(str(getattr(record, "title", "") or ""))
                texts.append(str(getattr(record, "abstract", "") or ""))
        blob = "\n".join(texts)
        for accession in extract_gse_accessions(blob):
            if accession in seen:
                continue
            seen.add(accession)
            ranked.append((score_geo_text(blob, spec), accession))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [accession for _score, accession in ranked]
