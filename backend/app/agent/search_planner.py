from __future__ import annotations

import re
from typing import Any

from backend.app.agent.accession_harvest import asks_pcr, asks_survival, catalog_query, literature_query, needs_clinical_outcome
from backend.app.agent.models import ResearchBrief
from backend.app.models import ResearchSpec
from backend.app.source_broker.source_catalog import seed_legacy_study_profiles

_STOPWORDS = {
    "the",
    "and",
    "or",
    "of",
    "in",
    "vs",
    "with",
    "for",
    "to",
    "is",
    "are",
    "its",
    "by",
    "on",
    "a",
    "an",
    "whether",
    "relationship",
    "between",
    "from",
    "into",
    "than",
    "that",
    "this",
    "among",
    "是否",
    "关系",
    "受到",
    "及其",
    "以及",
    "或者",
    "具有",
    "进行",
    "研究",
    "乳腺癌",
    "患者",
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+/.-]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# Legacy planner compatibility. The actual seed profiles now live in the
# versioned Source Broker catalog and remain pre-acquisition hints only.
_STUDY_PROFILES: tuple[dict[str, Any], ...] = seed_legacy_study_profiles()


def geo_search_applicable(spec: ResearchSpec) -> bool:
    """GEO series are expression/response cohorts, not default survival or inhibitor-trial sources."""
    blob = f"{spec.research_goal} {' '.join(spec.drugs)}"
    upper = blob.upper()
    if any(token in upper for token in ("ALPELISIB", "CAPIVASERTIB")) or any(
        token in (spec.research_goal or "") for token in ("阿培利司", "卡匹伐塞替")
    ):
        return False
    if any(term in blob for term in ("抑制剂", "抑制", "inhibitor", "Inhibitor")) and (
        "PI3K" in upper or "PIK3" in upper
    ):
        return False
    if "expression" in (spec.required_data_types or []):
        return True
    if asks_pcr(spec):
        return True
    if asks_survival(spec) and "treatment_response" not in (spec.outcomes or []):
        return False
    if not needs_clinical_outcome(spec):
        return False
    subtype = (spec.subtype or "").casefold()
    if "hr-positive" in subtype and ("her2-negative" in subtype or "her2-" in subtype):
        return False
    return True


def question_search_terms(question: str, spec: ResearchSpec, brief: ResearchBrief | None = None) -> list[str]:
    terms: list[str] = []
    if brief is not None:
        terms.extend(brief.keywords)
        terms.extend(field.label for field in brief.fields if field.priority == "primary")
        terms.extend(
            cohort.name
            for cohort in brief.named_cohorts
            if cohort.role in {"named_primary", "inferred_primary"}
        )
    terms.extend(spec.genes)
    terms.extend(spec.drugs)
    if spec.subtype:
        terms.append(spec.subtype)
    blob = question or spec.research_goal or ""
    for token in _TOKEN_RE.findall(blob):
        if token.casefold() in _STOPWORDS or len(token) <= 1:
            continue
        terms.append(token)
    for token in _CJK_RE.findall(blob):
        if token in _STOPWORDS or len(token) > 8:
            continue
        terms.append(token)
    cleaned: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = str(term or "").strip()
        if not key:
            continue
        folded = key.casefold()
        if folded in seen or folded in _STOPWORDS:
            continue
        seen.add(folded)
        cleaned.append(key)
    return cleaned[:16]


def infer_cohorts_from_fields(field_ids: set[str]) -> list[dict[str, str]]:
    """If a primary field is covered by exactly one known genomic cohort, infer that cohort."""
    inferred: list[dict[str, str]] = []
    seen: set[str] = set()
    for field_id in field_ids:
        covering = [
            profile
            for profile in _STUDY_PROFILES
            if _profile_covers(profile, field_id) and profile["tool"] in {"search_cbioportal", "search_gdc"}
        ]
        if len(covering) != 1:
            continue
        profile = covering[0]
        key = str(profile["arg_value"])
        if key in seen:
            continue
        seen.add(key)
        inferred.append(
            {
                "name": str(profile["name"]),
                "study_id": str(profile["arg_value"]) if profile["tool"] == "search_cbioportal" else "",
                "project_id": str(profile["arg_value"]) if profile["tool"] == "search_gdc" else "",
                "tool_name": str(profile["tool"]),
                "field_id": field_id,
            }
        )
    return inferred


