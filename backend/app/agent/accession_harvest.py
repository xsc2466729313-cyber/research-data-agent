from __future__ import annotations

import re
from typing import Any

from backend.app.models import ResearchSpec


GSE_PATTERN = re.compile(r"\b(GSE[1-9]\d{2,6})\b", re.IGNORECASE)
NCT_PATTERN = re.compile(r"\b(NCT\d{8})\b", re.IGNORECASE)
_OUTCOME_MARKERS = (
    "treatment_response",
    "pathological complete response",
    "pathologic complete response",
    "pcr",
    "response",
    "survival",
    "响应",
    "疗效",
    "缓解",
    "生存",
)

# Explicit treatment-as-exposure. Do not match 治疗响应 / 新辅助化疗 as a required treatment column.
_TREATMENT_EXPOSURE_MARKERS = (
    "治疗方案",
    "治疗手段",
    "用药方案",
    "化疗方案",
    "靶向治疗",
    "内分泌治疗",
    "曲妥珠",
    "trastuzumab",
    "herceptin",
    "alpelisib",
    "pertuzumab",
    "regimen",
    "treatment arm",
    "therapy arm",
)

_PCR_MARKERS = (
    "pcr",
    "pathological complete response",
    "pathologic complete response",
    "病理完全缓解",
)

_SURVIVAL_MARKERS = (
    "survival",
    " os",
    "os_",
    "os/",
    "/os",
    "rfs",
    "dfs",
    "pfs",
    "生存",
    "总生存",
    "无病生存",
    "无复发生存",
    "无进展生存",
)
_SURVIVAL_ABBREV_RE = re.compile(r"(?<![A-Za-z])(OS|RFS|DFS|PFS|DMFS)(?![A-Za-z])")
_TIMEPOINT_MARKERS = ("样本时间点", "timepoint", "治疗前后", "配对样本", "基线与治疗后", "纵向")
_CNA_MARKERS = ("拷贝数", "cna", "amplification", "扩增", "copy number")
_TNBC_MARKERS = ("triple-negative", "triple negative", "tnbc", "三阴性")


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


def _intent_blob(spec: ResearchSpec) -> str:
    return " ".join(
        [
            " ".join(spec.outcomes or []),
            " ".join(spec.required_data_types or []),
            spec.research_goal or "",
        ]
    ).casefold()


def question_asks_survival(question: str) -> bool:
    blob = question or ""
    lowered = blob.casefold()
    if any(
        token in lowered
        for token in (
            "生存",
            "总生存",
            "无病生存",
            "无复发生存",
            "无进展生存",
            "overall survival",
            "relapse-free",
            "relapse free",
            "disease-free",
            "disease free",
            "progression-free",
            "progression free",
        )
    ):
        return True
    return bool(_SURVIVAL_ABBREV_RE.search(blob))


def question_asks_clinical_outcome(question: str) -> bool:
    if question_asks_survival(question):
        return True
    blob = (question or "").casefold()
    return any(token in blob for token in _OUTCOME_MARKERS)


def needs_clinical_outcome(spec: ResearchSpec) -> bool:
    if question_asks_clinical_outcome(spec.research_goal or ""):
        return True
    blob = _intent_blob(spec)
    return any(token in blob for token in _OUTCOME_MARKERS)


def asks_treatment(spec: ResearchSpec) -> bool:
    if spec.drugs:
        return True
    blob = _intent_blob(spec)
    return any(token in blob for token in _TREATMENT_EXPOSURE_MARKERS)


def asks_sample_timepoint(spec: ResearchSpec) -> bool:
    blob = _intent_blob(spec)
    return any(token in blob for token in _TIMEPOINT_MARKERS)


def asks_copy_number(spec: ResearchSpec) -> bool:
    blob = _intent_blob(spec)
    return any(token in blob for token in _CNA_MARKERS)


def asks_pcr(spec: ResearchSpec) -> bool:
    blob = _intent_blob(spec)
    return any(token in blob for token in _PCR_MARKERS)


def asks_survival(spec: ResearchSpec) -> bool:
    if question_asks_survival(spec.research_goal or ""):
        return True
    blob = _intent_blob(spec)
    if asks_pcr(spec) and not any(token in blob for token in ("生存", "survival", "总生存", "无病生存", "os", "rfs", "dfs")):
        return False
    return any(token in blob for token in _SURVIVAL_MARKERS) or "survival" in (spec.outcomes or [])


def is_tnbc_question(spec: ResearchSpec) -> bool:
    blob = " ".join([spec.subtype or "", spec.research_goal or ""]).casefold()
    return any(token in blob for token in _TNBC_MARKERS)


def _keyword_terms(spec: ResearchSpec) -> list[str]:
    terms = [*spec.genes, *spec.drugs]
    if spec.subtype:
        terms.append(spec.subtype)
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_+/.-]{1,}", spec.research_goal or ""))
    return [term for term in terms if term]


