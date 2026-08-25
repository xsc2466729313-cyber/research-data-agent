from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from backend.app.agent.accession_harvest import catalog_query, literature_query
from backend.app.agent.models import AgentGoalStatus, CollectionGap, CollectionSearchAction
from backend.app.models import ResearchSpec


Diagnosis = Literal[
    "all_met",
    "no_patient_table",
    "outcome_mismatch",
    "missing_same_cohort_exposure",
    "missing_clinical_covariates",
    "missing_evidence",
    "residual_gaps",
]

StopAction = Literal["continue", "stop_pass", "stop_partial", "stop_exhausted"]


DIAGNOSIS_LABELS: dict[str, str] = {
    "all_met": "当前方法已满足研究目标",
    "no_patient_table": "尚未形成患者/样本主表，更换可解析队列",
    "outcome_mismatch": "结局域不匹配，切换含治疗响应的独立队列",
    "missing_same_cohort_exposure": "分子暴露与结局不在同一患者队列，寻找可同时解析两者的独立研究",
    "missing_clinical_covariates": "临床/样本协变量不足，改用官方临床表补充",
    "missing_evidence": "解释层证据不足，补充知识库或试验目录",
    "residual_gaps": "仍有字段缺口，改用尚未尝试的方法",
}


@dataclass(frozen=True)
class MethodStrategy:
    strategy_id: str
    label: str
    tool_name: str
    source_name: str
    priority: int
    diagnoses: frozenset[str]
    primary_cohort: bool
    has_response: bool
    has_mutation: bool
    argument_builder: Callable[[ResearchSpec, int], dict[str, Any]]
    applicable: Callable[[ResearchSpec], bool] = lambda spec: True


def _her2_positive_response(spec: ResearchSpec) -> bool:
    subtype = (spec.subtype or "").casefold()
    return "her2-positive" in subtype and "her2-negative" not in subtype


def _should_search_geo(spec: ResearchSpec) -> bool:
    text = f"{spec.research_goal} {' '.join(spec.drugs)}".upper()
    if "PI3K" in text or "ALPELISIB" in text or "CAPIVASERTIB" in text or "阿培利司" in spec.research_goal:
        return False
    if "expression" in spec.required_data_types:
        return True
    if "treatment_response" not in spec.required_data_types:
        return False
    subtype = (spec.subtype or "").casefold()
    if "hr-positive" in subtype and ("her2-negative" in subtype or "her2-" in subtype):
        return False
    return True


def _genes(spec: ResearchSpec) -> list[str]:
    return spec.genes or ["ERBB2", "PIK3CA"]