def _primary_field_ids(brief: ResearchBrief | None, spec: ResearchSpec) -> set[str]:
    if brief is not None:
        ids = {field.field_id for field in brief.fields if field.priority == "primary"}
        if ids:
            return ids
    ids = {f"{gene.lower()}_mutation" for gene in spec.genes}
    if asks_pcr(spec):
        ids.add("pcr")
    elif "treatment_response" in (spec.outcomes or []) or (
        needs_clinical_outcome(spec) and not asks_survival(spec)
    ):
        ids.add("treatment_response")
    if asks_survival(spec):
        ids.update({"os_status", "dfs_status"})
    return ids


def _profile_covers(profile: dict[str, Any], field_id: str) -> bool:
    fields = profile["fields"]
    if field_id in fields:
        return True
    if field_id.endswith("_mutation") and "mutation" in fields:
        return True
    if field_id.endswith("_variants") and "mutation" in fields:
        return True
    if field_id in {"os_status", "os_months", "dfs_status", "dfs_months", "rfs_status"} and "survival" in fields:
        return True
    if field_id in {"pcr", "pcr_binary"} and ("pcr" in fields or "treatment_response" in fields):
        return True
    return False


def _field_rarity(field_id: str) -> float:
    covered = sum(1 for profile in _STUDY_PROFILES if _profile_covers(profile, field_id))
    return 1.0 / covered if covered else 0.0


def _weighted_coverage(profile: dict[str, Any], primary_ids: set[str]) -> float:
    if not primary_ids:
        return 0.0
    total = sum(_field_rarity(field_id) for field_id in primary_ids) or 1.0
    gained = sum(_field_rarity(field_id) for field_id in primary_ids if _profile_covers(profile, field_id))
    return gained / total


def _profile_score(
    profile: dict[str, Any],
    primary_ids: set[str],
    named_ids: set[str],
    spec: ResearchSpec,
) -> float:
    if profile["tool"] == "search_geo" and not geo_search_applicable(spec):
        return 0.0
    needles = profile.get("needles") or frozenset()
    needle_hit = bool(needles & primary_ids) or (asks_pcr(spec) and "pcr" in (profile.get("fields") or []))
    named_bonus = 1.0 if str(profile.get("arg_value") or "").casefold() in named_ids else 0.0
    if needles and not needle_hit and named_bonus == 0:
        return 0.0
    if profile.get("arg_value") == "breast_alpelisib_2020" and asks_survival(spec) and "treatment_response" not in (
        spec.outcomes or []
    ):
        return 0.0
    hits = sum(1 for field_id in primary_ids if _profile_covers(profile, field_id))
    if hits == 0 and named_bonus == 0:
        return 0.0
    coverage = _weighted_coverage(profile, primary_ids)
    needle_bonus = 0.4 if needle_hit else 0.0
    drug_bonus = 1.2 if spec.drugs and "treatment_response" in (profile.get("fields") or []) else 0.0
    return named_bonus * 2 + coverage + needle_bonus + drug_bonus


