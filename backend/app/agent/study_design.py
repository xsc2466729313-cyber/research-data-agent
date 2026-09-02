from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from backend.app.agent.accession_harvest import (
    asks_copy_number,
    asks_pcr,
    asks_sample_timepoint,
    asks_survival,
    asks_treatment,
    is_tnbc_question,
    needs_clinical_outcome,
)
from backend.app.agent.match_scoring import variable_fill_rate
from backend.app.agent.models import (
    CohortConstructionReport,
    CohortFilterStep,
    DataSourceRecommendation,
    ResearchBrief,
    StudyDesignReport,
    StudyVariable,
)
from backend.app.models import CandidateSource, ResearchSpec, SourceItem
from backend.app.oncology import disease_match_terms, is_breast_cancer


SOURCE_CATALOG: dict[str, tuple[str, list[str]]] = {
    "GDC / TCGA": ("患者临床、表达、突变与拷贝数", ["clinical", "mutation", "expression"]),
    "GTEx": ("健康人体组织与正常对照表达", ["normal_tissue", "expression"]),
    "NCBI GEO": ("外部表达、治疗响应与验证队列", ["expression", "treatment_response", "survival"]),
    "cBioPortal": ("肿瘤临床与分子整合队列", ["clinical", "mutation", "expression", "survival"]),
    "ClinicalTrials.gov": ("治疗方案、试验设计与临床结局", ["clinical_trial", "treatment_response"]),
    "GDSC": ("细胞系药物敏感性 AUC / IC50", ["preclinical_cell_line"]),
    "DepMap": ("细胞系依赖性与药物敏感性", ["preclinical_cell_line"]),
    "CIViC": ("变异、药物、疾病与证据关系", ["knowledge_evidence"]),
    "OncoKB": ("肿瘤变异临床意义知识", ["knowledge_evidence"]),
}

SUPPORTED_DATABASES = {
    "GDC",
    "NCBI GEO",
    "cBioPortal",
    "ClinicalTrials.gov",
    "CIViC",
}

# Aliases used both to mark a study variable available and to compute gap coverage.
VARIABLE_FIELD_ALIASES: dict[str, list[str]] = {
    "disease": ["disease", "patient_status", "cancer_type", "diagnosis"],
    "subtype": ["subtype", "derived_ihc_subtype", "her2_status"],
    "treatment": ["treatment", "drug", "chemotherapy", "therapy", "neoadjuvant_treatment"],
    "outcome": [
        "treatment_response",
        "pcr",
        "pcr_binary",
        "response",
        "response_at_surgery",
        "pathological_complete_response",
        "pathologic_complete_response",
        "trastuzumab_response",
    ],
    "pcr": ["pcr", "pcr_binary", "pathological_complete_response", "pathologic_complete_response"],
    "survival": ["os_status", "os_months", "dfs_status", "dfs_months", "rfs_status", "rfs_months"],
    "intclust": ["intclust", "integrative_cluster", "int_clust"],
    "patient_id": ["patient_id"],
    "sample_id": ["sample_id"],
    "sample_type": ["sample_type", "sample_type_detailed", "tissue_type", "specimen_type"],
    "sample_timepoint": ["sample_timepoint", "timepoint", "time_point", "collection_timepoint"],
    "sample_source": [
        "sample_source",
        "tissue_source_site",
        "tissue_source",
        "specimen_source",
        "sample_origin",
        "organ",
        "tissue",
    ],
    "age": ["age"],
    "stage": ["stage"],
    "er_status": ["er_status"],
    "pr_status": ["pr_status"],
    "sex": ["sex"],
    "endocrine_therapy": ["endocrine_therapy", "hormone_therapy"],
    "measurable_disease": ["measurable_disease"],
    "weeks_on_study": ["weeks_on_study"],
}

# Protocol-suggested breast-cancer covariates. Never copied across studies.
PROTOCOL_COVARIATES: list[tuple[str, str]] = [
    ("age", "年龄"),
    ("stage", "分期"),
    ("er_status", "ER 状态"),
    ("pr_status", "PR 状态"),
]