def _outcome_search_clause(spec: ResearchSpec) -> str:
    if asks_pcr(spec):
        return "response OR pCR OR neoadjuvant"
    if asks_survival(spec):
        return "overall survival OR relapse-free survival OR RFS OR OS"
    if needs_clinical_outcome(spec) and "treatment_response" in (spec.outcomes or []):
        return "response OR pCR OR neoadjuvant"
    return ""


def catalog_query(spec: ResearchSpec, extra_terms: list[str] | None = None) -> str:
    parts = [spec.disease or "breast cancer"]
    extras = [str(term).strip() for term in (extra_terms or []) if str(term).strip()]
    if extras:
        parts.extend(extras)
    else:
        if spec.subtype:
            parts.append(spec.subtype)
        parts.extend(spec.genes)
        parts.extend(spec.drugs)
    outcome = _outcome_search_clause(spec)
    if outcome:
        parts.append(outcome)
    if any(item.endswith("mutation") or item == "mutation" for item in spec.required_data_types) or spec.genes:
        parts.append("mutation OR sequencing")
    return " ".join(part for part in parts if part).strip()


def literature_query(spec: ResearchSpec, extra_terms: list[str] | None = None) -> str:
    parts = [spec.disease or "breast cancer", "GSE"]
    extras = [str(term).strip() for term in (extra_terms or []) if str(term).strip()]
    if extras:
        parts.extend(extras)
    else:
        parts.extend(spec.genes)
        parts.extend(spec.drugs)
    if asks_pcr(spec) or (needs_clinical_outcome(spec) and not asks_survival(spec) and "treatment_response" in (spec.outcomes or [])):
        parts.append("pathological complete response OR treatment response")
    elif asks_survival(spec):
        parts.append("overall survival OR relapse-free survival")
    return " ".join(part for part in parts if part).strip()


def score_geo_text(text: str, spec: ResearchSpec, extra_terms: list[str] | None = None) -> int:
    blob = (text or "").casefold()
    score = 0
    if asks_pcr(spec) or (needs_clinical_outcome(spec) and not asks_survival(spec)):
        for token in ("pcr", "pathological complete response", "treatment response", "neoadjuvant", "response"):
            if token in blob:
                score += 4
    elif asks_survival(spec):
        for token in ("overall survival", "relapse-free", "disease-free", "intclust", "integrative cluster"):
            if token in blob:
                score += 4
    for gene in spec.genes:
        if gene.casefold() in blob:
            score += 3
    for drug in spec.drugs:
        if drug.casefold() in blob:
            score += 2
    subtype = (spec.subtype or "").casefold()
    goal = (spec.research_goal or "").casefold()
    if any(token in subtype or token in goal for token in ("triple", "tnbc", "三阴性")):
        if any(token in blob for token in ("tnbc", "triple-negative", "triple negative", "basal-like", "basal like")):
            score += 5
    if any(token in subtype or token in goal for token in ("her2-positive", "her2+", "her2 阳性")):
        if any(token in blob for token in ("her2", "erbb2", "trastuzumab")):
            score += 3
    for token in extra_terms or []:
        folded = str(token).strip().casefold()
        if folded and len(folded) > 1 and folded in blob:
            score += 2
    for token in ("her2", "erbb2", "trastuzumab", "pik3ca", "brca1", "brca2"):
        if token in blob:
            score += 1
    if "breast" in blob:
        score += 1
    return score


def seed_geo_accessions(spec: ResearchSpec) -> list[str]:
    """Public breast-cancer GEO series that match the question type.

    These are pre-acquisition hints from the source registry, not Gold Set labels.
    """
    blob = f"{spec.research_goal} {' '.join(spec.drugs)}"
    upper = blob.upper()
    if any(token in upper for token in ("ALPELISIB", "CAPIVASERTIB")) or any(
        token in (spec.research_goal or "") for token in ("阿培利司", "卡匹伐塞替")
    ):
        return []
    seeds: list[str] = []
    if asks_pcr(spec) or (
        needs_clinical_outcome(spec)
        and not asks_survival(spec)
        and "treatment_response" in (spec.outcomes or spec.required_data_types or [])
    ):
        seeds.extend(["GSE76360", "GSE25066"])
    goal = (spec.research_goal or "").casefold()
    if any(token in goal for token in ("scan-b", "scanb", "gse96058")):
        seeds.append("GSE96058")
    if "expression" in (spec.required_data_types or []) and not asks_pcr(spec):
        seeds.append("GSE96058")
    return list(dict.fromkeys(seeds))


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
                ranked.append((score_geo_text(text, spec, extra_terms=_keyword_terms(spec)), accession))
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
            ranked.append((score_geo_text(blob, spec, extra_terms=_keyword_terms(spec)), accession))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    harvested = [accession for _score, accession in ranked]
    return list(dict.fromkeys([*seed_geo_accessions(spec), *harvested]))
