from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.accession_harvest import asks_pcr, asks_survival, needs_clinical_outcome
from backend.app.models import ResearchSpec
from backend.app.oncology import is_breast_cancer


PCR_SWITCH_ACCESSIONS = ("GSE25066", "GSE76360", "GSE50948")
TRIAL_SWITCH_IDS = ("NCT01104584",)
SURVIVAL_CANONICAL = {
    "os_status",
    "os_months",
    "dfs_status",
    "dfs_months",
    "dss_status",
    "dss_months",
    "vital_status",
}
SURVIVAL_SYNONYMS = {
    "overall_survival",
    "overall_survival_months",
    "os",
    "dss",
    "dss_status",
    "dss_months",
    "rfs_status",
    "rfs_months",
    "disease_free_survival",
    "disease_free_survival_months",
    "disease_specific_survival",
}
PCR_CANONICAL = {"pcr", "pcr_binary", "treatment_response", "response", "pathological_complete_response"}
PCR_SYNONYMS = {
    "pathological_complete_response",
    "pathologic_complete_response",
    "pcr_status",
    "pcr_yes_no",
    "response_at_surgery",
    "residual_cancer_burden",
}
FORBIDDEN_AS_PCR = {
    "os_status",
    "os_months",
    "dfs_status",
    "dfs_months",
    "dss_status",
    "dss_months",
    "vital_status",
    "auc",
    "ic50",
}


@dataclass
class OutcomeRepairPlan:
    gap_kind: str
    needed: str
    present: list[str] = field(default_factory=list)
    focus_accessions: list[str] = field(default_factory=list)
    focus_tools: list[str] = field(default_factory=list)
    map_synonyms: bool = False
    rationale: str = ""
    forbidden_note: str = ""

    @property
    def material(self) -> bool:
        return self.gap_kind in {"wrong_cohort", "unmapped_synonym", "missing"}


def _column_names(dataset: Any | None) -> set[str]:
    names: set[str] = set()
    if dataset is None:
        return names
    for column in getattr(dataset, "columns", None) or []:
        name = getattr(column, "name", None) or str(column)
        if name:
            names.add(str(name).casefold())
    for row in list(getattr(dataset, "rows", None) or [])[:8]:
        if isinstance(row, dict):
            names.update(str(key).casefold() for key in row)
    target = getattr(dataset, "target_column", None)
    if target:
        names.add(str(target).casefold())
    return names


def _needed_outcome(spec: ResearchSpec | None, question: str) -> str:
    if spec is not None:
        if asks_pcr(spec):
            return "pCR"
        if asks_survival(spec) or "survival" in (spec.outcomes or []):
            return "survival"
        blob = " ".join([spec.research_goal, *spec.outcomes, *spec.required_data_types]).casefold()
        if any(token in blob for token in ("auc", "ic50", "细胞系", "depmap")):
            return "cell_line"
        if needs_clinical_outcome(spec):
            return "response"
        return "none"
    text = (question or "").casefold()
    if any(token in text for token in ("pcr", "病理完全缓解")):
        return "pCR"
    if any(token in text for token in ("os", "生存", "rfs", "dss")):
        return "survival"
    if any(token in text for token in ("auc", "ic50", "细胞系", "depmap")):
        return "cell_line"
    if any(token in text for token in ("响应", "response", "疗效")):
        return "response"
    return "none"


