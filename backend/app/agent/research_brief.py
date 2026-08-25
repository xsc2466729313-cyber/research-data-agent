from __future__ import annotations

import re
from statistics import fmean
from typing import Any

from backend.app.agent.accession_harvest import (
    asks_pcr,
    asks_survival,
    question_asks_clinical_outcome,
    question_asks_survival,
)
from backend.app.agent.match_scoring import fill_rate
from backend.app.agent.models import (
    DataValueAssessment,
    NamedCohort,
    PrioritizedField,
    ResearchBrief,
)
from backend.app.agent.search_planner import FieldDrivenSearchPlanner, infer_cohorts_from_fields, question_search_terms
from backend.app.models import ResearchSpec

_REPRODUCIBILITY_MARKERS = (
    "可重复",
    "可再现",
    "是否一致",
    "是否相同",
    "reproducib",
    "consistenc",
    "concordant",
)
_HOTSPOT_MARKERS = ("热点", "突变谱", "变异谱", "hotspot", "hot-spot", "variant spectrum")
_MODERATION_MARKERS = ("调节", "交互", "效应修饰", "moderat", "interact", "effect modific")
_QUESTION_FIELD_LEXICON: tuple[dict[str, Any], ...] = (
    {
        "patterns": (r"(?<![A-Za-z])OS(?![A-Za-z])", r"总生存", r"overall survival"),
        "field_id": "os_status",
        "label": "总生存 OS",
        "priority": "primary",
        "reason": "题目点名的生存结局，需要事件状态和随访时间。",
        "aliases": ["os_status", "os_months", "vital_status"],
    },
    {
        "patterns": (r"(?<![A-Za-z])RFS(?![A-Za-z])", r"无复发生存", r"relapse[- ]free"),
        "field_id": "dfs_status",
        "label": "无复发生存 RFS",
        "priority": "primary",
        "reason": "题目点名 RFS；本系统把 RFS 映射到无病/无复发生存字段，不与 OS 混用。",
        "aliases": ["dfs_status", "dfs_months", "rfs_status", "rfs_months"],
    },
    {
        "patterns": (r"(?<![A-Za-z])DFS(?![A-Za-z])", r"无病生存", r"disease[- ]free"),
        "field_id": "dfs_status",
        "label": "无病生存 DFS",
        "priority": "primary",
        "reason": "题目点名的无病生存结局。",
        "aliases": ["dfs_status", "dfs_months"],
    },
    {
        "patterns": (r"\bER\b", r"雌激素受体", r"ER[- ]?status", r"ER 状态", r"ER状态"),
        "field_id": "er_status",
        "label": "ER 状态",
        "priority": "primary",
        "reason": "题目点名的临床分层/调节变量。",
        "aliases": ["er_status"],
    },
    {
        "patterns": (r"HER[- ]?2", r"人表皮生长因子受体2"),
        "field_id": "her2_status",
        "label": "HER2 状态",
        "priority": "primary",
        "reason": "题目把 HER2 作为分层变量；IHC 2+ 不自动判阳，ERBB2 CNA 不能代替 IHC。",
        "aliases": ["her2_status"],
    },
    {
        "patterns": (r"intclust", r"int[- ]?clust", r"integrative cluster", r"整合聚类"),
        "field_id": "intclust",
        "label": "IntClust 分型",
        "priority": "primary",
        "reason": "题目点名的整合聚类分型，几乎只在 METABRIC 发布。",
        "aliases": ["intclust", "integrative_cluster", "int_clust"],
    },
    {
        "patterns": (r"PAM50", r"intrinsic subtype"),
        "field_id": "subtype",
        "label": "PAM50 / 内在亚型",
        "priority": "primary",
        "reason": "题目点名的表达分子分型。",
        "aliases": ["subtype", "pam50", "claudin_subtype"],
    },
    {
        "patterns": (r"分子亚型", r"分子分型", r"Claudin"),
        "field_id": "subtype",
        "label": "分子亚型",
        "priority": "primary",
        "reason": "题目点名分子亚型，需同队列临床或表达分型字段。",
        "aliases": ["subtype", "derived_ihc_subtype", "claudin_subtype", "pam50"],
    },
    {
        "patterns": (r"\bPR\b", r"孕激素受体", r"PR 状态", r"PR状态"),
        "field_id": "pr_status",
        "label": "PR 状态",
        "priority": "primary",
        "reason": "题目点名的受体分层变量。",
        "aliases": ["pr_status"],
    },
    {
        "patterns": (r"\bpCR\b", r"病理完全缓解", r"pathological complete response", r"pathologic complete response"),
        "field_id": "pcr",
        "label": "病理完全缓解 pCR",
        "priority": "primary",
        "reason": "题目点名的治疗响应结局，必须来自同一研究的 clinical response 域。",
        "aliases": ["pcr", "pcr_binary", "response", "treatment_response"],
    },
    {
        "patterns": (r"治疗响应", r"治疗反应", r"treatment response"),
        "field_id": "treatment_response",
        "label": "治疗响应",
        "priority": "primary",
        "reason": "题目点名治疗响应，不能用生存或细胞系药敏代替。",
        "aliases": ["response", "treatment_response", "pcr"],
    },
)
_NAMED_COHORTS: tuple[dict[str, Any], ...] = (
    {
        "patterns": (r"\bMETABRIC\b",),
        "name": "METABRIC",
        "study_id": "brca_metabric",
        "project_id": "",
        "tool_name": "search_cbioportal",
        "role": "named_primary",
    },
    {
        "patterns": (r"TCGA[- ]?BRCA", r"\bTCGA\b"),
        "name": "TCGA-BRCA",
        "study_id": "brca_tcga_pan_can_atlas_2018",
        "project_id": "TCGA-BRCA",
        "tool_name": "search_cbioportal",
        "role": "named_primary",
    },
)


