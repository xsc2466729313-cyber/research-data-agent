from __future__ import annotations

import re
from typing import Any

from backend.app.agent.accession_harvest import asks_pcr, asks_survival, catalog_query, literature_query, needs_clinical_outcome
from backend.app.agent.models import ResearchBrief
from backend.app.models import ResearchSpec
from backend.app.oncology import default_genes, is_breast_cancer, resolve_cancer_profile, trial_condition
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


def _question_intents(spec: ResearchSpec) -> set[str]:
    text = spec.research_goal
    folded = text.casefold()
    intents: set[str] = set()
    def positive_marker(markers: tuple[str, ...]) -> bool:
        for marker in markers:
            start = 0
            while True:
                index = folded.find(marker, start)
                if index < 0:
                    break
                before = folded[max(0, index - 40):index]
                after = folded[index + len(marker):index + len(marker) + 40]
                negated = any(token in before for token in ("不要", "不得", "禁止", "不是", "排除"))
                negated = negated or ("不" in after and ("正例" in after or "主库" in after or "试验登记" in after))
                if not negated:
                    return True
                start = index + len(marker)
        return False

    if positive_marker(("细胞系", "cell line", "auc", "ic50", "depmap", "药敏")):
        intents.add("cell_line")
    if any(token in text for token in ("临床试验", "登记试验", "招募", "NCT")) or "trial registry" in folded:
        intents.add("trial_registry")
    if positive_marker(("文献级证据", "文献级预测性证据", "知识证据", "文献证据", "预测性证据")) or any(
        token in folded for token in ("literature-level", "knowledge evidence", "knowledgebase")
    ):
        intents.add("knowledge_only")
    if any(token in text for token in ("同一患者", "同患者", "患者内")) or "same patient" in folded:
        intents.add("same_patient")
    if spec.subtype and not spec.outcomes:
        intents.add("patient_stratification")
    if any(token in text for token in ("区分", "不得当成同一字段", "字段对齐")):
        intents.add("harmonization")
    if any(token in text for token in ("免疫组化", "IHC", "拷贝数", "CNA", "CNV")) and any(
        token in text for token in ("分列", "对照", "不要合并", "不得合并")
    ):
        intents.add("harmonization")
    if positive_marker(("化疗响应", "化疗队列")) and any(token in text for token in ("抗 HER2", "HER2 靶向")):
        intents.add("chemo_response_only")
    return intents