def protocol_covariates(spec: ResearchSpec) -> list[tuple[str, str]]:
    if is_breast_cancer(spec.disease):
        return PROTOCOL_COVARIATES
    return [(field, label) for field, label in PROTOCOL_COVARIATES if field in {"age", "stage"}]

# Same-cohort clinical fields that can stand in as covariates when published.
SAME_COHORT_COVARIATES: list[tuple[str, str]] = [
    ("sex", "性别"),
    ("endocrine_therapy", "内分泌治疗"),
    ("measurable_disease", "可测量病灶"),
    ("weeks_on_study", "在研周数"),
]


def dataset_has_variable(dataset: Any, field: str) -> bool:
    aliases = VARIABLE_FIELD_ALIASES.get(field, [field])
    rows = list(getattr(dataset, "rows", []) or [])
    if not rows:
        columns = {
            column.name if hasattr(column, "name") else str(column)
            for column in getattr(dataset, "columns", []) or []
        }
        return any(alias in columns for alias in aliases)
    return any(
        StudyDesignBuilder._has_value(row.get(alias))
        for alias in aliases
        for row in rows
    )


def covariate_fields_in_pack(primary: Any, companions: list[Any] | None = None) -> dict[str, str]:
    found: dict[str, str] = {}
    for dataset in [primary, *(companions or [])]:
        if dataset is None:
            continue
        name = str(getattr(dataset, "name", "") or "独立来源表")
        for field, _label in PROTOCOL_COVARIATES:
            if field in found:
                continue
            if dataset_has_variable(dataset, field):
                found[field] = name
    return found


