from __future__ import annotations

import json
from typing import Any

from backend.app.agent.models import (
    CollectionAgentReport,
    CollectionFieldEvidence,
    CollectionGap,
    CollectionIteration,
    CollectionSearchAction,
    StudyDesignReport,
)
from backend.app.models import ResearchSpec


SOURCE_RULES: dict[str, dict[str, Any]] = {
    "sample_id": {
        "sources": ["cBioPortal", "GDC", "NCBI GEO"],
        "reason": "样本编号是患者/样本级关联和去重的基础，不能用候选数据集摘要替代。",
    },
    "patient_id": {
        "sources": ["cBioPortal", "GDC", "NCBI GEO"],
        "reason": "患者编号用于患者级聚合和分组切分，低置信度关联不得自动合并。",
    },
    "sample_type": {
        "sources": ["cBioPortal", "GDC", "NCBI GEO", "NCBI BioSample"],
        "reason": "样本类型决定原发、转移、正常组织或其他标本的分析边界，不能由疾病名称推断。",
    },
    "sample_timepoint": {
        "sources": ["NCBI GEO", "GDC", "cBioPortal"],
        "reason": "样本时间点必须与治疗时间窗对应；缺失时不能把治疗前后样本混为同一分析单位。",
    },
    "sample_source": {
        "sources": ["cBioPortal", "GDC", "NCBI GEO", "NCBI BioSample"],
        "reason": "样本来源用于核对取材部位和组织类型，不能用患者编号或队列名称替代。",
    },
    "subtype": {
        "sources": ["cBioPortal", "GDC", "NCBI GEO"],
        "reason": "亚型必须来自临床/样本字段或可追溯的原始样本特征，不能由疾病名称推断。",
    },
    "treatment": {
        "sources": ["NCBI GEO", "GDC", "ClinicalTrials.gov"],
        "reason": "治疗方案需要患者/样本级治疗字段；临床试验目录只作方案解释，不能冒充患者治疗记录。",
    },
    "treatment_response": {
        "sources": ["NCBI GEO", "GDC", "ClinicalTrials.gov"],
        "reason": "治疗响应必须来自 clinical response 域，并保留原始时间点和响应定义。",
    },
    "outcome": {
        "sources": ["NCBI GEO", "GDC", "ClinicalTrials.gov"],
        "reason": "研究结局必须来自与问题匹配的患者级结局字段，不能用疾病名称或知识证据替代。",
    },
    "mutation": {
        "sources": ["cBioPortal", "GDC"],
        "reason": "基因突变必须来自同一患者/样本的分子检测记录；截断表不能把缺失解释为野生型。",
    },
    "age": {
        "sources": ["cBioPortal", "GDC"],
        "reason": "年龄是可选协变量，但需要原始患者临床字段和单位说明。",
    },
    "stage": {
        "sources": ["cBioPortal", "GDC"],
        "reason": "分期需要原始临床字段；不同分期版本不能直接混用。",
    },
    "evidence": {
        "sources": ["CIViC", "OncoKB"],
        "reason": "知识证据用于解释层，不能直接填入患者主表。",
    },
}