def _named_profile_calls(spec: ResearchSpec) -> list[tuple[str, dict[str, Any]]]:
    """Resolve explicit identifiers and distinctive catalog names before broad discovery."""
    text = spec.research_goal
    found: list[tuple[str, dict[str, Any]]] = []
    explicit = {token.upper() for token in re.findall(r"\b(?:GSE\d+|NCT\d{8})\b", text, re.I)}
    compact = re.sub(r"[^a-z0-9]+", "", text.casefold())
    for profile in _STUDY_PROFILES:
        accession = str(profile["arg_value"])
        title = str(profile["name"])
        distinctive = [
            token
            for token in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?", title)
            if len(re.sub(r"[^A-Za-z0-9]", "", token)) >= 5
            and token.casefold() not in {"breast", "cancer", "study", "cohort", "series", "expression"}
        ]
        name_hit = any(
            "-" in token and re.sub(r"[^a-z0-9]+", "", token.casefold()) in compact
            for token in distinctive
        )
        if accession.upper() not in explicit and not name_hit:
            continue
        args: dict[str, Any] = {profile["arg_key"]: accession}
        if profile["tool"] == "search_cbioportal":
            args.update({"gene_symbols": spec.genes or ["ERBB2"], "max_records": 200})
        elif profile["tool"] == "search_geo":
            args["max_files"] = 5
        elif profile["tool"] == "search_gdc":
            args.update({"data_types": ["Clinical Supplement"], "max_files": 5})
        found.append((str(profile["tool"]), args))
    for accession in sorted(explicit):
        if any(accession == str(args.get("accession") or args.get("nct_id") or "").upper() for _, args in found):
            continue
        if accession.startswith("GSE"):
            found.append(("search_geo", {"accession": accession, "max_files": 5}))
        else:
            found.append(("search_trials", {"condition": spec.disease, "nct_id": accession, "max_trials": 10}))
    return found


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
    if "ESR1" in spec.genes and any(token in spec.research_goal for token in ("ER 状态", "ER status", "ER/")):
        ids.add("er_status")
    if asks_pcr(spec):
        ids.add("pcr")
    elif "treatment_response" in (spec.outcomes or []) or "treatment_response" in (spec.required_data_types or []):
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
    needle_hit = bool(needles & primary_ids) or any(
        _profile_covers(profile, field_id) for field_id in primary_ids
    ) or (asks_pcr(spec) and "pcr" in (profile.get("fields") or []))
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
        cancer_profile = resolve_cancer_profile(spec.disease)
        breast_specific = is_breast_cancer(spec.disease)
        genes = spec.genes or default_genes(spec.disease)
        max_records = int(getattr(request, "max_records", 10_000) or 10_000)
        primary_ids = _primary_field_ids(brief, spec)
        intents = _question_intents(spec)
        if spec.genes and not spec.outcomes and "cell_line" not in intents:
            intents.add("clinical_features")
        named_ids = {
            str(token).casefold()
            for cohort in (getattr(brief, "named_cohorts", None) or [])
            for token in (cohort.study_id, cohort.project_id)
            if token
        }
        ranked = sorted(
            (
                (_profile_score(profile, primary_ids, named_ids, spec), index, profile)
                for index, profile in enumerate(_STUDY_PROFILES if breast_specific else ())
            ),
            key=lambda item: (-item[0], item[1]),
        )
        cohort_calls: list[tuple[str, dict[str, Any]]] = []
        for score, _index, profile in ranked:
            if intents & {"cell_line", "trial_registry", "knowledge_only"}:
                continue
            if "chemo_response_only" in intents and profile["tool"] != "search_geo":
                continue
            if "chemo_response_only" in intents and profile["arg_value"] != "GSE25066":
                continue
            if "HER2-positive" in (spec.subtype or "") and not spec.genes and profile["tool"] != "search_geo":
                continue
            if "HER2-positive" in (spec.subtype or "") and profile["arg_value"] == "GSE25066":
                continue
            if (
                "clinical_features" in intents
                and "treatment_response" in (profile.get("fields") or [])
                and "treatment_response" in (profile.get("needles") or [])
            ):
                continue
            if "same_patient" in intents and primary_ids and not all(
                _profile_covers(profile, field_id) for field_id in primary_ids
            ):
                continue
            if "knowledge_only" in intents and profile["tool"] != "search_civic":
                continue
            if "harmonization" in intents and profile["tool"] == "search_civic":
                continue
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
        if cancer_profile is not None and not breast_specific and not intents & {
            "cell_line",
            "trial_registry",
            "knowledge_only",
        }:
            if cancer_profile.cbioportal_studies:
                cohort_calls.append(
                    (
                        "search_cbioportal",
                        {
                            "study_id": cancer_profile.cbioportal_studies[0],
                            "gene_symbols": genes,
                            "max_records": max_records,
                        },
                    )
                )
            if cancer_profile.gdc_projects:
                data_types = ["Clinical Supplement"]
                if spec.genes or "mutation" in (spec.required_data_types or []):
                    data_types.append("Masked Somatic Mutation")
                cohort_calls.append(
                    (
                        "search_gdc",
                        {
                            "project_id": cancer_profile.gdc_projects[0],
                            "data_types": data_types,
                            "max_files": 5,
                        },
                    )
                )
        if breast_specific and "patient_stratification" in intents and not cohort_calls:
            for profile in _STUDY_PROFILES:
                fields = profile.get("fields") or frozenset()
                if profile["tool"] in {"search_cbioportal", "search_gdc"} and "subtype" in fields:
                    args = {profile["arg_key"]: profile["arg_value"]}
                    if profile["tool"] == "search_cbioportal":
                        args.update({"gene_symbols": genes, "max_records": max_records})
                    else:
                        args.update({"data_types": ["Clinical Supplement"], "max_files": 5})
                    cohort_calls.append((profile["tool"], args))
        if asks_pcr(spec):
            cohort_calls.sort(key=lambda item: 0 if item[0] == "search_geo" else 1)
        if cohort_calls and not intents & {"cell_line", "trial_registry", "knowledge_only"}:
            # Keep a small, source-diverse cohort set for patient-level tasks.
            if named_ids:
                cohort_calls = cohort_calls[:2]
            else:
                selected = [cohort_calls[0]]
                first_tool = cohort_calls[0][0]
                selected.extend(call for call in cohort_calls[1:] if call[0] != first_tool and len(selected) < 2)
                selected.extend(call for call in cohort_calls[1:] if call not in selected and len(selected) < 2)
                cohort_calls = selected
        if breast_specific and "ERBB2" in spec.genes and not intents & {"harmonization", "knowledge_only"} and (
            asks_pcr(spec) or "treatment_response" in (spec.outcomes or [])
        ):
            if not any(name == "search_geo" and args.get("accession") == "GSE76360" for name, args in cohort_calls):
                cohort_calls.insert(0, ("search_geo", {"accession": "GSE76360", "max_files": 5}))
        terms = question_search_terms(spec.research_goal, spec, brief)
        discovery: list[tuple[str, dict[str, Any]]] = []
        if not intents & {"cell_line", "trial_registry", "knowledge_only"} and (spec.genes or asks_pcr(spec) or asks_survival(spec) or needs_clinical_outcome(spec) or terms):
            discovery.append(("search_geo_catalog", {"query": catalog_query(spec, extra_terms=terms), "max_records": 20}))
            discovery.append(
                ("search_europe_pmc", {"query": literature_query(spec, extra_terms=terms), "max_records": 20})
            )
        aux_early: list[tuple[str, dict[str, Any]]] = []
        civic_relevant = (
            (bool(spec.drugs) and "same_patient" not in intents)
            or "knowledge_only" in intents
        )
        if spec.drugs or civic_relevant:
            if civic_relevant:
                aux_early.append(
                    (
                        "search_civic",
                        {
                            "disease_name": spec.disease,
                            "molecular_profile_name": " ".join(genes),
                            "therapy_name": spec.drugs[0] if spec.drugs else None,
                            "max_items": 5,
                        },
                    )
                )
            if (spec.drugs and "same_patient" not in intents) or "trial_registry" in intents:
                aux_early.append(
                    (
                        "search_trials",
                        {
                            "condition": trial_condition(spec.disease),
                            "query_terms": " ".join(spec.drugs + genes + terms[:6]),
                            "max_trials": 5,
                        },
                    )
                )
        aux_late: list[tuple[str, dict[str, Any]]] = []
        if "knowledge_only" in intents and not spec.drugs:
            aux_late.append(
                (
                    "search_civic",
                    {
                        "disease_name": spec.disease,
                        "molecular_profile_name": " ".join(genes),
                        "therapy_name": None,
                        "max_items": 5,
                    },
                )
            )
        if not intents & {"cell_line", "trial_registry", "knowledge_only"}:
            aux_late.append(
                (
                    "search_biosample",
                    {"query": " ".join([spec.disease, *genes, *terms[:8]]).strip(), "max_records": 20},
                )
            )
        if "cell_line" in intents:
            aux_early.append(
                (
                    "search_depmap",
                    {
                        "query": " ".join([f"{spec.disease} cell line", *spec.drugs[:2], "AUC IC50"]).strip(),
                        "drug": spec.drugs[0] if spec.drugs else None,
                        "max_records": 50,
                    },
                )
            )
        if "trial_registry" in intents:
            trial_id = (
                "NCT01042379"
                if breast_specific and any(token in spec.research_goal for token in ("I-SPY", "NCT01042379"))
                else "NCT01104584"
                if breast_specific
                else None
            )
            trial_arguments = {
                "condition": trial_condition(spec.disease),
                "query_terms": " ".join(spec.drugs + genes + terms[:6]),
                "max_trials": 5,
            }
            if trial_id:
                trial_arguments["nct_id"] = trial_id
            aux_early.append(
                (
                    "search_trials",
                    trial_arguments,
                )
            )
        if "knowledge_only" in intents or any(
            token in spec.research_goal for token in ("文献", "论文", "图注", "表格", "PMC")
        ):
            aux_late.append(
                (
                    "extract_paper_assets",
                    {"query": " ".join([spec.disease, *genes, *terms[:6], "table"]).strip(), "max_records": 5},
                )
            )
        lead = 1 if cohort_calls and cohort_calls[0][0] == "search_geo" else min(2, len(cohort_calls))
        named_calls = _named_profile_calls(spec)
        if named_calls and "expression" in (spec.required_data_types or []) and not spec.genes:
            cohort_calls = []
            lead = 0
        candidates = named_calls + cohort_calls[:lead] + discovery + aux_early + cohort_calls[lead:] + aux_late
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
        deduplicated: list[tuple[str, dict[str, Any]]] = []
        seen_calls: set[str] = set()
        for name, args in candidates:
            key = f"{name}|{sorted((str(k), str(v)) for k, v in args.items())}"
            if key in seen_calls:
                continue
            seen_calls.add(key)
            deduplicated.append((name, args))
        budget = int(getattr(request, "max_sources", len(deduplicated)) or len(deduplicated))
        return [
            {"id": f"rule-call-{index + 1}", "name": name, "arguments": args}
            for index, (name, args) in enumerate(deduplicated[:budget])
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
        unique = infer_cohorts_from_fields(_primary_field_ids(brief, spec)) if is_breast_cancer(spec.disease) else []
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
