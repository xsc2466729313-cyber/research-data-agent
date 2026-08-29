"""受控的乳腺癌公开数据检索入口目录。

入口目录用于扩展自主检索的候选范围，不代表这些入口已经成功获取数据。
每次实际调用仍由对应 Adapter 做官方接口、格式、缓存和响应校验。
"""

from __future__ import annotations

import json
import re
from typing import Any


MAX_SOURCE_ENTRIES = 20
MAX_ENTRIES_PER_TOOL = 6

# These are public breast-cancer cohorts known to be available in cBioPortal.
# Additional IDs matching the breast-cancer namespace are accepted by the
# adapter guard and may be proposed by the model.
CBIOPORTAL_BREAST_STUDIES = (
    "brca_metabric",
    "brca_tcga_pan_can_atlas_2018",
    "brca_tcga",
    "brca_tcga_gdc",
    "brca_aurora_2023",
    "brca_mapk_hp_msk_2021",
    "brca_mskcc_2019",
    "breast_alpelisib_2020",
)

# GEO is intentionally not restricted to a short accession allow-list. A
# valid GSE accession is an official NCBI namespace; the research agent is
# allowed to explore it, while the Adapter remains the source of truth for
# whether the accession exists and contains usable resources.
GEO_BREAST_ACCESSIONS = (
    "GSE76360",
    "GSE25066",
    "GSE96058",
)

# GDC project IDs are validated as official-looking identifiers and then
# checked by the GDC API. These known projects seed broad breast-cancer
# exploration without pretending that every project is breast-specific.
GDC_BREAST_PROJECTS = (
    "TCGA-BRCA",
    "CPTAC-2",
    "CPTAC-3",
)

CBIOPORTAL_STUDY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,127}$")
GEO_ACCESSION_PATTERN = re.compile(r"^GSE[1-9]\d*$")
GDC_PROJECT_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{1,63}$")


def call_key(call: dict[str, Any]) -> str:
    """Return a stable key so same-tool calls with different entries survive."""

    return f"{call.get('name')}:{json.dumps(call.get('arguments') or {}, sort_keys=True, ensure_ascii=False)}"


def entry_key(call: dict[str, Any]) -> str:
    """Return the provenance key for an actual database entry."""

    name = str(call.get("name") or "")
    args = call.get("arguments") or {}
    field = {
        "search_geo": "accession",
        "search_cbioportal": "study_id",
        "search_gdc": "project_id",
        "search_trials": "nct_id",
        "search_civic": "disease_name",
        "search_depmap": "query",
        "extract_paper_assets": "pmcid",
    }.get(name, "")
    value = str(args.get(field) or "").strip().casefold()
    return f"{name}:{value}:{call_key(call)}" if not value else f"{name}:{value}"


def is_breast_cancer_study_id(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(
        CBIOPORTAL_STUDY_PATTERN.fullmatch(normalized)
        and (normalized.startswith("brca_") or normalized.startswith("breast_"))
    )


def is_gdc_breast_project_id(value: str) -> bool:
    normalized = value.strip().upper()
    return bool(
        GDC_PROJECT_PATTERN.fullmatch(normalized)
        and (
            normalized in GDC_BREAST_PROJECTS
            or "BRCA" in normalized
            or normalized.startswith("BREAST")
            or normalized.startswith("CPTAC-")
        )
    )