class CollectionAgent:
    """Plan bounded, auditable follow-up searches from observed field gaps."""

    def __init__(self, max_rounds: int = 3) -> None:
        self.max_rounds = max_rounds

    def inspect(
        self,
        *,
        spec: ResearchSpec,
        dataset: Any,
        readiness: Any,
        design: StudyDesignReport,
        source_names: list[str],
        source_items: list[Any],
        round_number: int,
        attempted_calls: set[str],
        actions: list[str],
    ) -> tuple[CollectionIteration, list[CollectionGap], list[CollectionGap]]:
        columns = {column.name for column in dataset.columns}
        critical: list[CollectionGap] = []
        recommended: list[CollectionGap] = []
        for variable in design.required_variables:
            coverage = self._coverage(dataset, variable.matched_fields)
            missing = not variable.available or (coverage is not None and coverage < 0.8)
            if not missing:
                continue
            gap = self._gap(variable, coverage, required=True, source_items=source_items)
            critical.append(gap)
        for variable in design.required_variables:
            if variable.required:
                continue
            coverage = self._coverage(dataset, variable.matched_fields)
            missing = not variable.available or (coverage is not None and coverage < 0.8)
            if missing:
                recommended.append(
                    self._gap(variable, coverage, required=False, source_items=source_items)
                )

        # Gene-specific variables use their variable id, while source rules use
        # the broader mutation class.
        for gap in [*critical, *recommended]:
            if gap.variable_id.endswith("_mutation") or gap.variable_id.endswith("_variants"):
                gap.suggested_sources = SOURCE_RULES["mutation"]["sources"]

        quality_gate = (
            "PASS"
            if not critical
            and dataset.row_count >= 30
            and bool(getattr(readiness, "analysis_ready", False))
            else "REVIEW"
        )
        status = "已通过质量门" if quality_gate == "PASS" else "发现字段缺口"
        note = (
            "关键样本字段、研究变量和结局已满足当前研究契约；可进入下一步队列质检。"
            if quality_gate == "PASS"
            else "质量门未通过；系统只记录缺口和补搜方向，不用外部摘要或其他患者填补主表。"
        )
        iteration = CollectionIteration(
            round_number=round_number,
            phase="质量门检测",
            status=status,
            quality_gate=quality_gate,
            source_names=sorted(set(source_names)),
            source_count=len(set(source_names)),
            row_count=dataset.row_count,
            column_count=len(columns),
            available_fields=sorted(columns),
            missing_critical_fields=[gap.label for gap in critical],
            missing_recommended_fields=[gap.label for gap in recommended],
            actions=actions,
            field_evidence=[
                evidence
                for gap in [*critical, *recommended]
                for evidence in gap.field_evidence
            ],
            note=note,
        )
        return iteration, critical, recommended

    def propose_actions(
        self,
        *,
        spec: ResearchSpec,
        gaps: list[CollectionGap],
        attempted_calls: set[str],
        max_records: int,
    ) -> list[CollectionSearchAction]:
        actions: list[CollectionSearchAction] = []

        def add(
            tool_name: str,
            source_name: str,
            priority: int,
            rationale: str,
            arguments: dict[str, Any],
        ) -> None:
            call = {"name": tool_name, "arguments": arguments}
            if self.call_key(call) in attempted_calls:
                return
            if any(self.call_key({"name": item.tool_name, "arguments": item.arguments}) == self.call_key(call) for item in actions):
                return
            actions.append(
                CollectionSearchAction(
                    action_id=f"follow-up-{len(actions) + 1}",
                    tool_name=tool_name,
                    source_name=source_name,
                    priority=priority,
                    rationale=rationale,
                    status="待执行",
                    arguments=arguments,
                )
            )

        gap_ids = {gap.variable_id for gap in gaps}
        if any(item in gap_ids or item.endswith("_mutation") for item in gap_ids):
            add(
                "search_cbioportal",
                "cBioPortal",
                1,
                "切换到 TCGA-BRCA 患者级队列，补充临床样本表、突变表和患者-样本关联；优先保留主表可连接的分子记录。",
                {
                    "study_id": "brca_tcga",
                    "gene_symbols": spec.genes or ["ERBB2", "PIK3CA"],
                    "max_records": max_records,
                },
            )
            add(
                "search_gdc",
                "GDC / TCGA",
                2,
                "扩大 TCGA-BRCA 官方文件检索，核对临床补充字段和突变文件；只有下载并解析后才能进入患者主表。",
                {
                    "project_id": "TCGA-BRCA",
                    "data_types": ["Clinical Supplement", "Masked Somatic Mutation"],
                    "max_files": 20,
                },
            )
        if "treatment" in gap_ids or "treatment_response" in gap_ids or "outcome" in gap_ids:
            for accession in ("GSE25066", "GSE96058", "GSE76360"):
                add(
                    "search_geo",
                    "NCBI GEO",
                    1,
                    f"检索 {accession} 患者级样本元数据和治疗结局，并下载可审计的 Series Matrix；不把不同队列直接横向拼接。",
                    {"accession": accession, "max_files": 5},
                )
            add(
                "search_trials",
                "ClinicalTrials.gov",
                3,
                "补充治疗方案、响应定义和试验设计语境；结果只作为解释层，不填患者字段。",
                {
                    "condition": spec.disease,
                    "query_terms": " ".join(spec.drugs + spec.genes),
                    "max_trials": 10,
                },
            )
        if {"subtype", "age", "stage", "sample_type", "sample_source", "sample_timepoint"} & gap_ids:
            add(
                "search_cbioportal",
                "cBioPortal",
                1,
                "回到患者临床属性接口，补充亚型、年龄、分期和样本元数据等样本级字段。",
                {
                    "study_id": "brca_tcga",
                    "gene_symbols": spec.genes or ["ERBB2", "PIK3CA"],
                    "max_records": max_records,
                },
            )
            add(
                "search_gdc",
                "GDC / TCGA",
                2,
                "查找官方临床补充文件和病例级临床字段，核对分期、年龄和样本类型定义。",
                {
                    "project_id": "TCGA-BRCA",
                    "data_types": ["Clinical Supplement"],
                    "max_files": 20,
                },
            )
        if "evidence" in gap_ids or "knowledge_evidence" in spec.required_data_types:
            add(
                "search_civic",
                "CIViC",
                4,
                "补充基因-变异-药物的权威知识证据，但不把证据行拼入患者主表。",
                {
                    "disease_name": spec.disease,
                    "molecular_profile_name": spec.genes[0] if spec.genes else None,
                    "therapy_name": spec.drugs[0] if spec.drugs else None,
                    "max_items": 10,
                },
            )
        return sorted(actions, key=lambda item: (item.priority, item.tool_name))

    def report(
        self,
        *,
        iterations: list[CollectionIteration],
        critical: list[CollectionGap],
        recommended: list[CollectionGap],
        actions: list[CollectionSearchAction],
        source_coverage: dict[str, str],
        max_rounds: int | None = None,
    ) -> CollectionAgentReport:
        last_gate = iterations[-1].quality_gate if iterations else "REVIEW"
        status = "已通过质量门" if last_gate == "PASS" else "需要继续补搜"
        return CollectionAgentReport(
            status=status,
            quality_gate=last_gate,
            max_rounds=max_rounds or self.max_rounds,
            completed_rounds=len(iterations),
            iterations=iterations,
            critical_gaps=critical,
            recommended_gaps=recommended,
            next_actions=actions,
            source_coverage=source_coverage,
            note=(
                "质量门通过后才进入后续队列构建；未通过时保留明确缺口，"
                "禁止用知识库、试验目录或不相干患者队列代替样本字段。"
            ),
        )

    @staticmethod
    def _coverage(dataset: Any, fields: list[str]) -> float | None:
        if not fields or not dataset.rows:
            return 0.0
        present = sum(
            any(CollectionAgent._has_value(row.get(field)) for field in fields)
            for row in dataset.rows
        )
        return present / len(dataset.rows)

    @staticmethod
    def _gap(
        variable: Any,
        coverage: float | None,
        required: bool,
        source_items: list[Any],
    ) -> CollectionGap:
        rule_key = variable.variable_id
        if rule_key.endswith("_mutation") or rule_key.endswith("_variants"):
            rule_key = "mutation"
        rule = SOURCE_RULES.get(rule_key, SOURCE_RULES.get(variable.role, {}))
        return CollectionGap(
            variable_id=variable.variable_id,
            label=variable.label,
            role=variable.role,
            required=required,
            coverage_rate=coverage,
            matched_fields=variable.matched_fields,
            reason=(
                f"{rule.get('reason', '当前主科研数据集缺少该字段。')}"
                + (f" 当前覆盖率为 {coverage:.1%}。" if coverage is not None else "")
            ),
            suggested_sources=list(rule.get("sources", [])),
            field_evidence=[
                CollectionFieldEvidence(
                    source_name=str(item.source_name),
                    source_id=str(item.source_id),
                    status=str(item.status),
                    matched_fields=list(variable.matched_fields),
                    note="已登记来源，但字段是否足量仍以当前患者/样本宽表覆盖率为准。",
                )
                for item in source_items
                if str(item.source_name) in rule.get("sources", [])
            ],
        )

    @staticmethod
    def _has_value(value: Any) -> bool:
        return value not in (None, "", [], {}, "NA", "N/A", "<缺失>")

    @staticmethod
    def call_key(call: dict[str, Any]) -> str:
        return f"{call.get('name')}:{json.dumps(call.get('arguments') or {}, sort_keys=True, ensure_ascii=False)}"