def diagnose_outcome_gap(
    *,
    spec: ResearchSpec | None,
    dataset: Any | None,
    target_match_rate: float | None,
    question: str = "",
) -> OutcomeRepairPlan:
    needed = _needed_outcome(spec, question)
    present = sorted(_column_names(dataset))
    present_set = set(present)
    matched = float(target_match_rate or 0.0) >= 0.45
    if needed in {"none"} or matched:
        return OutcomeRepairPlan(gap_kind="none", needed=needed, present=present, rationale="结局已匹配或本题不强制临床终点。")

    has_pcr = bool(present_set & PCR_CANONICAL) or bool(present_set & PCR_SYNONYMS)
    has_survival = bool(present_set & SURVIVAL_CANONICAL) or bool(present_set & SURVIVAL_SYNONYMS)
    has_cell = bool(present_set & {"auc", "ic50"})
    breast_specific = is_breast_cancer(spec.disease if spec is not None else question)
    response_accessions = list(PCR_SWITCH_ACCESSIONS) if breast_specific else []
    response_tools = ["search_geo", "search_trials"] if breast_specific else [
        "search_geo_catalog",
        "search_trials",
        "search_cbioportal",
    ]
    unmapped_survival = bool(present_set & SURVIVAL_SYNONYMS) and not bool(present_set & {"os_status", "os_months", "dfs_status", "dfs_months"})
    unmapped_pcr = bool(present_set & PCR_SYNONYMS) and not bool(present_set & {"pcr", "pcr_binary", "treatment_response"})

    if needed in {"pCR", "response"}:
        if has_pcr and unmapped_pcr:
            return OutcomeRepairPlan(
                gap_kind="unmapped_synonym",
                needed=needed,
                present=present,
                map_synonyms=True,
                rationale="当前表已有可映射的治疗响应/pCR 同义列，第二轮做字段对齐，不用生存冒充 pCR。",
                forbidden_note="禁止把 OS/RFS/DSS 或细胞系 AUC/IC50 写成患者 pCR。",
            )
        if has_survival and not has_pcr:
            return OutcomeRepairPlan(
                gap_kind="wrong_cohort",
                needed=needed,
                present=present,
                focus_accessions=response_accessions,
                focus_tools=response_tools,
                rationale=(
                    "当前队列只有生存结局，与本题 pCR/治疗响应不同域。第二轮改搜乳腺癌患者响应队列。"
                    if breast_specific
                    else "当前队列只有生存结局，与本题治疗响应不同域。第二轮按当前癌种重新发现响应队列。"
                ),
                forbidden_note="禁止用总体生存冒充 pCR。",
            )
        if has_cell and not has_pcr:
            return OutcomeRepairPlan(
                gap_kind="wrong_cohort",
                needed=needed,
                present=present,
                focus_accessions=response_accessions,
                focus_tools=response_tools,
                rationale="当前是细胞系药敏表，不能当患者临床响应。第二轮按当前癌种重新发现患者队列。",
                forbidden_note="禁止把 AUC/IC50 写成患者 pCR。",
            )
        return OutcomeRepairPlan(
            gap_kind="missing",
            needed=needed,
            present=present,
            focus_accessions=(response_accessions + list(TRIAL_SWITCH_IDS) if breast_specific else []),
            focus_tools=response_tools,
            rationale=(
                "当前表没有识别到本题结局。第二轮补搜含 pCR/治疗响应的乳腺癌 GEO 系列和登记试验。"
                if breast_specific
                else "当前表没有识别到本题结局。第二轮按当前癌种重新发现队列、试验和公开数据。"
            ),
            forbidden_note="分不清域则进入 review，不跨域贴值。",
        )

    if needed == "survival":
        if unmapped_survival or (has_survival and not matched):
            return OutcomeRepairPlan(
                gap_kind="unmapped_synonym",
                needed=needed,
                present=present,
                map_synonyms=True,
                rationale="当前表有 OS/RFS/DSS 等同义列，第二轮映射到 canonical 生存字段并保留 raw_field。",
            )
        return OutcomeRepairPlan(
            gap_kind="missing",
            needed=needed,
            present=present,
            focus_tools=["search_cbioportal", "search_gdc"],
            rationale="本题要生存结局，当前表未识别到 OS/RFS/DSS。第二轮改搜当前癌种的 cBioPortal/TCGA 临床表。",
        )

    if needed == "cell_line":
        return OutcomeRepairPlan(
            gap_kind="missing" if not has_cell else "none",
            needed=needed,
            present=present,
            focus_tools=["search_depmap"] if not has_cell else [],
            rationale="本题要细胞系药敏，第二轮调用 DepMap；结果保留 preclinical_cell_line。" if not has_cell else "细胞系结局已匹配。",
        )

    return OutcomeRepairPlan(gap_kind="none", needed=needed, present=present)
