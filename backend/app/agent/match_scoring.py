from __future__ import annotations

from statistics import fmean
from typing import Any

from backend.app.agent.accession_harvest import asks_copy_number, asks_pcr, asks_survival, needs_clinical_outcome
from backend.app.models import ResearchSpec

PCR_FIELD_WEIGHTS: dict[str, float] = {
    "pcr": 1.0,
    "pathological_complete_response": 1.0,
    "pathologic_complete_response": 1.0,
    "pcr_binary": 0.96,
    "response_at_surgery": 0.88,
    "treatment_response": 0.82,
    "response": 0.76,
    "trastuzumab_response": 0.72,
}

RESPONSE_FIELD_WEIGHTS: dict[str, float] = {
    "treatment_response": 1.0,
    "response": 0.94,
    "response_at_surgery": 0.9,
    "pcr": 0.88,
    "pcr_binary": 0.84,
    "trastuzumab_response": 0.8,
}

SURVIVAL_FIELD_WEIGHTS: dict[str, float] = {
    "os_status": 1.0,
    "os_months": 0.9,
    "dfs_status": 0.94,
    "dfs_months": 0.88,
    "vital_status": 0.52,
}


def has_filled(value: Any) -> bool:
    if value is None or value == "":
        return False
    if value in ([], {}):
        return False
    text = str(value).strip()
    return text.upper() not in {"NA", "N/A", "<缺失>"}


def fill_rate(rows: list[dict[str, Any]] | None, fields: list[str] | tuple[str, ...]) -> float:
    records = list(rows or [])
    names = [name for name in fields if name]
    if not records or not names:
        return 0.0
    hits = sum(any(has_filled(row.get(name)) for name in names) for row in records)
    return hits / len(records)


def outcome_field_weights(spec: ResearchSpec) -> dict[str, float]:
    if asks_pcr(spec):
        return dict(PCR_FIELD_WEIGHTS)
    if asks_survival(spec) or "survival" in (spec.outcomes or []):
        return dict(SURVIVAL_FIELD_WEIGHTS)
    if needs_clinical_outcome(spec):
        return dict(RESPONSE_FIELD_WEIGHTS)
    return {}


def outcome_match_rate(dataset: Any, spec: ResearchSpec) -> float:
    if not needs_clinical_outcome(spec):
        return 1.0
    rows = list(getattr(dataset, "rows", []) or [])
    weights = outcome_field_weights(spec)
    if not rows or not weights:
        return 0.0
    best = 0.0
    for field, weight in weights.items():
        best = max(best, weight * fill_rate(rows, [field]))
    return round(min(1.0, best), 4)


def gene_match_score(rows: list[dict[str, Any]], gene: str, spec: ResearchSpec) -> float:
    symbol = gene.casefold()
    mutation = fill_rate(rows, [f"{symbol}_mutation"])
    variants = fill_rate(rows, [f"{symbol}_variants"])
    cna = fill_rate(rows, [f"{symbol}_cna"])
    altered = fill_rate(rows, [f"{symbol}_altered"])
    cna_weight = 1.0 if asks_copy_number(spec) else 0.52
    return round(
        min(1.0, max(mutation, 0.92 * variants, cna_weight * cna, 0.78 * altered)),
        4,
    )


def requested_gene_coverage(dataset: Any, spec: ResearchSpec) -> float | None:
    if not spec.genes:
        return None
    rows = list(getattr(dataset, "rows", []) or [])
    if not rows:
        names = {
            (column.name if hasattr(column, "name") else str(column)).casefold()
            for column in getattr(dataset, "columns", []) or []
        }
        hits = [
            1.0
            if f"{gene.casefold()}_mutation" in names
            else 0.52
            if f"{gene.casefold()}_cna" in names
            else 0.0
            for gene in spec.genes
        ]
        return round(fmean(hits), 4) if hits else 0.0
    scores = [gene_match_score(rows, gene, spec) for gene in spec.genes]
    return round(fmean(scores), 4)


def variable_fill_rate(rows: list[dict[str, Any]] | None, fields: list[str], *, matched: bool = False) -> float:
    records = list(rows or [])
    if not records:
        return 1.0 if matched else 0.0
    return round(fill_rate(records, fields), 4)