class FieldDrivenSearchPlanner:
    """Rank public sources by the question's primary fields and keywords."""

    def plan(self, spec: ResearchSpec, request: Any, brief: ResearchBrief | None = None) -> list[dict[str, Any]]:
        genes = spec.genes or ["PIK3CA"]
        max_records = int(getattr(request, "max_records", 10_000) or 10_000)
        primary_ids = _primary_field_ids(brief, spec)
        named_ids = {
            str(token).casefold()
            for cohort in (getattr(brief, "named_cohorts", None) or [])
            for token in (cohort.study_id, cohort.project_id)
            if token
        }
        ranked = sorted(
            (
                (_profile_score(profile, primary_ids, named_ids, spec), index, profile)
                for index, profile in enumerate(_STUDY_PROFILES)
            ),
            key=lambda item: (-item[0], item[1]),
        )
        cohort_calls: list[tuple[str, dict[str, Any]]] = []
        for score, _index, profile in ranked:
            if score <= 0:
                continue
            args: dict[str, Any] = {profile["arg_key"]: profile["arg_value"]}
            if profile["tool"] == "search_cbioportal":
                args["gene_symbols"] = genes
                args["max_records"] = max_records
            elif profile["tool"] == "search_geo":
                args["max_files"] = 5
            elif profile["tool"] == "search_gdc":
                data_types = ["Clinical Supplement"]
                if spec.genes or "mutation" in (spec.required_data_types or []):
                    data_types.append("Masked Somatic Mutation")
                args["data_types"] = data_types
                args["max_files"] = 5
            cohort_calls.append((profile["tool"], args))
        terms = question_search_terms(spec.research_goal, spec, brief)
        discovery: list[tuple[str, dict[str, Any]]] = []
        if spec.genes or asks_pcr(spec) or asks_survival(spec) or needs_clinical_outcome(spec) or terms:
            discovery.append(("search_geo_catalog", {"query": catalog_query(spec, extra_terms=terms), "max_records": 20}))
            discovery.append(
                ("search_europe_pmc", {"query": literature_query(spec, extra_terms=terms), "max_records": 20})
            )
        aux_early: list[tuple[str, dict[str, Any]]] = []
        if spec.drugs or "evidence" in (spec.required_data_types or []):
            if spec.drugs:
                aux_early.append(
                    (
                        "search_civic",
                        {
                            "disease_name": "Breast Cancer",
                            "molecular_profile_name": " ".join(genes),
                            "therapy_name": spec.drugs[0],
                            "max_items": 5,
                        },
                    )
                )
            if spec.drugs or any(term in spec.research_goal for term in ("试验", "招募", "临床研究")):
                aux_early.append(
                    (
                        "search_trials",
                        {
                            "condition": "Breast Cancer",
                            "query_terms": " ".join(spec.drugs + genes + terms[:6]),
                            "max_trials": 5,
                        },
                    )
                )
        aux_late: list[tuple[str, dict[str, Any]]] = []
        if "evidence" in (spec.required_data_types or []) and not spec.drugs:
            aux_late.append(
                (
                    "search_civic",
                    {
                        "disease_name": "Breast Cancer",
                        "molecular_profile_name": " ".join(genes),
                        "therapy_name": None,
                        "max_items": 5,
                    },
                )
            )
        aux_late.append(
            (
                "search_biosample",
                {"query": " ".join(["Breast Cancer", *genes, *terms[:8]]).strip(), "max_records": 20},
            )
        )
        if any(token in spec.research_goal.casefold() for token in ("细胞系", "auc", "ic50", "depmap", "药敏")):
            aux_early.append(
                (
                    "search_depmap",
                    {
                        "query": " ".join(["Breast Cancer cell line", *spec.drugs[:2], "AUC IC50"]).strip(),
                        "drug": spec.drugs[0] if spec.drugs else None,
                        "max_records": 50,
                    },
                )
            )
        if any(token in spec.research_goal for token in ("试验", "NCT", "登记", "招募")):
            aux_early.append(
                (
                    "search_trials",
                    {
                        "condition": "Breast Neoplasms",
                        "nct_id": "NCT01042379",
                        "query_terms": "I-SPY2 neoadjuvant",
                        "max_trials": 5,
                    },
                )
            )
        if "evidence" in (spec.required_data_types or []) or any(
            token in spec.research_goal for token in ("文献", "论文", "图注", "表格", "PMC")
        ):
            aux_late.append(
                (
                    "extract_paper_assets",
                    {"query": " ".join(["Breast Cancer", *genes, *terms[:6], "table"]).strip(), "max_records": 5},
                )
            )
        lead = 1 if cohort_calls and cohort_calls[0][0] == "search_geo" else min(2, len(cohort_calls))
        candidates = cohort_calls[:lead] + discovery + aux_early + cohort_calls[lead:] + aux_late
        focus = [str(item).strip() for item in getattr(request, "focus_accessions", []) or [] if str(item).strip()]
        focus_tools = {str(item).casefold() for item in getattr(request, "focus_tools", []) or []}
        forced: list[tuple[str, dict[str, Any]]] = []
        for accession in focus:
            upper = accession.upper()
            if upper.startswith("GSE"):
                forced.append(("search_geo", {"accession": upper, "max_files": 5}))
            elif upper.startswith("NCT"):
                forced.append(
                    (
                        "search_trials",
                        {
                            "condition": spec.disease or "Breast Neoplasms",
                            "nct_id": upper,
                            "query_terms": " ".join(spec.drugs + spec.genes),
                            "max_trials": 10,
                        },
                    )
                )
            elif accession.casefold() in {"depmap", "ccle"}:
                forced.append(("search_depmap", {"query": f"{spec.disease} cell line AUC IC50", "max_records": 80}))
            else:
                forced.append(("search_cbioportal", {"study_id": accession, "gene_symbols": genes or ["ERBB2"], "max_records": getattr(request, "max_records", 200)}))
        if forced:
            candidates = forced + candidates
        preferred = {value.casefold() for value in getattr(request, "preferred_sources", []) or []}
        preferred |= focus_tools
        if preferred:
            source_to_tool = {
                "ncbi geo": "search_geo",
                "geo": "search_geo",
                "search_geo": "search_geo",
                "clinicaltrials.gov": "search_trials",
                "search_trials": "search_trials",
                "aact": "search_trials",
                "depmap": "search_depmap",
                "search_depmap": "search_depmap",
                "civic": "search_civic",
                "cbioportal": "search_cbioportal",
                "gdc / tcga": "search_gdc",
                "gdc": "search_gdc",
            }

            def _preferred_rank(item: tuple[str, dict[str, Any]]) -> int:
                name, args = item
                blob = f"{name} {args}".casefold()
                for token in preferred:
                    mapped = source_to_tool.get(token, token)
                    if mapped == name or token in blob or token in name.casefold():
                        return 0
                    if token.startswith("gse") and str(args.get("accession") or "").casefold() == token:
                        return 0
                    if token.startswith("nct") and str(args.get("nct_id") or "").casefold() == token:
                        return 0
                return 1

            candidates.sort(key=_preferred_rank)
        return [
            {"id": f"rule-call-{index + 1}", "name": name, "arguments": args}
            for index, (name, args) in enumerate(candidates)
        ]

    def strategy_text(self, spec: ResearchSpec, brief: ResearchBrief | None = None) -> str:
        primary = [field.label for field in (brief.fields if brief else []) if field.priority == "primary"]
        terms = question_search_terms(spec.research_goal, spec, brief)
        focus = "、".join(primary or terms[:6]) or "题目关键词"
        named = [
            cohort.name
            for cohort in (brief.named_cohorts if brief else [])
            if cohort.role in {"named_primary", "inferred_primary"}
        ]
        unique = infer_cohorts_from_fields(_primary_field_ids(brief, spec))
        affinity = [item["name"] for item in unique if item["name"] not in named]
        if named:
            extra = f"；主字段还指向 { '、'.join(affinity) }" if affinity else ""
            return (
                f"按题目关键词与主字段（{focus}）检索；优先 { '、'.join(named) }{extra}，"
                "再按字段覆盖率补最匹配的独立队列，目录和文献只用来发现 accession。"
            )
        if affinity:
            return (
                f"按题目关键词与主字段（{focus}）检索；{ '、'.join(affinity) } 因覆盖本题特有字段被优先，"
                "其余来源按覆盖率排序，禁止跨研究贴患者。"
            )
        return (
            f"按题目关键词与主字段（{focus}）自主检索字段最全、最匹配的独立队列；"
            "目录和文献只用来发现 accession，不跨研究贴患者。"
        )