STRATEGIES: tuple[MethodStrategy, ...] = (
    MethodStrategy(
        strategy_id="cohort.geo.gse76360",
        label="切换独立队列 GSE76360（HER2 阳性术前曲妥珠单抗响应）",
        tool_name="search_geo",
        source_name="NCBI GEO",
        priority=1,
        diagnoses=frozenset({"outcome_mismatch", "no_patient_table", "missing_same_cohort_exposure"}),
        primary_cohort=True,
        has_response=True,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {"accession": "GSE76360", "max_files": 5},
        applicable=lambda spec: _should_search_geo(spec) and _her2_positive_response(spec),
    ),
    MethodStrategy(
        strategy_id="cohort.geo.gse25066",
        label="切换独立队列 GSE25066（新辅助化疗响应）",
        tool_name="search_geo",
        source_name="NCBI GEO",
        priority=2,
        diagnoses=frozenset({"outcome_mismatch", "no_patient_table", "missing_same_cohort_exposure"}),
        primary_cohort=True,
        has_response=True,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {"accession": "GSE25066", "max_files": 5},
        applicable=_should_search_geo,
    ),
    MethodStrategy(
        strategy_id="cohort.geo.gse96058",
        label="切换独立队列 GSE96058（长期随访表达谱）",
        tool_name="search_geo",
        source_name="NCBI GEO",
        priority=3,
        diagnoses=frozenset({"no_patient_table", "residual_gaps"}),
        primary_cohort=True,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {"accession": "GSE96058", "max_files": 5},
        applicable=_should_search_geo,
    ),
    MethodStrategy(
        strategy_id="cohort.cbio.metabric",
        label="检索 cBioPortal METABRIC 临床与分子队列",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=4,
        diagnoses=frozenset({"no_patient_table", "missing_same_cohort_exposure", "missing_clinical_covariates"}),
        primary_cohort=True,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": "brca_metabric",
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
    ),
    MethodStrategy(
        strategy_id="cohort.cbio.tcga",
        label="改用 cBioPortal TCGA-BRCA 患者级临床/突变表",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=5,
        diagnoses=frozenset(
            {"no_patient_table", "missing_same_cohort_exposure", "missing_clinical_covariates", "residual_gaps"}
        ),
        primary_cohort=True,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": "brca_tcga",
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
    ),
    MethodStrategy(
        strategy_id="cohort.cbio.pancan",
        label="改用 cBioPortal TCGA Pan-Cancer BRCA 队列",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=6,
        diagnoses=frozenset({"no_patient_table", "missing_same_cohort_exposure", "residual_gaps"}),
        primary_cohort=True,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": "brca_tcga_pan_can_atlas_2018",
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
    ),
    MethodStrategy(
        strategy_id="files.gdc.clinical_mutation",
        label="扩大 GDC/TCGA 官方临床补充与突变文件检索",
        tool_name="search_gdc",
        source_name="GDC / TCGA",
        priority=7,
        diagnoses=frozenset({"missing_clinical_covariates", "missing_same_cohort_exposure", "residual_gaps"}),
        primary_cohort=False,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "project_id": "TCGA-BRCA",
            "data_types": ["Clinical Supplement", "Masked Somatic Mutation"],
            "max_files": 20,
        },
    ),
    MethodStrategy(
        strategy_id="context.trials",
        label="补充 ClinicalTrials.gov 方案与响应定义（解释层）",
        tool_name="search_trials",
        source_name="ClinicalTrials.gov",
        priority=8,
        diagnoses=frozenset({"missing_evidence", "outcome_mismatch", "residual_gaps"}),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "condition": spec.disease,
            "query_terms": " ".join(spec.drugs + spec.genes),
            "max_trials": 10,
        },
    ),
    MethodStrategy(
        strategy_id="context.civic",
        label="补充 CIViC 基因-药物证据（解释层，不写入患者主表）",
        tool_name="search_civic",
        source_name="CIViC",
        priority=9,
        diagnoses=frozenset({"missing_evidence", "residual_gaps"}),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "disease_name": spec.disease,
            "molecular_profile_name": spec.genes[0] if spec.genes else None,
            "therapy_name": spec.drugs[0] if spec.drugs else None,
            "max_items": 10,
        },
    ),
    MethodStrategy(
        strategy_id="discover.geo.catalog",
        label="上网检索 NCBI GEO 目录，发现尚未尝试的 Series",
        tool_name="search_geo_catalog",
        source_name="NCBI GEO",
        priority=10,
        diagnoses=frozenset(
            {
                "no_patient_table",
                "outcome_mismatch",
                "missing_same_cohort_exposure",
                "residual_gaps",
            }
        ),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "query": catalog_query(spec),
            "max_records": 20,
        },
    ),
    MethodStrategy(
        strategy_id="discover.literature.pmc",
        label="检索 Europe PMC 文献，从摘要中收集 GSE/NCT",
        tool_name="search_europe_pmc",
        source_name="Europe PMC",
        priority=11,
        diagnoses=frozenset(
            {
                "no_patient_table",
                "outcome_mismatch",
                "missing_same_cohort_exposure",
                "missing_evidence",
                "residual_gaps",
            }
        ),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "query": literature_query(spec),
            "max_records": 20,
        },
    ),
)


@dataclass
class LoopDecision:
    action: StopAction
    diagnosis: Diagnosis
    quality_gate: str
    note: str
    goals: list[AgentGoalStatus]
    actions: list[CollectionSearchAction]
    next_strategy_ids: list[str]