class ResearchBriefBuilder:
    """Deterministic first agent: freeze primary fields, then search named cohorts."""

    def build(self, question: str, spec: ResearchSpec) -> ResearchBrief:
        text = question or spec.research_goal or ""
        needs_outcome = question_asks_clinical_outcome(text)
        type_id, type_label = self._research_type(text, spec, needs_outcome)
        named_cohorts = self._named_cohorts(text)
        fields = self._fields(text, spec, named_cohorts)
        named_cohorts = self._attach_inferred_cohorts(named_cohorts, fields)
        if named_cohorts and not any(field.field_id == "study_id" for field in fields):
            fields = self._fields(text, spec, named_cohorts)
        primary_labels = [field.label for field in fields if field.priority == "primary"]
        named_labels = [
            cohort.name
            for cohort in named_cohorts
            if cohort.role in {"named_primary", "inferred_primary"}
        ]
        keywords = question_search_terms(text, spec)
        keywords = list(
            dict.fromkeys(
                [
                    *spec.genes,
                    *spec.drugs,
                    *[field.label for field in fields if field.priority == "primary"],
                    *named_labels,
                    *keywords,
                ]
            )
        )[:16]
        brief = ResearchBrief(
            research_type_id=type_id,
            research_type=type_label,
            primary_question=text.strip() or spec.research_goal,
            named_cohorts=named_cohorts,
            fields=fields,
            analysis_plan=self._analysis_plan(type_id, named_labels, primary_labels, spec, text),
            needs_clinical_outcome=needs_outcome,
            keywords=keywords,
        )
        brief.search_strategy = FieldDrivenSearchPlanner().strategy_text(spec, brief)
        return brief

    def assess(
        self,
        brief: ResearchBrief,
        dataset: Any,
        source_datasets: list[Any] | None = None,
        readiness: Any | None = None,
    ) -> DataValueAssessment:
        rows = list(getattr(dataset, "rows", []) or [])
        primary = [field for field in brief.fields if field.priority == "primary"]
        coverages = [fill_rate(rows, field.aliases or [field.field_id]) for field in primary]
        primary_coverage = round(fmean(coverages), 4) if coverages else None
        missing = [
            field.label
            for field, coverage in zip(primary, coverages)
            if coverage <= 0
        ]
        named = [cohort for cohort in brief.named_cohorts if cohort.role in {"named_primary", "inferred_primary"}]
        pack = [dataset, *(source_datasets or [])]
        hit: list[str] = []
        missing_cohorts: list[str] = []
        for cohort in named:
            if self._pack_has_cohort(pack, cohort):
                hit.append(cohort.name)
            else:
                missing_cohorts.append(cohort.name)
        row_count = int(getattr(dataset, "row_count", 0) or len(rows))
        if not rows or (primary and primary_coverage == 0):
            status = "尚不足"
            judgment = "主表还没有本题最关键变量，不能判断数据对这个问题有没有科研价值。"
            next_step = "按命名队列和主要字段重新检索；不要用临床终点题的 GEO 响应队列顶替。"
        elif missing or missing_cohorts or (primary_coverage or 0) < 0.6 or row_count < 30:
            status = "部分可用"
            missing_bits = []
            if missing:
                missing_bits.append("主字段缺口：" + "、".join(missing))
            if missing_cohorts:
                missing_bits.append("尚未拿到的命名队列：" + "、".join(missing_cohorts))
            if row_count < 30:
                missing_bits.append(f"当前仅 {row_count} 行，只适合结构检查")
            judgment = "主变量已部分落地，可做探索性核对，但还不足以支撑正式可重复性结论。"
            if missing_bits:
                judgment = judgment + " " + "；".join(missing_bits) + "。"
            next_step = "保留已命中的独立队列，补齐缺失主字段后再比较关联方向；禁止跨研究按患者编号合并。"
        else:
            status = "有科研价值"
            if named:
                judgment = (
                    f"命名队列 { '、'.join(hit) or '主表' } 已覆盖主要字段"
                    f"（平均行覆盖 {primary_coverage:.0%}），可在各自队列内做初步关联并比较方向是否一致。"
                )
            else:
                judgment = f"主字段平均行覆盖 {primary_coverage:.0%}，当前宽表可以进入本题的探索性分析。"
            next_step = "分别报告各独立队列的关联方向，不把跨研究同一编号解释为同一患者。"
        del readiness
        return DataValueAssessment(
            status=status,
            judgment=judgment,
            primary_coverage=primary_coverage,
            named_cohorts_hit=hit,
            named_cohorts_missing=missing_cohorts,
            missing_primary_fields=missing,
            next_step=next_step,
        )

    @staticmethod
    def primary_coverage(dataset: Any, brief: ResearchBrief | None) -> float:
        if brief is None:
            return 0.0
        rows = list(getattr(dataset, "rows", []) or [])
        primary = [field for field in brief.fields if field.priority == "primary"]
        if not primary:
            return 0.0
        return round(fmean(fill_rate(rows, field.aliases or [field.field_id]) for field in primary), 4)

    @staticmethod
    def _research_type(text: str, spec: ResearchSpec, needs_outcome: bool) -> tuple[str, str]:
        blob = text.casefold()
        if any(token in blob for token in _REPRODUCIBILITY_MARKERS):
            return "cross_cohort_reproducibility", "跨队列可重复性"
        if question_asks_survival(text) or asks_survival(spec):
            return "survival_analysis", "预后/生存分析"
        if asks_pcr(spec) or needs_outcome:
            return "response_analysis", "治疗响应分析"
        if spec.genes:
            return "molecular_association", "分子关联分析"
        return "molecular_association", "分子关联分析"

    @staticmethod
    def _named_cohorts(text: str) -> list[NamedCohort]:
        cohorts: list[NamedCohort] = []
        seen: set[str] = set()
        for spec in _NAMED_COHORTS:
            if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in spec["patterns"]):
                continue
            key = spec["name"]
            if key in seen:
                continue
            seen.add(key)
            cohorts.append(
                NamedCohort(
                    name=spec["name"],
                    study_id=spec["study_id"],
                    project_id=spec["project_id"],
                    tool_name=spec["tool_name"],
                    role=spec["role"],
                )
            )
            if spec["project_id"]:
                cohorts.append(
                    NamedCohort(
                        name=f"{spec['name']} / GDC",
                        study_id="",
                        project_id=spec["project_id"],
                        tool_name="search_gdc",
                        role="auxiliary",
                    )
                )
        return cohorts

    @staticmethod
    def _attach_inferred_cohorts(
        named_cohorts: list[NamedCohort],
        fields: list[PrioritizedField],
    ) -> list[NamedCohort]:
        seen_names = {cohort.name for cohort in named_cohorts}
        seen_ids = {cohort.study_id for cohort in named_cohorts if cohort.study_id}
        primary_ids = {field.field_id for field in fields if field.priority == "primary"}
        extra: list[NamedCohort] = []
        for item in infer_cohorts_from_fields(primary_ids):
            if item["name"] in seen_names or item["study_id"] in seen_ids:
                continue
            extra.append(
                NamedCohort(
                    name=item["name"],
                    study_id=item["study_id"],
                    project_id=item["project_id"],
                    tool_name=item["tool_name"],
                    role="inferred_primary",
                )
            )
            seen_names.add(item["name"])
            if item["study_id"]:
                seen_ids.add(item["study_id"])
        return extra + named_cohorts

    @staticmethod
    def _fields(
        text: str,
        spec: ResearchSpec,
        named_cohorts: list[NamedCohort],
    ) -> list[PrioritizedField]:
        fields: list[PrioritizedField] = []
        seen: set[str] = set()

        def add(
            field_id: str,
            label: str,
            priority: str,
            reason: str,
            aliases: list[str],
        ) -> None:
            if field_id in seen:
                return
            seen.add(field_id)
            fields.append(
                PrioritizedField(
                    field_id=field_id,
                    label=label,
                    priority=priority,
                    reason=reason,
                    aliases=list(dict.fromkeys(aliases)),
                )
            )

        for gene in spec.genes:
            symbol = gene.lower()
            hotspot = any(token in text.casefold() for token in _HOTSPOT_MARKERS)
            add(
                f"{symbol}_mutation",
                f"{gene} 突变",
                "primary",
                "题目点名的分子暴露，必须有患者/样本级检测结果。",
                [f"{symbol}_mutation", f"{symbol}_altered", "gene", "mutation_status"],
            )
            if hotspot:
                add(
                    f"{symbol}_variants",
                    f"{gene} 热点突变谱",
                    "primary",
                    "题目要求突变谱/热点，不能只用有无突变的二元标记。",
                    [f"{symbol}_variants", f"{symbol}_mutation"],
                )
        for item in _QUESTION_FIELD_LEXICON:
            if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in item["patterns"]):
                continue
            add(item["field_id"], item["label"], item["priority"], item["reason"], list(item["aliases"]))
        if named_cohorts:
            add(
                "study_id",
                "命名队列",
                "important",
                "题目指定或由主字段推断的研究必须作为独立队列保留，不能跨研究贴患者。",
                ["study_id"],
            )
        add("patient_id", "患者编号", "important", "分析单位与去重依据。", ["patient_id"])
        add("sample_id", "样本编号", "important", "样本级溯源与重复样本识别。", ["sample_id"])
        add("disease", "疾病", "important", "确认乳腺癌边界。", ["disease", "cancer_type", "diagnosis"])
        add("sample_type", "样本类型", "important", "原发/转移/正常组织必须可区分。", ["sample_type"])
        if any(field.field_id == "er_status" for field in fields) and "pr_status" not in seen:
            add("pr_status", "PR 状态", "important", "ER 题可同时看 PR；未点名则不挡主目标。", ["pr_status"])
        if "her2_status" not in seen:
            add("her2_status", "HER2 状态", "secondary", "未点名的受体协变量，有则用，无则保留缺口。", ["her2_status"])
        add("age", "年龄", "secondary", "次要临床协变量；原研究未发布则不得跨队列补值。", ["age", "age_group"])
        add("stage", "分期", "secondary", "次要临床协变量；不同分期版本不能混用。", ["stage"])
        return fields

    @staticmethod
    def _analysis_plan(
        type_id: str,
        named_labels: list[str],
        primary_labels: list[str],
        spec: ResearchSpec,
        text: str = "",
    ) -> str:
        exposure = "、".join(spec.genes) or (primary_labels[0] if primary_labels else "主暴露")
        stratifiers = [label for label in primary_labels if exposure not in label and "突变" not in label]
        if any(token in text.casefold() for token in _MODERATION_MARKERS):
            layers = "、".join(stratifiers) or "题目分层变量"
            cohort = "、".join(named_labels) or "同一研究队列"
            return (
                f"在 {cohort} 内估计 {exposure} 与结局的关系，并按 {layers} 分层/检验是否存在调节；"
                "分层变量必须来自同一研究发布的字段，不能用其他队列的变量冒充。"
            )
        if type_id == "cross_cohort_reproducibility" and named_labels:
            return (
                f"在 { '、'.join(named_labels) } 内分别统计 {exposure} 及其与分层变量的关联，"
                "比较两边方向是否一致；不宣称跨研究同一编号为同一人。"
            )
        if type_id == "survival_analysis":
            return f"在同一队列内分析 {exposure} 与 OS/RFS 等生存结局；随访时间和事件状态必须来自该研究。"
        if type_id == "response_analysis":
            return f"在同一队列内分析 {exposure} 与研究结局的关系，治疗和结局必须来自 clinical response 域。"
        return f"先确认题目主字段齐备，再对 {exposure} 做探索性分布与分层关联；次要字段只用于描述，不挡主目标。"

    @staticmethod
    def _pack_has_cohort(pack: list[Any], cohort: NamedCohort) -> bool:
        tokens = [token.casefold() for token in (cohort.study_id, cohort.project_id, cohort.name) if token]
        for item in pack:
            key = str(getattr(item, "study_key", "") or getattr(item, "name", "") or "").casefold()
            rows = list(getattr(item, "rows", []) or [])
            row_study = str(rows[0].get("study_id") or "").casefold() if rows else ""
            haystack = f"{key} {row_study}"
            if any(token and token in haystack for token in tokens):
                return True
        return False
