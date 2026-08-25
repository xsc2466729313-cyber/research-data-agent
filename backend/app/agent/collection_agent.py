from __future__ import annotations

import json
from typing import Any

from backend.app.agent.goal_loop import GoalLoopController
from backend.app.agent.models import (
    CollectionAgentReport,
    CollectionFieldEvidence,
    CollectionGap,
    CollectionIteration,
    CollectionSearchAction,
    StudyDesignReport,
)
from backend.app.agent.study_design import PROTOCOL_COVARIATES, VARIABLE_FIELD_ALIASES, covariate_fields_in_pack
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
    """Observe field gaps, diagnose the failure, and switch unused retrieval methods."""

    def __init__(self, max_rounds: int = 12) -> None:
        self.max_rounds = max_rounds
        self.goal_loop = GoalLoopController()

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
        source_datasets: list[Any] | None = None,
    ) -> tuple[CollectionIteration, list[CollectionGap], list[CollectionGap]]:
        columns = {column.name for column in dataset.columns}
        critical: list[CollectionGap] = []
        recommended: list[CollectionGap] = []
        for variable in design.required_variables:
            if not variable.required:
                continue
            coverage = self._coverage(dataset, self._coverage_fields(variable, dataset))
            missing = not variable.available or (coverage is not None and coverage < 0.8)
            if not missing:
                continue
            gap = self._gap(variable, coverage, required=True, source_items=source_items)
            critical.append(gap)
        for variable in design.required_variables:
            if variable.required:
                continue
            coverage = self._coverage(dataset, self._coverage_fields(variable, dataset))
            missing = not variable.available or (coverage is not None and coverage < 0.8)
            if missing:
                if getattr(variable, "companion_sources", None):
                    continue
                recommended.append(
                    self._gap(variable, coverage, required=False, source_items=source_items)
                )

        # Gene-specific variables use their variable id, while source rules use
        # the broader mutation class.
        for gap in [*critical, *recommended]:
            if gap.variable_id.endswith("_mutation") or gap.variable_id.endswith("_variants"):
                gap.suggested_sources = SOURCE_RULES["mutation"]["sources"]

        pack_fields = covariate_fields_in_pack(dataset, source_datasets)
        if len(pack_fields) >= len(PROTOCOL_COVARIATES):
            recommended = [
                gap
                for gap in recommended
                if gap.variable_id not in pack_fields
            ]
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
            else "质量门未通过；将按缺口类型更换尚未尝试的检索方法，不用其他患者填补主表。"
        )
        iteration = CollectionIteration(
            round_number=round_number,
            phase="观察-诊断",
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
        dataset: Any | None = None,
        readiness: Any | None = None,
        limit: int = 2,
    ) -> list[CollectionSearchAction]:
        diagnosis = self.goal_loop.diagnose(
            spec=spec,
            dataset=dataset,
            readiness=readiness,
            gaps=gaps,
        )
        return self.goal_loop.next_actions(
            spec=spec,
            diagnosis=diagnosis,
            attempted_calls=attempted_calls,
            max_records=max_records,
            limit=limit,
        )

    def decide(
        self,
        *,
        spec: ResearchSpec,
        dataset: Any,
        readiness: Any,
        gaps: list[CollectionGap],
        attempted_calls: set[str],
        max_records: int,
        round_number: int,
        max_rounds: int,
        cohort: Any | None = None,
        source_datasets: list[Any] | None = None,
    ):
        return self.goal_loop.decide(
            spec=spec,
            dataset=dataset,
            readiness=readiness,
            gaps=gaps,
            attempted_calls=attempted_calls,
            max_records=max_records,
            round_number=round_number,
            max_rounds=max_rounds,
            cohort=cohort,
            source_datasets=source_datasets,
        )

    def report(
        self,
        *,
        iterations: list[CollectionIteration],
        critical: list[CollectionGap],
        recommended: list[CollectionGap],
        actions: list[CollectionSearchAction],
        source_coverage: dict[str, str],
        max_rounds: int | None = None,
        stop_reason: str = "",
        diagnosis: str | None = None,
        goals: list[Any] | None = None,
        strategies_tried: list[str] | None = None,
    ) -> CollectionAgentReport:
        last_gate = iterations[-1].quality_gate if iterations else "REVIEW"
        if last_gate == "PASS":
            status = "已通过质量门"
        elif last_gate == "PARTIAL":
            status = "主目标已达成，剩余科学缺口"
        else:
            status = "需要继续换方法" if any(item.decision == "continue" for item in iterations) else "方法已用尽或仍待补搜"
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
                stop_reason
                or "观察缺口类型后更换尚未尝试的方法；质量门通过或方法耗尽后停止。"
                "禁止用知识库、试验目录或不相干患者队列代替样本字段。"
            ),
            stop_reason=stop_reason or (iterations[-1].note if iterations else ""),
            diagnosis=diagnosis or (iterations[-1].diagnosis if iterations else None),
            goals=list(goals or []),
            strategies_tried=list(strategies_tried or []),
        )

    @staticmethod
    def _coverage_fields(variable: Any, dataset: Any) -> list[str]:
        fields = list(dict.fromkeys([
            *list(variable.matched_fields or []),
            *VARIABLE_FIELD_ALIASES.get(variable.variable_id, []),
            variable.variable_id,
        ]))
        if variable.variable_id == "outcome":
            target = getattr(dataset, "target_column", None)
            if target:
                fields.append(target)
        return fields

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