class GoalLoopController:
    """Observe gaps, diagnose failure type, switch unused methods until goals are met."""

    def evaluate_goals(
        self,
        *,
        spec: ResearchSpec,
        dataset: Any | None,
        readiness: Any | None,
        cohort: Any | None = None,
    ) -> list[AgentGoalStatus]:
        row_count = int(getattr(dataset, "row_count", 0) or 0)
        target_match = bool(getattr(readiness, "target_match", False))
        gene_coverage = getattr(readiness, "requested_variable_coverage_rate", None)
        cohort_rows = int(getattr(cohort, "final_row_count", row_count) or 0)
        needs_response = "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types
        needs_genes = bool(spec.genes)

        patient_table = row_count >= 30
        matched_outcome = (not needs_response) or target_match
        analysis_cohort = cohort_rows > 0 if matched_outcome and row_count else False
        if not needs_response:
            analysis_cohort = row_count > 0
        same_cohort_exposure = True
        if needs_genes:
            same_cohort_exposure = gene_coverage is not None and gene_coverage >= 1

        return [
            AgentGoalStatus(
                goal_id="patient_table",
                label="形成可审计的患者/样本主表",
                required=True,
                met=patient_table,
                evidence=f"{row_count} 行",
            ),
            AgentGoalStatus(
                goal_id="matched_outcome",
                label="研究结局与问题同一数据域",
                required=needs_response,
                met=matched_outcome,
                evidence="治疗响应已匹配" if target_match else "结局尚未匹配",
            ),
            AgentGoalStatus(
                goal_id="analysis_cohort",
                label="筛选出非空分析队列",
                required=True,
                met=analysis_cohort,
                evidence=f"分析队列 {cohort_rows} 行",
            ),
            AgentGoalStatus(
                goal_id="same_cohort_exposure",
                label="分子暴露与结局来自同一患者队列",
                required=needs_genes,
                met=same_cohort_exposure,
                evidence=(
                    "基因变量已覆盖"
                    if same_cohort_exposure
                    else "当前队列缺少同患者分子检测，禁止跨库贴字段"
                ),
            ),
        ]

    def diagnose(
        self,
        *,
        spec: ResearchSpec,
        dataset: Any | None,
        readiness: Any | None,
        gaps: list[CollectionGap],
        goals: list[AgentGoalStatus] | None = None,
    ) -> Diagnosis:
        if dataset is None and gaps:
            return self._diagnose_from_gaps(spec, gaps)
        goals = goals or self.evaluate_goals(spec=spec, dataset=dataset, readiness=readiness)
        if all(not goal.required or goal.met for goal in goals):
            return "all_met"
        by_id = {goal.goal_id: goal for goal in goals}
        if not by_id["patient_table"].met:
            if any(gap.variable_id in {"treatment_response", "outcome"} for gap in gaps):
                return "outcome_mismatch"
            return "no_patient_table"
        if by_id["matched_outcome"].required and not by_id["matched_outcome"].met:
            return "outcome_mismatch"
        if by_id["same_cohort_exposure"].required and not by_id["same_cohort_exposure"].met:
            return "missing_same_cohort_exposure"
        gap_ids = {gap.variable_id for gap in gaps}
        if {"sample_type", "age", "stage", "sample_source", "sample_timepoint"} & gap_ids:
            return "missing_clinical_covariates"
        if "evidence" in gap_ids or "knowledge_evidence" in spec.required_data_types:
            return "missing_evidence"
        return "residual_gaps"

    def next_actions(
        self,
        *,
        spec: ResearchSpec,
        diagnosis: Diagnosis,
        attempted_calls: set[str],
        max_records: int,
        limit: int = 2,
    ) -> list[CollectionSearchAction]:
        if diagnosis == "all_met":
            return []
        actions: list[CollectionSearchAction] = []
        for strategy in self._candidates(spec, diagnosis):
            arguments = strategy.argument_builder(spec, max_records)
            call = {"name": strategy.tool_name, "arguments": arguments}
            if self.call_key(call) in attempted_calls:
                continue
            if any(
                self.call_key({"name": item.tool_name, "arguments": item.arguments}) == self.call_key(call)
                for item in actions
            ):
                continue
            actions.append(
                CollectionSearchAction(
                    action_id=f"follow-up-{strategy.strategy_id}",
                    tool_name=strategy.tool_name,
                    source_name=strategy.source_name,
                    priority=strategy.priority,
                    rationale=f"{DIAGNOSIS_LABELS[diagnosis]}。下一方法：{strategy.label}。",
                    status="待执行",
                    arguments=arguments,
                    strategy_id=strategy.strategy_id,
                    strategy_label=strategy.label,
                )
            )
            if len(actions) >= limit:
                break
        return actions

    def decide(
        self,
        *,
        spec: ResearchSpec,
        dataset: Any | None,
        readiness: Any | None,
        gaps: list[CollectionGap],
        attempted_calls: set[str],
        max_records: int,
        round_number: int,
        max_rounds: int,
        cohort: Any | None = None,
        follow_up_limit: int = 2,
    ) -> LoopDecision:
        goals = self.evaluate_goals(spec=spec, dataset=dataset, readiness=readiness, cohort=cohort)
        diagnosis = self.diagnose(spec=spec, dataset=dataset, readiness=readiness, gaps=gaps, goals=goals)
        primary_open = [goal for goal in goals if goal.required and goal.goal_id != "same_cohort_exposure" and not goal.met]
        secondary_open = [goal for goal in goals if goal.required and goal.goal_id == "same_cohort_exposure" and not goal.met]
        actions = self.next_actions(
            spec=spec,
            diagnosis=diagnosis,
            attempted_calls=attempted_calls,
            max_records=max_records,
            limit=follow_up_limit,
        )
        if diagnosis == "all_met":
            return LoopDecision(
                action="stop_pass",
                diagnosis=diagnosis,
                quality_gate="PASS",
                note="全部研究目标已满足；停止换方法，进入质量门汇总。",
                goals=goals,
                actions=[],
                next_strategy_ids=[],
            )
        if not primary_open and secondary_open and not actions:
            return LoopDecision(
                action="stop_partial",
                diagnosis=diagnosis,
                quality_gate="PARTIAL",
                note=(
                    "主目标已达成：独立队列已有匹配的治疗响应分析集。"
                    "已检索公开目录与文献，仍无法在不跨库贴患者的前提下补齐同队列分子暴露，停止空转。"
                ),
                goals=goals,
                actions=[],
                next_strategy_ids=[],
            )
        if not actions:
            return LoopDecision(
                action="stop_exhausted",
                diagnosis=diagnosis,
                quality_gate="REVIEW",
                note="已无尚未尝试且能缩小当前缺口的方法；保留缺口，不编造字段。",
                goals=goals,
                actions=[],
                next_strategy_ids=[],
            )
        if round_number >= max_rounds:
            return LoopDecision(
                action="stop_exhausted",
                diagnosis=diagnosis,
                quality_gate="PARTIAL" if not primary_open else "REVIEW",
                note=f"已达到最大迭代轮次 {max_rounds}；保留已取得的最佳队列与未闭合缺口。",
                goals=goals,
                actions=actions,
                next_strategy_ids=[item.strategy_id for item in actions if item.strategy_id],
            )
        return LoopDecision(
            action="continue",
            diagnosis=diagnosis,
            quality_gate="REVIEW",
            note=f"{DIAGNOSIS_LABELS[diagnosis]}；将执行：{'；'.join(item.strategy_label or item.source_name for item in actions)}。",
            goals=goals,
            actions=actions,
            next_strategy_ids=[item.strategy_id for item in actions if item.strategy_id],
        )

    @staticmethod
    def _diagnose_from_gaps(spec: ResearchSpec, gaps: list[CollectionGap]) -> Diagnosis:
        gap_ids = {gap.variable_id for gap in gaps}
        if "treatment_response" in gap_ids or "outcome" in gap_ids:
            return "outcome_mismatch"
        if any(item.endswith("_mutation") or item.endswith("_variants") or item == "mutation" for item in gap_ids):
            return "missing_same_cohort_exposure"
        if {"sample_type", "age", "stage", "sample_source", "sample_timepoint", "subtype"} & gap_ids:
            return "missing_clinical_covariates"
        if "evidence" in gap_ids or "knowledge_evidence" in spec.required_data_types:
            return "missing_evidence"
        return "residual_gaps"

    def _candidates(self, spec: ResearchSpec, diagnosis: Diagnosis) -> list[MethodStrategy]:
        ranked = [
            strategy
            for strategy in STRATEGIES
            if diagnosis in strategy.diagnoses and strategy.applicable(spec)
        ]
        if diagnosis == "missing_same_cohort_exposure":
            dual = [item for item in ranked if item.primary_cohort and item.has_response and item.has_mutation]
            web_discovery = [item for item in ranked if item.strategy_id.startswith("discover.")]
            ranked = [*dual, *web_discovery]
        if diagnosis == "outcome_mismatch":
            ranked = [item for item in ranked if item.has_response or not item.primary_cohort]
            ranked.sort(key=lambda item: (0 if item.has_response and item.primary_cohort else 1, item.priority))
        else:
            ranked.sort(key=lambda item: item.priority)
        return ranked

    @staticmethod
    def call_key(call: dict[str, Any]) -> str:
        import json

        return f"{call.get('name')}:{json.dumps(call.get('arguments') or {}, sort_keys=True, ensure_ascii=False)}"
