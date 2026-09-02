from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from backend.app.agent.accession_harvest import catalog_query, literature_query, needs_clinical_outcome
from backend.app.agent.models import AgentGoalStatus, CollectionGap, CollectionSearchAction
from backend.app.agent.search_planner import geo_search_applicable, question_search_terms
from backend.app.agent.study_design import covariate_fields_in_pack, protocol_covariates
from backend.app.models import ResearchSpec
from backend.app.oncology import (
    default_cbioportal_study,
    default_gdc_project,
    default_genes,
    is_breast_cancer,
    resolve_cancer_profile,
)


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
    return is_breast_cancer(spec.disease) and geo_search_applicable(spec)


def _genes(spec: ResearchSpec) -> list[str]:
    return spec.genes or default_genes(spec.disease)


def _breast_only(spec: ResearchSpec) -> bool:
    return is_breast_cancer(spec.disease)


def _configured_non_breast(spec: ResearchSpec) -> bool:
    return resolve_cancer_profile(spec.disease) is not None and not is_breast_cancer(spec.disease)


STRATEGIES: tuple[MethodStrategy, ...] = (
    MethodStrategy(
        strategy_id="cohort.cbio.alpelisib",
        label="检索同患者 PIK3CA 突变与治疗响应队列（cBioPortal breast_alpelisib_2020）",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=1,
        diagnoses=frozenset(
            {
                "outcome_mismatch",
                "no_patient_table",
                "missing_same_cohort_exposure",
            }
        ),
        primary_cohort=True,
        has_response=True,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": "breast_alpelisib_2020",
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
        applicable=lambda spec: _breast_only(spec)
        and "PIK3CA" in {gene.upper() for gene in spec.genes}
        and (
            "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types
        ),
    ),
    MethodStrategy(
        strategy_id="cohort.cbio.mskcc2019",
        label="检索同患者 PIK3CA 突变与治疗响应队列（cBioPortal brca_mskcc_2019）",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=2,
        diagnoses=frozenset(
            {
                "outcome_mismatch",
                "no_patient_table",
                "missing_same_cohort_exposure",
            }
        ),
        primary_cohort=True,
        has_response=True,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": "brca_mskcc_2019",
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
        applicable=lambda spec: _breast_only(spec)
        and "PIK3CA" in {gene.upper() for gene in spec.genes}
        and (
            "treatment_response" in spec.outcomes or "treatment_response" in spec.required_data_types
        ),
    ),
    MethodStrategy(
        strategy_id="cohort.cbio.cancer_default",
        label="检索当前癌种的 cBioPortal 临床与分子队列",
        tool_name="search_cbioportal",
        source_name="cBioPortal",
        priority=3,
        diagnoses=frozenset(
            {"no_patient_table", "missing_same_cohort_exposure", "missing_clinical_covariates", "residual_gaps"}
        ),
        primary_cohort=True,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "study_id": default_cbioportal_study(spec.disease),
            "gene_symbols": _genes(spec),
            "max_records": max_records,
        },
        applicable=_configured_non_breast,
    ),
    MethodStrategy(
        strategy_id="cohort.geo.gse76360",
        label="切换独立队列 GSE76360（HER2 阳性术前曲妥珠单抗响应）",
        tool_name="search_geo",
        source_name="NCBI GEO",
        priority=2,
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
        applicable=_breast_only,
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
        applicable=_breast_only,
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
        applicable=_breast_only,
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
        applicable=_breast_only,
    ),
    MethodStrategy(
        strategy_id="files.gdc.cancer_default",
        label="检索当前癌种的 GDC/TCGA 临床补充与突变文件",
        tool_name="search_gdc",
        source_name="GDC / TCGA",
        priority=7,
        diagnoses=frozenset({"missing_clinical_covariates", "missing_same_cohort_exposure", "residual_gaps"}),
        primary_cohort=False,
        has_response=False,
        has_mutation=True,
        argument_builder=lambda spec, max_records: {
            "project_id": default_gdc_project(spec.disease),
            "data_types": ["Clinical Supplement", "Masked Somatic Mutation"],
            "max_files": 20,
        },
        applicable=_configured_non_breast,
    ),
    MethodStrategy(
        strategy_id="context.trials",
        label="补充 ClinicalTrials.gov 方案与响应定义（解释层）",
        tool_name="search_trials",
        source_name="ClinicalTrials.gov",
        priority=8,
        diagnoses=frozenset({"missing_evidence", "outcome_mismatch", "residual_gaps", "no_patient_table"}),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "condition": spec.disease,
            "query_terms": " ".join(spec.drugs + spec.genes),
            "nct_id": "NCT01042379"
            if is_breast_cancer(spec.disease)
            and any(token in spec.research_goal for token in ("试验", "NCT", "登记", "I-SPY"))
            else None,
            "max_trials": 10,
        },
    ),
    MethodStrategy(
        strategy_id="context.depmap",
        label="检索 DepMap 细胞系药敏（AUC/IC50，不得当患者疗效）",
        tool_name="search_depmap",
        source_name="DepMap",
        priority=8,
        diagnoses=frozenset({"outcome_mismatch", "residual_gaps", "no_patient_table"}),
        primary_cohort=False,
        has_response=True,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "query": f"{spec.disease} cell line AUC IC50",
            "drug": spec.drugs[0] if spec.drugs else None,
            "max_records": min(max_records, 80),
        },
        applicable=lambda spec: any(
            token in spec.research_goal.casefold() for token in ("细胞系", "auc", "ic50", "depmap", "药敏")
        ),
    ),
    MethodStrategy(
        strategy_id="context.paper_extract",
        label="从开放论文提取表格与图注（不从图像素读数）",
        tool_name="extract_paper_assets",
        source_name="Europe PMC",
        priority=9,
        diagnoses=frozenset(
            {"missing_evidence", "residual_gaps", "missing_same_cohort_exposure", "no_patient_table"}
        ),
        primary_cohort=False,
        has_response=False,
        has_mutation=False,
        argument_builder=lambda spec, max_records: {
            "query": " ".join([spec.disease, *spec.genes[:3], "table"]).strip(),
            "max_records": 5,
        },
        applicable=lambda spec: "evidence" in (spec.required_data_types or [])
        or any(token in spec.research_goal for token in ("文献", "论文", "图注", "表格", "PMC")),
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
            "query": catalog_query(spec, extra_terms=question_search_terms(spec.research_goal, spec)),
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
            "query": literature_query(spec, extra_terms=question_search_terms(spec.research_goal, spec)),
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
        source_datasets: list[Any] | None = None,
    ) -> list[AgentGoalStatus]:
        row_count = int(getattr(dataset, "row_count", 0) or 0)
        target_match = bool(getattr(readiness, "target_match", False))
        target_match_rate = getattr(readiness, "target_match_rate", None)
        gene_coverage = getattr(readiness, "requested_variable_coverage_rate", None)
        cohort_rows = int(getattr(cohort, "final_row_count", row_count) or 0)
        needs_response = needs_clinical_outcome(spec)
        needs_genes = bool(spec.genes)

        patient_table = row_count >= 30
        if not needs_response:
            matched_outcome = True
        elif target_match_rate is not None:
            matched_outcome = target_match_rate >= 0.45
        else:
            matched_outcome = target_match
        analysis_cohort = cohort_rows > 0 if matched_outcome and row_count else False
        if not needs_response:
            analysis_cohort = row_count > 0
        same_cohort_exposure = True
        if needs_genes:
            same_cohort_exposure = gene_coverage is not None and gene_coverage >= 0.75
        pack_fields = covariate_fields_in_pack(dataset, source_datasets)
        planned_covariates = protocol_covariates(spec)
        covariate_pack = all(field in pack_fields for field, _label in planned_covariates)

        if target_match_rate is not None:
            outcome_evidence = f"结局匹配率 {target_match_rate:.0%}"
        elif target_match:
            outcome_evidence = "治疗响应已匹配"
        else:
            outcome_evidence = "结局尚未匹配"
        gene_evidence = (
            f"基因变量覆盖 {gene_coverage:.0%}"
            if gene_coverage is not None and same_cohort_exposure
            else "当前队列缺少同患者分子检测，禁止跨库贴字段"
            if needs_genes
            else "本题未要求基因暴露"
        )

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
                evidence=outcome_evidence,
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
                evidence=gene_evidence,
            ),
            AgentGoalStatus(
                goal_id="covariate_pack",
                label="临床协变量已在多源数据包中解析（不跨患者合并）",
                required=False,
                met=covariate_pack,
                evidence=(
                    f"已解析 {', '.join(pack_fields)}"
                    if pack_fields
                    else "主分析表未发布本题所需临床协变量，待补独立临床来源表"
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
        source_datasets: list[Any] | None = None,
    ) -> Diagnosis:
        if dataset is None and gaps:
            return self._diagnose_from_gaps(spec, gaps)
        goals = goals or self.evaluate_goals(
            spec=spec,
            dataset=dataset,
            readiness=readiness,
            source_datasets=source_datasets,
        )
        required_met = all(not goal.required or goal.met for goal in goals)
        pack_fields = covariate_fields_in_pack(dataset, source_datasets)
        planned_covariates = protocol_covariates(spec)
        covariate_ids = {field for field, _label in planned_covariates}
        if required_met:
            if not all(field in pack_fields for field in covariate_ids) and (
                any(gap.variable_id in covariate_ids for gap in gaps) or not pack_fields
            ):
                return "missing_clinical_covariates"
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
        limit: int = 3,
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
        follow_up_limit: int = 3,
        source_datasets: list[Any] | None = None,
    ) -> LoopDecision:
        goals = self.evaluate_goals(
            spec=spec,
            dataset=dataset,
            readiness=readiness,
            cohort=cohort,
            source_datasets=source_datasets,
        )
        diagnosis = self.diagnose(
            spec=spec,
            dataset=dataset,
            readiness=readiness,
            gaps=gaps,
            goals=goals,
            source_datasets=source_datasets,
        )
        primary_open = [goal for goal in goals if goal.required and goal.goal_id != "same_cohort_exposure" and not goal.met]
        secondary_open = [goal for goal in goals if goal.required and goal.goal_id == "same_cohort_exposure" and not goal.met]
        actions = self.next_actions(
            spec=spec,
            diagnosis=diagnosis,
            attempted_calls=attempted_calls,
            max_records=max_records,
            limit=follow_up_limit,
        )
        required_met = not primary_open and not secondary_open
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
        if required_met and diagnosis == "missing_clinical_covariates":
            if actions:
                return LoopDecision(
                    action="continue",
                    diagnosis=diagnosis,
                    quality_gate="PARTIAL",
                    note="主分析变量已齐；继续检索独立临床来源表补齐本题所需协变量，不把跨研究字段贴到当前分析患者。",
                    goals=goals,
                    actions=actions,
                    next_strategy_ids=[item.strategy_id for item in actions if item.strategy_id],
                )
            return LoopDecision(
                action="stop_pass",
                diagnosis="all_met",
                quality_gate="PASS",
                note="主分析变量已齐；公开临床协变量来源已检索完毕，未跨患者合并。",
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
        goal = spec.research_goal or ""
        folded = goal.casefold()
        if any(token in folded for token in ("细胞系", "auc", "ic50", "depmap", "药敏", "ccle")):
            ranked = [item for item in ranked if item.tool_name == "search_depmap" or not item.primary_cohort]
            ranked.sort(key=lambda item: (0 if item.tool_name == "search_depmap" else item.priority))
            return ranked
        if any(token in goal for token in ("试验", "NCT", "登记", "I-SPY")):
            ranked = [item for item in ranked if item.tool_name == "search_trials" or item.strategy_id.startswith("discover.")]
            ranked.sort(key=lambda item: (0 if item.tool_name == "search_trials" else item.priority))
            return ranked
        if "evidence" in (spec.required_data_types or []) or any(
            token in goal for token in ("文献", "论文", "图注", "表格", "PMC")
        ):
            papers = [item for item in ranked if item.tool_name == "extract_paper_assets"]
            rest = [item for item in ranked if item.tool_name != "extract_paper_assets"]
            rest.sort(key=lambda item: item.priority)
            if papers:
                return [*papers, *rest]
        if diagnosis == "missing_same_cohort_exposure":
            dual = [item for item in ranked if item.primary_cohort and item.has_response and item.has_mutation]
            web_discovery = [item for item in ranked if item.strategy_id.startswith("discover.")]
            ranked = [*dual, *web_discovery]
        if diagnosis == "outcome_mismatch":
            ranked = [item for item in ranked if item.has_response or not item.primary_cohort]
            dual = [item for item in ranked if item.primary_cohort and item.has_response and item.has_mutation]
            geo = [item for item in ranked if item.tool_name == "search_geo" and item.has_response]
            seen = {id(item) for item in [*dual, *geo]}
            other = [item for item in ranked if id(item) not in seen]
            ranked = [*dual[:1], *geo, *dual[1:], *other]
        else:
            ranked.sort(key=lambda item: item.priority)
        return ranked

    @staticmethod
    def call_key(call: dict[str, Any]) -> str:
        import json

        return f"{call.get('name')}:{json.dumps(call.get('arguments') or {}, sort_keys=True, ensure_ascii=False)}"