class StudyDesignBuilder:
    """Create auditable study-design and cohort diagnostics from observed task data."""

    def build(
        self,
        spec: ResearchSpec,
        dataset: Any,
        readiness: Any,
        candidates: list[CandidateSource],
        source_items: list[SourceItem],
        execution_mode: str = "live",
        source_datasets: list[Any] | None = None,
        brief: ResearchBrief | None = None,
    ) -> tuple[StudyDesignReport, CohortConstructionReport]:
        columns = {
            column.name if hasattr(column, "name") else str(column.get("name"))
            for column in dataset.columns
        }
        design = self._build_design(spec, dataset, columns, candidates, source_items, source_datasets, brief)
        cohort = self._build_cohort(spec, dataset, readiness, design, columns, execution_mode)
        design = design.model_copy(
            update={"variable_coverage_rate": cohort.variable_coverage_rate}
        )
        return design, cohort

    def _build_design(
        self,
        spec: ResearchSpec,
        dataset: Any,
        columns: set[str],
        candidates: list[CandidateSource],
        source_items: list[SourceItem],
        source_datasets: list[Any] | None = None,
        brief: ResearchBrief | None = None,
    ) -> StudyDesignReport:
        type_id, type_label = (brief.research_type_id, brief.research_type) if brief else self._research_type(spec)
        population = self._population(spec)
        exposure = self._exposure(spec)
        outcome = self._outcome(spec, brief)
        covariates = self._covariates(spec, columns, dataset, source_datasets)
        variables = self._required_variables(spec, columns, type_id, dataset, source_datasets, brief)
        selected_databases = {
            self._canonical_database(item.source_name)
            for item in source_items
        } | {
            self._canonical_database(item.source_database)
            for item in candidates
        }
        recommendations = []
        for database, (purpose, domains) in SOURCE_CATALOG.items():
            canonical = self._canonical_database(database)
            selected = canonical in selected_databases
            supported = canonical in SUPPORTED_DATABASES
            if selected:
                availability = "本次已登记"
                note = "本次任务已有真实来源或候选记录；具体可用字段仍以原始数据审计为准。"
            elif supported:
                availability = "已接入，可按任务调用"
                note = "系统已有受控 Adapter，但本次任务未选择或未成功返回该来源。"
            else:
                availability = "待接入"
                note = "方案要求纳入该数据库；当前前端只展示规划，不把它当作已获取数据。"
            recommendations.append(
                DataSourceRecommendation(
                    database=database,
                    purpose=purpose,
                    data_domains=domains,
                    availability=availability,
                    selected=selected,
                    source_ids=[
                        item.source_id
                        for item in source_items
                        if self._canonical_database(item.source_name) == canonical
                    ],
                    note=note,
                )
            )
        limitations = [
            "研究设计字段来自科研问题解析与确定性规则；正式统计分析前仍需研究者冻结 Evaluation Contract。",
            "当前未接入的 GTEx、GDSC、DepMap、OncoKB 只作为数据源规划，不生成虚假记录。",
        ]
        return StudyDesignReport(
            status="已生成" if spec.research_goal else "信息不足",
            generation_note=(
                "研究设计规则已生成；当前为仅规划模式，未执行真实数据筛选。"
                if dataset.row_count == 0
                else "研究设计规则已生成，并基于当前任务返回的数据字段计算覆盖率。"
            ),
            research_type=type_label,
            research_type_id=type_id,
            population=population,
            exposure=exposure,
            outcome=outcome,
            covariates=covariates,
            analysis_unit=dataset.unit_of_analysis,
            model_expression=self._model_expression(type_id, exposure, outcome),
            cohort_rules=self._cohort_rules(spec, brief),
            required_variables=variables,
            data_source_recommendations=recommendations,
            limitations=limitations,
        )

    def _build_cohort(
        self,
        spec: ResearchSpec,
        dataset: Any,
        readiness: Any,
        design: StudyDesignReport,
        columns: set[str],
        execution_mode: str,
    ) -> CohortConstructionReport:
        rows = [dict(row) for row in dataset.rows]
        steps: list[CohortFilterStep] = []
        current = rows
        disease_terms = disease_match_terms(spec.disease)
        current = self._step(
            steps,
            current,
            "include_disease",
            "目标疾病",
            "纳入",
            f"disease 应与 {spec.disease} 一致；字段缺失时保留记录并进入复核。",
            lambda row: self._contains(row.get("disease"), *disease_terms),
            active=any(self._has_value(row.get("disease")) for row in current),
        )
        current = self._step(
            steps,
            current,
            "include_primary_tumor",
            "原发肿瘤",
            "纳入",
            "sample_type 为 primary/原发肿瘤；没有该字段时不自动排除。",
            lambda row: self._contains(row.get("sample_type"), "primary", "原发"),
            active=any(self._has_value(row.get("sample_type")) for row in current),
        )
        if "HER2" in (spec.subtype or "").upper():
            current = self._step(
                steps,
                current,
                "include_her2_status",
                "HER2 状态可用",
                "纳入",
                "需要 her2_status 原始字段；IHC 2+ 不自动转为阳性。",
                lambda row: self._has_value(row.get("her2_status")),
                active="her2_status" in columns,
            )
        for gene in spec.genes:
            mutation_field = f"{gene.lower()}_mutation"
            current = self._step(
                steps,
                current,
                f"include_{gene.lower()}_mutation",
                f"{gene} 突变信息",
                "纳入",
                f"需要 {mutation_field} 或等价突变字段；当前不跨来源硬拼患者。",
                lambda row, field=mutation_field: self._has_value(row.get(field)),
                active=mutation_field in columns,
            )
        target = readiness.target_column or dataset.target_column
        current = self._step(
            steps,
            current,
            "include_outcome",
            "研究结局可用",
            "纳入",
            "结局字段必须与研究问题同域，不能用 OS 替代治疗响应。",
            lambda row: self._has_value(row.get(target)) if target else False,
            active=bool(target and target in columns),
        )
        current = self._step(
            steps,
            current,
            "exclude_normal_tissue",
            "排除正常组织",
            "排除",
            "若有 sample_type，则排除 normal/正常组织；没有字段时保留并复核。",
            lambda row: not self._contains(row.get("sample_type"), "normal", "正常"),
            active=any(self._has_value(row.get("sample_type")) for row in current),
        )
        current = self._step(
            steps,
            current,
            "exclude_duplicates",
            "排除重复记录",
            "排除",
            "仅对完全重复的患者/样本行去重，不把同一患者的合法多样本误删。",
            self._unique_row_predicate(),
            active=bool(current),
        )
        required_variables = [
            variable
            for variable in design.required_variables
            if variable.required and variable.available
        ]
        current = self._step(
            steps,
            current,
            "exclude_missing_key_variables",
            "排除关键变量缺失",
            "排除",
            "只在必需字段真实存在时执行；按已匹配字段取值，不用变量编号冒充列名。",
            lambda row: all(self._row_has_variable(row, variable) for variable in required_variables),
            active=bool(required_variables),
        )
        current = self._step(
            steps,
            current,
            "exclude_low_quality_samples",
            "排除低质量样本",
            "排除",
            "需要 quality/quality_score 等质量字段；当前没有质量字段时不自动判定。",
            lambda row: not self._contains(row.get("quality"), "low", "fail", "低", "不合格"),
            active=any(self._has_value(row.get("quality")) for row in current),
        )
        final_rows = current
        notes = [
            "每一步计数来自当前任务实际返回的患者/样本行；未提供字段的规则显示为待复核。",
            "患者级关联 F1 未加载 Gold Set，因此保持未评测，不用内部诊断分替代。",
        ]
        if readiness.repeated_patient_count:
            notes.append("同一患者对应多个样本，分析时应按患者分组切分，避免信息泄漏。")
        if any(row.get("response_domain") == "preclinical_cell_line" for row in final_rows):
            notes.append("检测到细胞系药敏域，必须与患者 clinical response 分层分析。")
        gate = "PASS" if readiness.analysis_ready else "REVIEW"
        is_plan = execution_mode == "plan_only"
        return CohortConstructionReport(
            status="已生成规则" if is_plan else ("已构建" if rows else "待执行"),
            execution_mode=execution_mode,
            rule_status="已生成" if is_plan else ("已执行" if rows else "待执行"),
            has_observed_rows=bool(rows),
            not_run_reason=(
                "仅规划模式未访问真实数据，筛选计数和最终队列暂不执行。"
                if is_plan
                else None
            ),
            source_row_count=len(rows),
            final_row_count=len(final_rows),
            patient_count=len({row.get("patient_id") for row in final_rows if self._has_value(row.get("patient_id"))}),
            sample_count=len({row.get("sample_id") for row in final_rows if self._has_value(row.get("sample_id"))}),
            inclusion_criteria=[
                spec.disease,
                "Primary Tumor",
                "HER2 status available" if "HER2" in (spec.subtype or "").upper() else "研究对象字段可识别",
                "Mutation available" if spec.genes else "研究暴露字段可识别",
                "Outcome available",
            ],
            exclusion_criteria=[
                "Normal tissue",
                "Non-target disease",
                "Missing key variables",
                "Duplicate patients or samples",
                "Low-quality samples",
            ],
            filter_steps=steps,
            variable_coverage_rate=(
                (
                    sum((variable.coverage_rate or 0.0) for variable in design.required_variables if variable.required)
                    / sum(1 for variable in design.required_variables if variable.required)
                )
                if any(variable.required for variable in design.required_variables)
                else None
            ),
            patient_linkage_f1=None,
            response_domains=sorted(
                {
                    str(row.get("response_domain"))
                    for row in final_rows
                    if self._has_value(row.get("response_domain"))
                }
            ),
            quality_gate=gate,
            publish_allowed=gate == "PASS",
            notes=notes,
        )

    @staticmethod
    def _required_variables(
        spec: ResearchSpec,
        columns: set[str],
        research_type: str,
        dataset: Any = None,
        source_datasets: list[Any] | None = None,
        brief: ResearchBrief | None = None,
    ) -> list[StudyVariable]:
        variables: list[tuple[str, str, str, bool, list[str]]] = [
            ("disease", "疾病", "人群", True, VARIABLE_FIELD_ALIASES["disease"]),
        ]
        if spec.subtype:
            if is_tnbc_question(spec):
                subtype_aliases = ["subtype", "derived_ihc_subtype"]
            else:
                subtype_aliases = VARIABLE_FIELD_ALIASES["subtype"]
            variables.append(("subtype", "疾病亚型", "人群", True, subtype_aliases))
        if spec.genes:
            subtype = (spec.subtype or "").casefold()
            her2_positive = "her2-positive" in subtype and "her2-negative" not in subtype
            goal_upper = spec.research_goal.upper()
            any_gene_mentioned = any(item.upper() in goal_upper for item in spec.genes)
            want_cna = asks_copy_number(spec)
            for gene in spec.genes:
                if gene.upper() == "ERBB2" and her2_positive and "ERBB2" not in goal_upper:
                    continue
                field = f"{gene.lower()}_mutation"
                required = gene.upper() in goal_upper if any_gene_mentioned else True
                gene_aliases = [field, f"{gene.lower()}_variants", "gene", "mutation_status"]
                variables.append((field, f"{gene} 突变", "暴露", required, gene_aliases))
                cna_field = f"{gene.lower()}_cna"
                if want_cna or cna_field in columns or f"{gene.lower()}_altered" in columns:
                    variables.append(
                        (
                            cna_field,
                            f"{gene} 拷贝数",
                            "暴露",
                            want_cna and required,
                            [cna_field],
                        )
                    )
        if asks_treatment(spec):
            variables.append(("treatment", "治疗方案", "暴露", True, VARIABLE_FIELD_ALIASES["treatment"]))
        elif needs_clinical_outcome(spec) or any(
            alias in columns for alias in VARIABLE_FIELD_ALIASES["treatment"]
        ):
            variables.append(("treatment", "治疗方案", "暴露", False, VARIABLE_FIELD_ALIASES["treatment"]))
        if needs_clinical_outcome(spec):
            if asks_pcr(spec):
                outcome_fields = VARIABLE_FIELD_ALIASES["pcr"] + VARIABLE_FIELD_ALIASES["outcome"]
            elif asks_survival(spec) or "survival" in spec.outcomes:
                outcome_fields = VARIABLE_FIELD_ALIASES["survival"]
            else:
                outcome_fields = VARIABLE_FIELD_ALIASES["outcome"]
            variables.append(("outcome", "研究结局", "结局", True, list(dict.fromkeys(outcome_fields))))
        elif "expression" in spec.required_data_types:
            variables.append(("outcome", "表达量", "结局", False, ["expression"]))
        for field, label in protocol_covariates(spec):
            variables.append((field, label, "协变量", False, VARIABLE_FIELD_ALIASES.get(field, [field])))
        rows_preview = list(getattr(dataset, "rows", []) or [])
        for field, label in SAME_COHORT_COVARIATES:
            aliases = VARIABLE_FIELD_ALIASES.get(field, [field])
            present = any(alias in columns for alias in aliases) and (
                not rows_preview
                or any(
                    StudyDesignBuilder._has_value(row.get(alias))
                    for alias in aliases
                    for row in rows_preview
                )
            )
            if present:
                variables.append((field, label, "协变量", False, aliases))
        variables.append(("patient_id", "患者编号", "分析单位", True, VARIABLE_FIELD_ALIASES["patient_id"]))
        variables.append(("sample_id", "样本编号", "分析单位", True, VARIABLE_FIELD_ALIASES["sample_id"]))
        variables.append(
            (
                "sample_type",
                "样本类型",
                "样本信息",
                True,
                VARIABLE_FIELD_ALIASES["sample_type"],
            )
        )
        timepoint_present = any(alias in columns for alias in VARIABLE_FIELD_ALIASES["sample_timepoint"])
        if asks_sample_timepoint(spec) or timepoint_present or needs_clinical_outcome(spec):
            variables.append(
                (
                    "sample_timepoint",
                    "样本时间点",
                    "样本信息",
                    asks_sample_timepoint(spec),
                    VARIABLE_FIELD_ALIASES["sample_timepoint"],
                )
            )
        variables.append(
            (
                "sample_source",
                "样本来源",
                "样本信息",
                False,
                VARIABLE_FIELD_ALIASES["sample_source"],
            )
        )
        brief_by_id = {field.field_id: field for field in (brief.fields if brief else [])}
        existing_ids = {item[0] for item in variables}
        if brief:
            for field in brief.fields:
                if field.field_id in existing_ids:
                    continue
                role = "暴露" if any(token in field.field_id for token in ("mutation", "variant", "cna")) else (
                    "人群" if field.field_id in {"subtype", "er_status", "her2_status", "disease"} else "协变量"
                )
                variables.append(
                    (
                        field.field_id,
                        field.label,
                        role,
                        field.priority == "primary",
                        field.aliases or [field.field_id],
                    )
                )
                existing_ids.add(field.field_id)
        result: list[StudyVariable] = []
        rows = list(getattr(dataset, "rows", []) or [])
        pack_sources = covariate_fields_in_pack(dataset, source_datasets)
        for variable_id, label, role, required, aliases in variables:
            brief_field = brief_by_id.get(variable_id)
            if brief_field is not None:
                if brief_field.priority == "primary":
                    required = True
                elif brief_field.priority == "secondary":
                    required = False
                if brief_field.aliases:
                    aliases = list(dict.fromkeys([*brief_field.aliases, *aliases]))
            priority = (
                brief_field.priority
                if brief_field is not None
                else ("primary" if required else ("important" if role in {"暴露", "结局", "人群", "分析单位"} else "secondary"))
            )
            matched = [field for field in aliases if field in columns]
            coverage = variable_fill_rate(rows, matched or aliases, matched=bool(matched))
            if rows:
                available = coverage > 0
            else:
                available = bool(matched)
                coverage = 1.0 if matched else 0.0
            companions = []
            if variable_id in pack_sources and not available:
                companions = [pack_sources[variable_id]]
            result.append(
                StudyVariable(
                    variable_id=variable_id,
                    label=label,
                    role=role,
                    required=required,
                    available=available,
                    priority=priority,
                    coverage_rate=coverage,
                    matched_fields=matched,
                    companion_sources=companions,
                    note=StudyDesignBuilder._variable_note(
                        available=available,
                        required=required,
                        role=role,
                        companion_sources=companions,
                        coverage_rate=coverage,
                    ),
                )
            )
        return result

    @staticmethod
    def _research_type(spec: ResearchSpec) -> tuple[str, str]:
        goal = spec.research_goal.casefold()
        if "survival" in spec.outcomes or "生存" in goal:
            return "survival_analysis", "预后/生存分析"
        if "expression" in spec.required_data_types and any(term in goal for term in ("差异表达", "tumor normal", "tumor+normal", "正常组织")):
            return "differential_expression", "肿瘤-正常差异表达"
        if any(term in goal for term in ("药物敏感", "auc", "ic50", "细胞系")):
            return "drug_sensitivity", "药物敏感性分析"
        if "treatment_response" in spec.outcomes or any(term in goal for term in ("响应", "疗效", "pcr", "缓解")):
            return "response_analysis", "治疗响应分析"
        if any(term in goal for term in ("可重复", "是否一致", "reproducib")):
            return "cross_cohort_reproducibility", "跨队列可重复性"
        return "molecular_association", "分子关联分析"

    @staticmethod
    def _population(spec: ResearchSpec) -> str:
        subtype = f"、{spec.subtype}" if spec.subtype else ""
        return f"{spec.disease}{subtype}患者/样本"

    @staticmethod
    def _exposure(spec: ResearchSpec) -> str:
        pieces = []
        if spec.genes:
            gene_label = "、".join(spec.genes)
            goal = (spec.research_goal or "").casefold()
            mentions_mutation = "突变" in spec.research_goal or "mutation" in goal
            if asks_copy_number(spec) and mentions_mutation:
                pieces.append(gene_label + " 突变或拷贝数")
            elif asks_copy_number(spec):
                pieces.append(gene_label + " 拷贝数")
            else:
                pieces.append(gene_label + " 突变状态")
        if spec.drugs:
            pieces.append("、".join(spec.drugs) + " 治疗")
        elif asks_treatment(spec):
            pieces.append("研究问题中的治疗暴露")
        return "；".join(pieces) or "待从科研问题中进一步冻结"

    @staticmethod
    def _outcome(spec: ResearchSpec, brief: ResearchBrief | None = None) -> str:
        if brief and brief.research_type_id == "cross_cohort_reproducibility":
            return "跨队列关联方向是否一致（非临床终点）"
        if asks_pcr(spec):
            return "病理完全缓解（pCR）"
        if asks_survival(spec) or "survival" in spec.outcomes:
            return "生存结局"
        if spec.outcomes:
            return "、".join(spec.outcomes)
        if needs_clinical_outcome(spec):
            return "临床结局"
        return "本题不强制临床结局"

    @staticmethod
    def _covariates(
        spec: ResearchSpec,
        columns: set[str] | None = None,
        dataset: Any = None,
        source_datasets: list[Any] | None = None,
    ) -> list[str]:
        columns = columns or set()
        rows = list(getattr(dataset, "rows", []) or [])
        labels: list[str] = []
        seen: set[str] = set()
        planned_covariates = protocol_covariates(spec)
        for field, label in [*SAME_COHORT_COVARIATES, *planned_covariates]:
            if label in seen:
                continue
            aliases = VARIABLE_FIELD_ALIASES.get(field, [field])
            present = any(alias in columns for alias in aliases) and (
                not rows
                or any(
                    StudyDesignBuilder._has_value(row.get(alias))
                    for alias in aliases
                    for row in rows
                )
            )
            if present:
                labels.append(label)
                seen.add(label)
        pack = covariate_fields_in_pack(dataset, source_datasets)
        for field, label in planned_covariates:
            if label in seen:
                continue
            if field in pack:
                labels.append(f"{label}（独立来源表）")
                seen.add(label)
        for _field, label in planned_covariates:
            if label not in seen:
                labels.append(f"{label}（本队列未发布）")
        return labels

    @staticmethod
    def _variable_note(
        *,
        available: bool,
        required: bool,
        role: str,
        companion_sources: list[str] | None = None,
        coverage_rate: float | None = None,
    ) -> str:
        coverage_text = f"行覆盖 {coverage_rate:.0%}。" if coverage_rate is not None else ""
        if available:
            return f"{coverage_text}字段已出现在当前科研宽表。".strip()
        if companion_sources:
            names = "、".join(companion_sources)
            return (
                f"已在独立来源表中解析：{names}。"
                "该字段没有合并到当前分析患者，因为跨研究编号相同不等于同一人。"
            )
        if required:
            return f"{coverage_text}当前结果没有该字段；不能用候选库摘要代替患者级变量。".strip()
        if role == "协变量":
            return (
                "本公开队列未发布该患者级字段；禁止把其他研究的临床协变量贴到当前患者。"
                "同队列已提供的临床协变量已单独列出。"
            )
        return f"{coverage_text}当前结果没有该字段；不能用候选库摘要代替患者级变量。".strip()

    @staticmethod
    def _model_expression(research_type: str, exposure: str, outcome: str) -> str:
        if research_type == "survival_analysis":
            return f"h(t) = h₀(t) · exp(β₁X + β₂G + β₃C)，其中 X={exposure}，Y={outcome}"
        if research_type == "differential_expression":
            return f"Expression(Tumor) − Expression(Normal)，分层因子 C={exposure}"
        if research_type == "cross_cohort_reproducibility":
            return f"在独立命名队列内估计 {exposure} 与分层变量的关联，再比较方向是否可重复；禁止跨研究按编号合并患者"
        return f"Y = f(X, G, C)，X={exposure}，Y={outcome}，C=同队列临床协变量（原研究未发布字段保留为缺口）"

    @staticmethod
    def _cohort_rules(spec: ResearchSpec, brief: ResearchBrief | None = None) -> list[str]:
        rules = [f"疾病为 {spec.disease}", "优先保留原发肿瘤样本", "保留患者/样本与来源证据"]
        named = [cohort.name for cohort in (brief.named_cohorts if brief else []) if cohort.role == "named_primary"]
        if named:
            rules.append("命名队列 " + "、".join(named) + " 各自独立分析，禁止跨研究按患者编号合并")
        if spec.subtype:
            subtype_note = "；HER2 检测维度单独保留" if is_breast_cancer(spec.disease) else ""
            rules.append(f"按 {spec.subtype} 进行亚型筛选{subtype_note}")
        elif brief and any(field.field_id == "her2_status" for field in brief.fields if field.priority == "primary"):
            rules.append("HER2 作为分层变量保留原始 IHC/FISH 状态；IHC 2+ 不自动判阳，CNA 不能代替 IHC")
        if spec.genes:
            rules.append(f"需要 {', '.join(spec.genes)} 的分子变量")
        if "treatment_response" in spec.outcomes:
            rules.append("治疗与响应必须来自 clinical response 域")
        if "survival" in spec.outcomes:
            rules.append("生存结局必须保留随访时间与事件状态")
        return rules

    @staticmethod
    def _step(
        steps: list[CohortFilterStep],
        rows: list[dict[str, Any]],
        step_id: str,
        label: str,
        rule_type: str,
        criterion: str,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        active: bool,
    ) -> list[dict[str, Any]]:
        before = len(rows)
        if not active:
            after = rows
            status = "待复核"
            note = "当前数据没有可执行的对应字段，未自动排除记录。"
        else:
            after = [row for row in rows if predicate(row)]
            status = "已执行"
            note = "计数来自当前真实返回行。"
        steps.append(
            CohortFilterStep(
                step_id=step_id,
                label=label,
                rule_type=rule_type,
                criterion=criterion,
                before_count=before,
                after_count=len(after),
                excluded_count=max(0, before - len(after)),
                status=status,
                note=note,
            )
        )
        return after

    @staticmethod
    def _row_has_variable(row: dict[str, Any], variable: StudyVariable) -> bool:
        fields = variable.matched_fields or [variable.variable_id]
        return any(StudyDesignBuilder._has_value(row.get(field)) for field in fields)

    @staticmethod
    def _unique_row_predicate() -> Callable[[dict[str, Any]], bool]:
        seen: set[str] = set()

        def predicate(row: dict[str, Any]) -> bool:
            key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                return False
            seen.add(key)
            return True

        return predicate

    @staticmethod
    def _has_value(value: Any) -> bool:
        return value not in (None, "", [], {}, "NA", "N/A", "<缺失>")

    @classmethod
    def _contains(cls, value: Any, *tokens: str) -> bool:
        text = str(value or "").casefold()
        return cls._has_value(value) and any(token.casefold() in text for token in tokens)

    @staticmethod
    def _canonical_database(value: str) -> str:
        text = value.casefold()
        if "gdc" in text or "tcga" in text:
            return "GDC"
        if "geo" in text:
            return "NCBI GEO"
        if "cbio" in text or "metabric" in text:
            return "cBioPortal"
        if "clinicaltrials" in text or "aact" in text:
            return "ClinicalTrials.gov"
        if "civic" in text:
            return "CIViC"
        return value
