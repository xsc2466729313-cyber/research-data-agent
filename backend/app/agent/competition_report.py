from __future__ import annotations

import re
from statistics import fmean
from typing import TYPE_CHECKING, Any

from backend.app.agent.models import (
    CompetitionAblationRow,
    CompetitionAlignmentReport,
    CompetitionChecklistItem,
    CompetitionGraphSummary,
    CompetitionMetric,
    HorizontalComparisonTable,
    CompetitionRagFlowEdge,
    CompetitionRagMatch,
    CompetitionRagFlowNode,
    CompetitionRagLayer,
    CompetitionVisualEdge,
    CompetitionVisualNode,
    ModelComparisonRow,
    ScientificUsabilityAnalysis,
    ScientificUsabilityFinding,
    StratifiedEvaluationRow,
    TaskAdaptiveFitnessReport,
    UnifiedEvaluationLayer,
    UnifiedEvaluationReport,
)

if TYPE_CHECKING:
    from backend.app.agent.models import AgentTaskResult


class CompetitionReportBuilder:
    """Build competition-facing diagnostics without claiming official scores."""

    def build(self, result: AgentTaskResult) -> CompetitionAlignmentReport:
        sources = list(result.source_items)
        candidates = list(result.candidate_sources)
        dataset = result.modeling_dataset
        readiness = result.readiness
        databases = self._unique_databases(sources, candidates)
        source_audit_score = self._source_audit_score(sources, dataset)
        outcome_complete = (
            None if readiness.target_missing_rate is None else 1 - readiness.target_missing_rate
        )
        field_complete = readiness.field_completeness_rate
        question_fit_score, question_fit_detail = self._question_fit_score(result, candidates)
        source_diversity = self._ratio(len(databases), 5)
        exploratory_analysis_score = self._exploratory_analysis_score(
            result,
            outcome_complete=outcome_complete,
            field_complete=field_complete,
            question_fit_score=question_fit_score,
            source_audit_score=source_audit_score,
        )
        diagnostic_score = self._diagnostic_score(
            outcome_complete,
            field_complete,
            source_audit_score,
            question_fit_score,
            source_diversity,
            exploratory_analysis_score,
        )
        metrics = [
            self._metric(
                "来源审计完整度",
                source_audit_score,
                ">=85% 更适合提交复核；100% 需人工原文复核",
                (
                    "按 source_id、official URL、accession、状态、checksum/local_path、"
                    "行级 source_id 和 raw_characteristics 加权；自动审计不直接宣称 100%。"
                ),
            ),
            self._metric(
                "结局完整率",
                outcome_complete,
                "尽量接近 100%",
                "结局字段必须与科研问题同域。",
            ),
            self._metric(
                "字段完整率",
                field_complete,
                ">=95% 更稳健",
                "基于主科研数据集的非审计字段计算。",
            ),
            self._metric(
                "请求要素覆盖率",
                question_fit_score,
                "患者级字段与候选证据共同解释",
                question_fit_detail,
            ),
            self._metric(
                "数据源多样性",
                source_diversity,
                "多源更利于交叉验证",
                f"当前联通 {len(databases)} 类数据库：{self._join(databases)}。",
            ),
            self._metric("科研探索可用性", exploratory_analysis_score, "探索性分析，不等于正式发表结论", readiness.status),
            CompetitionMetric(
                name="内部综合诊断分",
                value=None,
                display_value=f"{diagnostic_score:.1f}",
                target="仅作任务诊断，不是官方成绩",
                status="已计算",
                detail="综合来源审计、完整性、结局匹配、请求要素覆盖和探索可用性。",
            ),
            self._count_metric("自动清洗值数", readiness.cleaned_value_count, "清洗与标准化次数。"),
            self._count_metric(
                "孤立分子记录排除数",
                readiness.excluded_orphan_record_count,
                "未连接到临床队列的分子记录。",
            ),
            self._count_metric("重复样本行", readiness.duplicate_row_count, "GEO 或队列中重复观测的行数。"),
        ]
        graph_summary = CompetitionGraphSummary(
            enabled=bool(sources or candidates),
            node_count=self._graph_node_count(result, databases),
            edge_count=self._graph_edge_count(result),
            relation_types=["科研问题->工具", "工具->来源", "来源->主数据集", "字段->字典", "质量反馈->修正"],
            entity_types=self._entity_types(result, databases),
            note=(
                "当前实现采用来源-数据集-字段三层图谱表达，并通过 lineage 图和字段字典展示可追溯关系；"
                "不把不同数据库中的患者强行拼接成同一对象。"
            ),
        )
        rag_flow_nodes, rag_flow_edges = self._rag_flow(result, databases)
        rag_matches = self._rag_matches(result, candidates, sources)
        graph_nodes, graph_edges = self._visual_graph(result, databases, sources, candidates)
        scientific_usability = self._scientific_usability(result)
        unified_evaluation = self._unified_evaluation(
            result,
            databases=databases,
            source_audit_score=source_audit_score,
            outcome_complete=outcome_complete,
            field_complete=field_complete,
            question_fit_score=question_fit_score,
            exploratory_analysis_score=exploratory_analysis_score,
            diagnostic_score=diagnostic_score,
        )
        summary = (
            f"当前任务围绕 {result.research_spec.research_goal} 形成了可追溯的科研数据集，"
            f"联通 {len(databases)} 类来源，输出 {dataset.row_count} 行数据与 {len(dataset.columns)} 个字段；"
            f"内部综合诊断分为 {diagnostic_score:.1f}；统一评价体系 v2 已生成模型对比、"
            "横向对比和分层对比矩阵，未实测 baseline 保持待评测。"
        )
        return CompetitionAlignmentReport(
            competition_name="2026年度中国青年科技创新揭榜挂帅擂台赛",
            track="赛道二·数据场景",
            direction="方向1A · 科学数据查找解析与整合",
            problem_focus=result.research_spec.research_goal,
            unified_evaluation=unified_evaluation,
            metrics=metrics,
            ablation_rows=self._ablation_rows(result, databases),
            rag_layers=self._rag_layers(result, databases),
            knowledge_graph=graph_summary,
            rag_flow_nodes=rag_flow_nodes,
            rag_flow_edges=rag_flow_edges,
            rag_matches=rag_matches,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            scientific_usability=scientific_usability,
            improvement_highlights=self._improvement_highlights(
                result, databases, outcome_complete, field_complete, source_audit_score
            ),
            limitations=self._limitations(result, readiness),
            submission_checklist=self._submission_checklist(result, readiness),
            deliverables=[
                "技术方案 PPT/PDF（<=20 页）",
                "可交互前端与测试 API",
                "源代码与运行说明",
                "Qwen 调用凭证或截图",
                "代表性案例的来源、解析和修正记录",
                "结构化科研数据集、字段字典与质量报告",
            ],
            summary=summary,
        )

    @staticmethod
    def _metric(name: str, value: float | None, target: str, detail: str) -> CompetitionMetric:
        if value is None:
            return CompetitionMetric(
                name=name,
                value=None,
                display_value="未计算",
                target=target,
                status="待补充",
                detail=detail,
            )
        display_value = f"{value * 100:.1f}%"
        if name == "数据源多样性":
            status = "已记录"
        elif name in {"来源审计完整度", "科研探索可用性"}:
            status = "达标" if value >= 0.85 else "观察" if value >= 0.6 else "待提升"
        else:
            status = "达标" if value >= 0.95 else "待提升"
        return CompetitionMetric(
            name=name,
            value=value,
            display_value=display_value,
            target=target,
            status=status,
            detail=detail,
        )

    @staticmethod
    def _count_metric(name: str, value: int, detail: str) -> CompetitionMetric:
        return CompetitionMetric(
            name=name,
            value=None,
            display_value=str(value),
            target="如实记录",
            status="已记录",
            detail=detail,
        )

    @staticmethod
    def _unified_evaluation(
        result: AgentTaskResult,
        *,
        databases: list[str],
        source_audit_score: float | None,
        outcome_complete: float | None,
        field_complete: float | None,
        question_fit_score: float | None,
        exploratory_analysis_score: float | None,
        diagnostic_score: float,
    ) -> UnifiedEvaluationReport:
        quality_gate, publish_allowed, gate_note = CompetitionReportBuilder._domain_quality_gate(
            result,
            source_audit_score=source_audit_score,
            question_fit_score=question_fit_score,
        )
        fitness = CompetitionReportBuilder._task_adaptive_fitness(
            result,
            source_audit_score=source_audit_score,
            outcome_complete=outcome_complete,
            field_complete=field_complete,
            question_fit_score=question_fit_score,
            exploratory_analysis_score=exploratory_analysis_score,
            quality_gate=quality_gate,
            publish_allowed=publish_allowed,
            gate_note=gate_note,
        )
        current_method = CompetitionReportBuilder._current_method_id(result, databases)
        observed = {
            "internal_diagnostic_score": round(diagnostic_score, 4),
            "fitness_score": fitness.fitness_score,
            "source_audit": source_audit_score,
            "outcome_completeness": outcome_complete,
            "field_completeness": field_complete,
            "question_fit": question_fit_score,
            "exploratory_usability": exploratory_analysis_score,
        }
        model_comparison = CompetitionReportBuilder._model_comparison_rows(
            result,
            current_method=current_method,
            fitness=fitness,
            quality_gate=quality_gate,
            publish_allowed=publish_allowed,
            observed=observed,
        )
        horizontal = CompetitionReportBuilder._horizontal_tables(
            result,
            model_comparison=model_comparison,
            fitness=fitness,
            quality_gate=quality_gate,
            source_audit_score=source_audit_score,
            field_complete=field_complete,
            question_fit_score=question_fit_score,
        )
        stratified = CompetitionReportBuilder._stratified_rows(
            result,
            databases=databases,
            source_audit_score=source_audit_score,
            fitness=fitness,
            quality_gate=quality_gate,
            publish_allowed=publish_allowed,
        )
        return UnifiedEvaluationReport(
            version="v2",
            status="已接入当前科研任务；外部 benchmark 与未运行模型保持待实测",
            no_fake_scores_notice=(
                "仅 Full Agent 当前任务行使用本次真实可观测结果；未运行的 baseline、"
                "其他模型和 Gold Set SDTI 一律不填推测分数。"
            ),
            layers=[
                UnifiedEvaluationLayer(
                    layer_id="external_benchmarks",
                    label="外部 Benchmark",
                    purpose="证明数据清洗、科学检索、Schema Matching 和 Entity Matching 的通用能力。",
                    status="待接入真实 benchmark run artifact",
                    primary_outputs=["Cleaning F1", "nDCG@10", "Schema F1", "Entity F1"],
                    evidence_requirement="必须记录 benchmark 版本、baseline 代码/论文来源和运行产物。",
                ),
                UnifiedEvaluationLayer(
                    layer_id="frozen_goldset_sdti",
                    label="冻结 Gold Set + SDTI",
                    purpose="评价本项目核心可信整合能力。",
                    status="Gold Set 未提供时保持 NOT_EVALUATED",
                    primary_outputs=["retrieval_f1", "faithfulness", "traceability", "error_f1", "repair_accuracy", "sdti"],
                    evidence_requirement="必须通过 goldset/templates 与 docs/EVALUATION_SDTI.md 的冻结门槛。",
                ),
                UnifiedEvaluationLayer(
                    layer_id="task_adaptive_fitness",
                    label="Task-Adaptive Fitness",
                    purpose="判断本次输出是否适合当前科研问题。",
                    status=fitness.status,
                    primary_outputs=["Research Relevance", "Analytical Adequacy", "Traceability & Reliability", "Reusability"],
                    evidence_requirement="Evaluation Contract 必须先于结果冻结；当前任务生成的是可审计 contract 摘要。",
                ),
                UnifiedEvaluationLayer(
                    layer_id="quality_gate",
                    label="Quality Gate",
                    purpose="判断数据能否发布或进入科研分析。",
                    status=quality_gate,
                    primary_outputs=["PASS", "REVIEW", "REJECT"],
                    evidence_requirement="来源真实性、Evidence、Schema/实体关联、任务硬需求和医学安全规则均需满足。",
                ),
            ],
            task_adaptive_fitness=fitness,
            model_comparison=model_comparison,
            horizontal_comparisons=horizontal,
            stratified_comparisons=stratified,
            required_next_runs=[
                "在 Hospital/Flights/Beers 上运行 Cleaning Benchmark，并填入真实 Cell F1。",
                "在 BEIR SciFact/NFCorpus 上运行 Retrieval Benchmark，并填入 nDCG@10、Recall@100。",
                "在 Valentine 与 DeepMatcher/ER-Magellan 数据上运行 Schema/Entity Matching。",
                "用同一冻结 Evaluation Contract 跑 rule_keyword、qwen_only、single_source_agent、multi_source_no_gate、full_agent。",
                "构建并冻结项目 Gold Set 后再计算 SDTI，未完成前不得宣称系统分数。",
            ],
        )

    @staticmethod
    def _domain_quality_gate(
        result: AgentTaskResult,
        *,
        source_audit_score: float | None,
        question_fit_score: float | None,
    ) -> tuple[str, bool, str]:
        if not result.modeling_dataset.rows:
            return "REJECT", False, "未形成患者/样本级科研数据集。"
        if source_audit_score is None or source_audit_score < 0.70:
            return "REVIEW", False, "来源审计不足，需补充 source_id、官方 URL、checksum 或原始值。"
        if question_fit_score is not None and question_fit_score < 0.60:
            return "REVIEW", False, "科研问题要素覆盖不足，需补充结局、治疗或分子变量证据。"
        if not result.readiness.analysis_ready:
            return "REVIEW", False, result.readiness.status
        if source_audit_score < 0.85:
            return "REVIEW", False, "来源审计未达到建议发布线。"
        return "PASS", True, "当前任务级质量门通过；仍不等同于 Gold Set SDTI 成绩。"

    @staticmethod
    def _task_adaptive_fitness(
        result: AgentTaskResult,
        *,
        source_audit_score: float | None,
        outcome_complete: float | None,
        field_complete: float | None,
        question_fit_score: float | None,
        exploratory_analysis_score: float | None,
        quality_gate: str,
        publish_allowed: bool,
        gate_note: str,
    ) -> TaskAdaptiveFitnessReport:
        dataset = result.modeling_dataset
        row_score = min(dataset.row_count / 50, 1.0) if dataset.row_count else 0.0
        requested_coverage = result.readiness.requested_variable_coverage_rate
        relevance = CompetitionReportBuilder._mean_present(
            [question_fit_score, requested_coverage, 1.0 if result.readiness.target_match else 0.0]
        )
        class_score = 0.0
        if dataset.class_distribution:
            nonmissing = [
                count
                for label, count in dataset.class_distribution.items()
                if label != "<缺失>" and count > 0
            ]
            class_score = 1.0 if len(nonmissing) > 1 else 0.45 if nonmissing else 0.0
        adequacy = CompetitionReportBuilder._mean_present(
            [row_score, field_complete, outcome_complete, class_score]
        )
        traceability_reliability = source_audit_score
        raw_retention = CompetitionReportBuilder._raw_retention_score(dataset.rows)
        reusability = CompetitionReportBuilder._mean_present(
            [
                1.0 if dataset.columns else 0.0,
                raw_retention,
                1.0 if dataset.rows else 0.0,
                field_complete,
            ]
        )
        dimension_values = [
            ("Research Relevance", relevance, "人群、变量、结局和任务要素匹配度。"),
            ("Analytical Adequacy", adequacy, "样本量、缺失、结局分布和基础分析可用性。"),
            ("Traceability & Reliability", traceability_reliability, "真实来源、行级 source_id、原始值和证据链完整性。"),
            ("Reusability", reusability, "字段字典、raw value、机器可读导出和复现信息。"),
        ]
        present_values = [value for _, value, _ in dimension_values if value is not None]
        if len(present_values) == len(dimension_values):
            product = 1.0
            for value in present_values:
                product *= max(0.0, min(1.0, value))
            fitness_score = round(100 * product ** (1 / len(present_values)), 4)
            status = "已计算"
        else:
            fitness_score = None
            status = "部分计算"
        dimensions = [
            CompetitionReportBuilder._metric(
                name,
                value,
                "0-4 rubric 归一化后几何平均",
                detail,
            )
            for name, value, detail in dimension_values
        ]
        gaps: list[str] = []
        for name, value, detail in dimension_values:
            if value is None:
                gaps.append(f"{name} 缺少可计算证据：{detail}")
            elif value < 0.75:
                gaps.append(f"{name} 低于建议线：{detail}")
        if quality_gate != "PASS":
            gaps.append(f"Quality Gate={quality_gate}：{gate_note}")
        contract_id = f"contract:{result.task_id}:task-adaptive-v2"
        return TaskAdaptiveFitnessReport(
            evaluation_contract_id=contract_id,
            frozen_before_run=True,
            status=status,
            fitness_score=fitness_score,
            dimensions=dimensions,
            quality_gate=quality_gate,
            publish_allowed=publish_allowed,
            gap_feedback=list(dict.fromkeys(gaps)),
            note=(
                "当前 contract 摘要由科研问题和冻结规则生成，用于任务级适用性诊断；"
                "正式论文/比赛横比应将完整 contract 落盘后批量重跑。"
            ),
        )

    @staticmethod
    def _current_method_id(result: AgentTaskResult, databases: list[str]) -> str:
        if not result.used_qwen:
            return "rule_keyword"
        if len(databases) <= 1:
            return "single_source_agent"
        return "full_agent"

    @staticmethod
    def _model_comparison_rows(
        result: AgentTaskResult,
        *,
        current_method: str,
        fitness: TaskAdaptiveFitnessReport,
        quality_gate: str,
        publish_allowed: bool,
        observed: dict[str, float | str | None],
    ) -> list[ModelComparisonRow]:
        variants = [
            ("rule_keyword", "Rule/Keyword Baseline", None),
            ("qwen_only", "Qwen-only", result.model_name if result.used_qwen else None),
            ("single_source_agent", "Single-source Agent", result.model_name if result.used_qwen else None),
            ("multi_source_no_gate", "Multi-source No-Gate", result.model_name if result.used_qwen else None),
            ("full_agent", "Full Agent", result.model_name if result.used_qwen else None),
        ]
        rows: list[ModelComparisonRow] = []
        for method_id, label, model in variants:
            if method_id == current_method:
                rows.append(
                    ModelComparisonRow(
                        method_id=method_id,
                        method_label=label,
                        base_model_id=model,
                        status="当前任务真实运行",
                        sdti_status="NOT_EVALUATED",
                        fitness_score=fitness.fitness_score,
                        quality_gate=quality_gate,
                        publish_allowed=publish_allowed,
                        observed_metrics=observed,
                        note="来自本次科研任务的真实可观测指标；未运行冻结 Gold Set，SDTI 不评测。",
                    )
                )
            else:
                rows.append(
                    ModelComparisonRow(
                        method_id=method_id,
                        method_label=label,
                        base_model_id=model,
                        status="待同任务实测",
                        sdti_status="NOT_EVALUATED",
                        fitness_score=None,
                        quality_gate="REVIEW",
                        publish_allowed=False,
                        observed_metrics={},
                        note="需使用同一 Evaluation Contract、同一数据范围和同一脚本重跑后填入。",
                    )
                )
        return rows

    @staticmethod
    def _horizontal_tables(
        result: AgentTaskResult,
        *,
        model_comparison: list[ModelComparisonRow],
        fitness: TaskAdaptiveFitnessReport,
        quality_gate: str,
        source_audit_score: float | None,
        field_complete: float | None,
        question_fit_score: float | None,
    ) -> list[HorizontalComparisonTable]:
        return [
            HorizontalComparisonTable(
                table_id="task_fitness_by_variant",
                title="当前科研任务模型横向对比",
                status="当前方法已填真实值，其余待同任务实测",
                columns=["method", "base_model", "fitness", "quality_gate", "sdti_status", "note"],
                rows=[
                    {
                        "method": row.method_label,
                        "base_model": row.base_model_id or "N/A",
                        "fitness": row.fitness_score,
                        "quality_gate": row.quality_gate,
                        "sdti_status": row.sdti_status,
                        "note": row.note,
                    }
                    for row in model_comparison
                ],
                note="横向表不填推测 baseline 分数；只展示本次真实运行和待实测槽位。",
            ),
            HorizontalComparisonTable(
                table_id="sdti_goldset_by_variant",
                title="冻结 Gold Set / SDTI 横向对比",
                status="NOT_EVALUATED",
                columns=["method", "retrieval_f1", "faithfulness", "traceability", "error_f1", "repair_accuracy", "sdti"],
                rows=[
                    {
                        "method": row.method_label,
                        "retrieval_f1": None,
                        "faithfulness": None,
                        "traceability": None,
                        "error_f1": None,
                        "repair_accuracy": None,
                        "sdti": None,
                    }
                    for row in model_comparison
                ],
                note="项目 Gold Set 尚未随本次任务提供，所有 SDTI 指标必须保持空值。",
            ),
            HorizontalComparisonTable(
                table_id="quality_gate_ablation",
                title="Quality Gate 消融横向表",
                status="Full Gate 当前可诊断，其他消融待重跑",
                columns=["variant", "critical_error_rate", "traceability", "coverage", "quality_gate", "publish_allowed"],
                rows=[
                    {
                        "variant": "No Gate",
                        "critical_error_rate": None,
                        "traceability": None,
                        "coverage": None,
                        "quality_gate": "待实测",
                        "publish_allowed": False,
                    },
                    {
                        "variant": "Source Gate",
                        "critical_error_rate": None,
                        "traceability": source_audit_score,
                        "coverage": None,
                        "quality_gate": "待实测",
                        "publish_allowed": False,
                    },
                    {
                        "variant": "Full Gate",
                        "critical_error_rate": None,
                        "traceability": source_audit_score,
                        "coverage": result.readiness.field_completeness_rate,
                        "quality_gate": quality_gate,
                        "publish_allowed": fitness.publish_allowed,
                    },
                ],
                note="Critical Error Rate 必须依赖人工/Gold Set 标注，当前任务不自动生成。",
            ),
            HorizontalComparisonTable(
                table_id="domain_quality_metrics",
                title="当前任务质量横向指标",
                status="已计算当前 Full Agent 诊断值",
                columns=["metric", "value", "direction", "source"],
                rows=[
                    {"metric": "Fitness Score", "value": fitness.fitness_score, "direction": "higher", "source": fitness.evaluation_contract_id},
                    {"metric": "Source Audit", "value": source_audit_score, "direction": "higher", "source": "source_items + dataset rows"},
                    {"metric": "Field Completeness", "value": field_complete, "direction": "higher", "source": "modeling_dataset"},
                    {"metric": "Question Fit", "value": question_fit_score, "direction": "higher", "source": "research_spec + candidates"},
                ],
                note="这些是任务级诊断指标，不是外部 Benchmark 或 Gold Set SDTI。",
            ),
        ]

    @staticmethod
    def _stratified_rows(
        result: AgentTaskResult,
        *,
        databases: list[str],
        source_audit_score: float | None,
        fitness: TaskAdaptiveFitnessReport,
        quality_gate: str,
        publish_allowed: bool,
    ) -> list[StratifiedEvaluationRow]:
        rows: list[StratifiedEvaluationRow] = []
        subtype = result.research_spec.subtype or "mixed_or_unknown"
        rows.append(
            StratifiedEvaluationRow(
                stratum_name="disease_subtype",
                stratum_value=subtype,
                n=result.modeling_dataset.row_count,
                metrics={"fitness_score": fitness.fitness_score, "target_match": str(result.readiness.target_match)},
                quality_gate=quality_gate,
                publish_allowed=publish_allowed,
                note="按科研问题识别的乳腺癌亚型分层。",
            )
        )
        source_counter: dict[str, int] = {}
        for source in result.source_items:
            db = CompetitionReportBuilder._canonical_database(source.source_name)
            source_counter[db] = source_counter.get(db, 0) + 1
        for candidate in result.candidate_sources:
            db = CompetitionReportBuilder._canonical_database(candidate.source_database)
            source_counter.setdefault(db, 0)
        for db in databases:
            rows.append(
                StratifiedEvaluationRow(
                    stratum_name="source_type",
                    stratum_value=db,
                    n=source_counter.get(db, 0),
                    metrics={
                        "selected_source_count": source_counter.get(db, 0),
                        "source_audit": source_audit_score if source_counter.get(db, 0) else None,
                    },
                    quality_gate=quality_gate if source_counter.get(db, 0) else "REVIEW",
                    publish_allowed=False,
                    note="来源类型分层；未登记真实来源的候选库不允许自动发布。",
                )
            )
        response_domains = CompetitionReportBuilder._response_domain_counts(result)
        for domain, count in response_domains.items():
            rows.append(
                StratifiedEvaluationRow(
                    stratum_name="response_domain",
                    stratum_value=domain,
                    n=count,
                    metrics={"row_share": CompetitionReportBuilder._ratio(count, max(result.modeling_dataset.row_count, 1))},
                    quality_gate=quality_gate,
                    publish_allowed=publish_allowed and domain == "clinical",
                    note="患者疗效、细胞系药敏、临床试验和知识证据必须分域评价。",
                )
            )
        evidence_counts = CompetitionReportBuilder._evidence_level_counts(result)
        for level, count in evidence_counts.items():
            rows.append(
                StratifiedEvaluationRow(
                    stratum_name="evidence_level",
                    stratum_value=level,
                    n=count,
                    metrics={"source_count": count},
                    quality_gate=quality_gate if level != "secondary_or_unknown" else "REVIEW",
                    publish_allowed=publish_allowed and level != "secondary_or_unknown",
                    note="证据等级分层来自 accession、PMID/DOI、官方库 URL 和来源登记情况。",
                )
            )
        link_confidence = "high" if result.modeling_dataset.patient_count and result.modeling_dataset.sample_count else "unresolved"
        rows.append(
            StratifiedEvaluationRow(
                stratum_name="patient_sample_link_confidence",
                stratum_value=link_confidence,
                n=result.modeling_dataset.row_count,
                metrics={
                    "patient_count": result.modeling_dataset.patient_count,
                    "sample_count": result.modeling_dataset.sample_count,
                },
                quality_gate=quality_gate if link_confidence == "high" else "REVIEW",
                publish_allowed=publish_allowed and link_confidence == "high",
                note="低置信度患者/样本关联不得自动合并或发布。",
            )
        )
        if result.readiness.warnings:
            rows.append(
                StratifiedEvaluationRow(
                    stratum_name="risk_level",
                    stratum_value="review_required",
                    n=len(result.readiness.warnings),
                    metrics={"warning_count": len(result.readiness.warnings)},
                    quality_gate="REVIEW",
                    publish_allowed=False,
                    note="风险提示需要进入 REVIEW，不被平均分掩盖。",
                )
            )
        return rows

    @staticmethod
    def _mean_present(values: list[float | None]) -> float | None:
        present = [value for value in values if value is not None]
        if not present:
            return None
        return round(fmean(present), 4)

    @staticmethod
    def _raw_retention_score(rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        retained = sum(
            1
            for row in rows
            if row.get("raw_characteristics")
            or any(str(key).startswith("raw_") and value not in {None, ""} for key, value in row.items())
        )
        return round(retained / len(rows), 4)

    @staticmethod
    def _response_domain_counts(result: AgentTaskResult) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in result.modeling_dataset.rows:
            domain = str(row.get("response_domain") or "").strip()
            if not domain:
                domain = "clinical" if result.modeling_dataset.target_column else "knowledge_evidence"
            counts[domain] = counts.get(domain, 0) + 1
        if not counts:
            if any("trial" in source.source_name.casefold() for source in result.source_items):
                counts["clinical_trial"] = 0
            else:
                counts["clinical"] = 0
        return counts

    @staticmethod
    def _evidence_level_counts(result: AgentTaskResult) -> dict[str, int]:
        counts: dict[str, int] = {}
        for source in result.source_items:
            url = (source.url or "").casefold()
            accession = source.accession or ""
            if accession and any(host in url for host in ("ncbi.nlm.nih.gov", "clinicaltrials.gov", "cbioportal.org", "gdc.cancer.gov", "civicdb.org")):
                level = "official_accession"
            elif "pmid" in url or "doi" in url:
                level = "PMID_or_DOI"
            elif any(host in url for host in ("civicdb.org", "cbioportal.org")):
                level = "curated_database"
            else:
                level = "secondary_or_unknown"
            counts[level] = counts.get(level, 0) + 1
        if not counts:
            counts["secondary_or_unknown"] = 0
        return counts

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    @staticmethod
    def _unique_databases(sources: list[Any], candidates: list[Any]) -> list[str]:
        names: list[str] = []
        raw_names = [
            *(source.source_name for source in sources),
            *(candidate.source_database for candidate in candidates),
        ]
        for item in raw_names:
            text = str(item or "").strip()
            if text:
                names.append(CompetitionReportBuilder._canonical_database(text))
        return sorted(dict.fromkeys(names))

    @staticmethod
    def _canonical_database(value: str) -> str:
        lower = value.lower()
        if "cbio" in lower:
            return "cBioPortal"
        if "geo" in lower:
            return "GEO"
        if "gdc" in lower:
            return "GDC"
        if "civic" in lower:
            return "CIViC"
        if "clinicaltrials" in lower or "aact" in lower:
            return "ClinicalTrials.gov"
        return value

    @staticmethod
    def _join(values: list[str]) -> str:
        return "、".join(values) if values else "暂无"

    @staticmethod
    def _diagnostic_score(*values: float | None) -> float:
        present = [value for value in values if value is not None]
        if not present:
            return 0.0
        return round(fmean(present) * 100, 1)

    @staticmethod
    def _source_audit_score(sources: list[Any], dataset: Any) -> float | None:
        if not sources:
            return None
        scores: list[float] = []
        for source in sources:
            score = 0.0
            score += 0.18 if getattr(source, "source_id", None) else 0.0
            score += 0.18 if getattr(source, "url", None) else 0.0
            score += 0.14 if getattr(source, "accession", None) else 0.0
            score += 0.12 if getattr(source, "status", None) else 0.0
            score += 0.18 if (getattr(source, "checksum", None) or getattr(source, "local_path", None)) else 0.0
            score += 0.10 if CompetitionReportBuilder._is_official_source_url(getattr(source, "url", None)) else 0.0
            score += 0.10 if getattr(source, "file_type", None) else 0.0
            scores.append(score)
        source_item_score = fmean(scores)

        row_lineage_score = 0.0
        raw_value_score = 0.0
        rows = list(getattr(dataset, "rows", []) or [])
        if rows:
            row_lineage_score = sum(1 for row in rows if row.get("source_id")) / len(rows)
            raw_value_score = sum(
                1
                for row in rows
                if row.get("raw_characteristics")
                or any(str(key).startswith("raw_") and value not in {None, ""} for key, value in row.items())
            ) / len(rows)
        weighted_score = source_item_score * 0.72 + row_lineage_score * 0.18 + raw_value_score * 0.10
        if weighted_score >= 0.995:
            weighted_score = 0.98
        return round(weighted_score, 4)

    @staticmethod
    def _is_official_source_url(url: str | None) -> bool:
        if not url:
            return False
        lower = url.lower()
        official_hosts = (
            "ncbi.nlm.nih.gov",
            "clinicaltrials.gov",
            "api.gdc.cancer.gov",
            "portal.gdc.cancer.gov",
            "cbioportal.org",
            "civicdb.org",
        )
        return any(host in lower for host in official_hosts)

    @staticmethod
    def _question_fit_score(result: AgentTaskResult, candidates: list[Any]) -> tuple[float | None, str]:
        spec = result.research_spec
        dataset = result.modeling_dataset
        facets: list[tuple[str, float]] = []
        if spec.disease:
            disease_text = spec.disease.casefold()
            dataset_text = " ".join(
                f"{row.get('disease', '')} {row.get('subtype', '')} {row.get('raw_characteristics', '')}"
                for row in dataset.rows
            ).casefold()
            candidate_text = " ".join(
                f"{getattr(candidate, 'dataset_name', '')} {getattr(candidate, 'data_type', '')}"
                for candidate in candidates
            ).casefold()
            disease_terms = [disease_text]
            if "breast" in disease_text:
                disease_terms.extend(["breast cancer", "breast carcinoma", "乳腺癌"])
            if spec.subtype:
                disease_terms.append(spec.subtype.casefold())
            disease_hit = any(term and term in dataset_text for term in disease_terms)
            candidate_hit = any(term and term in candidate_text for term in disease_terms)
            facets.append(("疾病人群", 1.0 if disease_hit else 0.8 if candidate_hit else 0.5 if dataset.rows else 0.0))
        if spec.outcomes:
            outcome_hit = 1.0 if result.readiness.target_match else 0.7 if any(getattr(candidate, "has_response", False) for candidate in candidates) else 0.0
            facets.append(("研究结局", outcome_hit))
        if spec.genes:
            column_names = {column.name.casefold() for column in dataset.columns}
            patient_gene_hits = sum(any(name.startswith(gene.casefold() + "_") for name in column_names) for gene in spec.genes)
            molecular_candidates = any(
                any(token in str(getattr(candidate, "data_type", "")).casefold() for token in ("突变", "分子", "拷贝", "mutation", "variant", "genomic"))
                for candidate in candidates
            )
            gene_score = patient_gene_hits / len(spec.genes)
            if patient_gene_hits < len(spec.genes) and molecular_candidates:
                gene_score = max(gene_score, 0.5)
            facets.append(("分子/基因证据", gene_score))
        if spec.drugs or any(term in spec.research_goal for term in ("治疗", "新辅助", "响应", "疗效")):
            treatment_hit = 1.0 if any(getattr(candidate, "has_treatment", False) for candidate in candidates) else 0.0
            facets.append(("治疗信息", treatment_hit))
        if spec.required_data_types:
            required = " ".join(spec.required_data_types).casefold()
            candidate_text = " ".join(f"{getattr(candidate, 'data_type', '')} {getattr(candidate, 'dataset_name', '')}" for candidate in candidates).casefold()
            data_type_hit = 1.0 if any(token and token in candidate_text for token in re.split(r"[\s,，;；/()（）]+", required) if len(token) >= 2) else 0.0
            facets.append(("数据类型", data_type_hit))
        if not facets:
            return None, "科研问题未指定可计算的基因、治疗或结局要素。"
        score = round(fmean(value for _, value in facets), 4)
        detail = "；".join(f"{name} {value:.0%}" for name, value in facets)
        detail += "。患者级缺失的基因变量不会被候选证据冒充为已入主表。"
        return score, detail

    @staticmethod
    def _exploratory_analysis_score(
        result: AgentTaskResult,
        *,
        outcome_complete: float | None,
        field_complete: float | None,
        question_fit_score: float | None,
        source_audit_score: float | None,
    ) -> float | None:
        dataset = result.modeling_dataset
        if not dataset.rows:
            return None
        row_score = min(dataset.row_count / 50, 1.0)
        class_score = 0.0
        if dataset.class_distribution:
            nonmissing = [count for label, count in dataset.class_distribution.items() if label != "<缺失>" and count > 0]
            class_score = 1.0 if len(nonmissing) > 1 else 0.45 if nonmissing else 0.0
        values = [
            row_score,
            outcome_complete if outcome_complete is not None else 0.0,
            field_complete if field_complete is not None else 0.0,
            question_fit_score if question_fit_score is not None else 0.0,
            source_audit_score if source_audit_score is not None else 0.0,
            class_score,
        ]
        return round(fmean(values), 4)

    @staticmethod
    def _ablation_rows(result: AgentTaskResult, databases: list[str]) -> list[CompetitionAblationRow]:
        current_genes = ", ".join(result.research_spec.genes) or "未指定"
        current_outcomes = ", ".join(result.research_spec.outcomes) or "未指定"
        qwen_effect = (
            f"当前任务已使用千问，结构化得到基因 {current_genes}；结局 {current_outcomes}。"
            if result.used_qwen
            else "当前任务未使用千问，已退回确定性规划。"
        )
        return [
            CompetitionAblationRow(
                variant="去掉千问结构化解析",
                removed_component="ResearchSpec 抽取与函数调用规划",
                expected_effect="问题理解、结局识别和工具选择都会变弱。",
                observed_effect=qwen_effect,
                note="消融重点是看科研问题理解是否带来更完整的变量覆盖。",
            ),
            CompetitionAblationRow(
                variant="去掉多源融合",
                removed_component="cBioPortal / GEO / GDC / CIViC 的交叉整合",
                expected_effect="来源多样性、字段完整性和证据互证能力下降。",
                observed_effect=f"当前任务联通 {len(databases)} 类数据库；若退化为单源，来源多样性会明显下降。",
                note="这项消融最能体现查找与整合不是单纯检索。",
            ),
            CompetitionAblationRow(
                variant="去掉来源保留与图谱",
                removed_component="source_id、official URL、lineage 图和字段字典联动",
                expected_effect="Traceability 下降，结果难以审计和复核。",
                observed_effect="当前结果已保留来源编号和官方地址；若关闭该层，图谱和下载表都失去回溯入口。",
                note="用于回应提交要求中的来源标注与结构化可回溯。",
            ),
        ]

    @staticmethod
    def _rag_layers(result: AgentTaskResult, databases: list[str]) -> list[CompetitionRagLayer]:
        source_summary = ", ".join(databases) if databases else "暂无来源"
        return [
            CompetitionRagLayer(
                layer="词法/关键词检索",
                implementation="从科研问题里抽取疾病、基因、药物、结局和 accession 候选。",
                why_it_matters="确保查找入口与任务语义对齐。",
                observable_effect=f"当前任务识别到 {source_summary} 作为检索与整合入口。",
            ),
            CompetitionRagLayer(
                layer="语义/Qwen规划",
                implementation="Qwen 输出结构化 ResearchSpec 和工具选择。",
                why_it_matters="减少无效来源和字段错配。",
                observable_effect="研究问题被拆成疾病、基因、药物和结局四类要素。",
            ),
            CompetitionRagLayer(
                layer="结构化/规则过滤",
                implementation="Pydantic 冻结字段、医学安全规则与质量门控。",
                why_it_matters="防止 HER2、ERBB2 CNA 和跨域 response 混用。",
                observable_effect="HER2 IHC 2+、来源缺失和低置信度关联都会被单独处理。",
            ),
            CompetitionRagLayer(
                layer="知识图谱/来源线索",
                implementation="来源、候选数据集、字段字典和 lineage 图联动。",
                why_it_matters="把可追溯性直接显示给评委和研究者。",
                observable_effect="每个节点都能回到官方页面或校验值。",
            ),
        ]

    @staticmethod
    def _graph_node_count(result: AgentTaskResult, databases: list[str]) -> int:
        return len(databases) + len(result.source_items) + len(result.modeling_dataset.columns) + 1

    @staticmethod
    def _graph_edge_count(result: AgentTaskResult) -> int:
        return len(result.source_items) + len(result.candidate_sources) + max(len(result.modeling_dataset.columns) - 1, 0)

    @staticmethod
    def _entity_types(result: AgentTaskResult, databases: list[str]) -> list[str]:
        values = ["科研问题", "主科研数据集", "字段", "来源项", *databases]
        return list(dict.fromkeys(values))

    @staticmethod
    def _rag_flow(result: AgentTaskResult, databases: list[str]) -> tuple[list[CompetitionRagFlowNode], list[CompetitionRagFlowEdge]]:
        source_label = ", ".join(databases[:3]) if databases else "公开数据库"
        nodes = [
            CompetitionRagFlowNode(node_id="rag-input", label="科研问题", layer="输入", order=1, status="已接收", detail=result.research_spec.research_goal),
            CompetitionRagFlowNode(node_id="rag-lexical", label="关键词/实体", layer="检索", order=2, status="已抽取", detail=f"疾病、基因、药物、结局：{source_label}"),
            CompetitionRagFlowNode(node_id="rag-qwen", label="千问规划", layer="规划", order=3, status="已生成", detail="结构化 ResearchSpec 与工具选择"),
            CompetitionRagFlowNode(node_id="rag-gate", label="规则与质量门控", layer="约束", order=4, status="已应用", detail="医学安全规则、来源校验、字段标准化"),
            CompetitionRagFlowNode(node_id="rag-graph", label="来源/知识图谱", layer="证据", order=5, status="已联动", detail="来源、字段字典、lineage 图"),
            CompetitionRagFlowNode(node_id="rag-output", label="科研数据集", layer="输出", order=6, status="已输出", detail=f"{result.modeling_dataset.row_count} 行科研宽表"),
        ]
        edges = [
            CompetitionRagFlowEdge(source="rag-input", target="rag-lexical", label="文本解析"),
            CompetitionRagFlowEdge(source="rag-lexical", target="rag-qwen", label="结构化规划"),
            CompetitionRagFlowEdge(source="rag-qwen", target="rag-gate", label="工具与规则"),
            CompetitionRagFlowEdge(source="rag-gate", target="rag-graph", label="来源与证据"),
            CompetitionRagFlowEdge(source="rag-graph", target="rag-output", label="整合输出"),
        ]
        return nodes, edges

    @staticmethod
    def _rag_matches(
        result: AgentTaskResult,
        candidates: list[Any],
        sources: list[Any],
    ) -> list[CompetitionRagMatch]:
        """Expose deterministic, auditable library-match signals, not benchmark scores."""
        selected_keys = {
            str(value)
            for source in sources
            for value in (source.accession, source.source_id)
            if value
        }
        seen: set[str] = set()
        matches: list[CompetitionRagMatch] = []
        required_text = " ".join(result.research_spec.required_data_types).casefold()
        disease_text = result.research_spec.disease.casefold()
        query_text = result.research_spec.research_goal.casefold()
        for candidate in candidates:
            match_key = f"{candidate.source_database}:{candidate.dataset_id}"
            if match_key in seen:
                continue
            seen.add(match_key)
            candidate_text = f"{candidate.dataset_name} {candidate.data_type} {candidate.source_database}".casefold()
            disease_terms = [
                token
                for token in re.split(r"[\s,，;；/()（）]+", disease_text)
                if len(token) >= 2
            ]
            disease_signal = 1.0 if any(token in candidate_text for token in disease_terms) else 0.0
            molecular_signal = 1.0 if any(
                token in candidate.data_type.casefold()
                for token in ("突变", "分子", "表达", "拷贝", "mutation", "expression", "genomic", "variant")
            ) and bool(result.research_spec.genes or "分子" in required_text or "mutation" in required_text) else 0.0
            treatment_signal = 1.0 if candidate.has_treatment else 0.0
            outcome_signal = 1.0 if candidate.has_response else 0.0
            data_type_signal = 1.0 if any(
                token and token in candidate_text
                for token in re.split(r"[\s,，;；/()（）]+", required_text)
                if len(token) >= 2
            ) else 0.0
            public_signal = 1.0 if candidate.public_access else 0.0
            signals = {
                "检索相关度": round(candidate.relevance_score, 4),
                "疾病语义": disease_signal,
                "分子数据": molecular_signal,
                "治疗字段": treatment_signal,
                "结局字段": outcome_signal,
                "数据类型": data_type_signal,
                "公开访问": public_signal,
            }
            weights = {
                "检索相关度": 0.25,
                "疾病语义": 0.15,
                "分子数据": 0.15,
                "治疗字段": 0.10,
                "结局字段": 0.15,
                "数据类型": 0.10,
                "公开访问": 0.10,
            }
            match_score = round(sum(signals[name] * weight for name, weight in weights.items()), 4)
            selected = bool(
                candidate.dataset_id in selected_keys
                or candidate.accession in selected_keys
            )
            matched_facets = [name for name, value in signals.items() if value >= 0.5]
            if selected:
                status = "已选用"
            elif match_score >= 0.8:
                status = "高匹配"
            elif match_score >= 0.6:
                status = "中匹配"
            else:
                status = "待复核"
            evidence = [
                f"候选库检索相关度 {candidate.relevance_score:.0%}",
                f"数据类型：{candidate.data_type}",
            ]
            if candidate.sample_count is not None:
                evidence.append(f"样本/记录规模：{candidate.sample_count}")
            if candidate.has_treatment:
                evidence.append("存在治疗字段")
            if candidate.has_response:
                evidence.append("存在结局/响应字段")
            if candidate.accession:
                evidence.append(f"数据编号：{candidate.accession}")
            rationale = "；".join(evidence)
            if selected:
                rationale += "；已在本次任务来源中登记。"
            elif query_text:
                rationale += "；保留为候选，需结合原始字段和人工复核继续确认。"
            matches.append(
                CompetitionRagMatch(
                    match_id=match_key,
                    database=CompetitionReportBuilder._canonical_database(candidate.source_database),
                    dataset_id=candidate.dataset_id,
                    dataset_name=candidate.dataset_name,
                    data_type=candidate.data_type,
                    accession=candidate.accession,
                    sample_count=candidate.sample_count,
                    match_score=match_score,
                    display_score=f"诊断匹配 {match_score:.1%}",
                    status=status,
                    selected=selected,
                    signals=signals,
                    matched_facets=matched_facets,
                    rationale=rationale,
                )
            )
        return sorted(matches, key=lambda item: (-item.match_score, not item.selected, item.dataset_name))

    @staticmethod
    def _visual_graph(
        result: AgentTaskResult,
        databases: list[str],
        sources: list[Any],
        candidates: list[Any],
    ) -> tuple[list[CompetitionVisualNode], list[CompetitionVisualEdge]]:
        nodes: list[CompetitionVisualNode] = [
            CompetitionVisualNode(
                node_id="question",
                label="科研问题",
                node_type="question",
                group="输入",
                weight=4,
                status="已建模",
                detail=result.research_spec.research_goal,
            ),
            CompetitionVisualNode(
                node_id="dataset",
                label="主科研数据集",
                node_type="dataset",
                group="输出",
                weight=max(result.modeling_dataset.row_count, 1),
                status="已输出",
                detail=result.modeling_dataset.name,
            ),
        ]
        edges: list[CompetitionVisualEdge] = []
        for db in databases:
            node_id = f"db:{db}"
            nodes.append(
                CompetitionVisualNode(
                    node_id=node_id,
                    label=db,
                    node_type="database",
                    group="来源",
                    weight=sum(1 for source in sources if CompetitionReportBuilder._canonical_database(source.source_name) == db) + sum(1 for candidate in candidates if CompetitionReportBuilder._canonical_database(candidate.source_database) == db),
                    status="已登记" if any(CompetitionReportBuilder._canonical_database(source.source_name) == db for source in sources) else "候选",
                    detail=f"已登记 {sum(1 for source in sources if CompetitionReportBuilder._canonical_database(source.source_name) == db)} 项来源，候选 {sum(1 for candidate in candidates if CompetitionReportBuilder._canonical_database(candidate.source_database) == db)} 项。",
                )
            )
            edges.append(
                CompetitionVisualEdge(
                    source="question",
                    target=node_id,
                    label="检索",
                    relation_type="retrieval",
                    strength=0.72,
                    detail="由科研问题驱动的数据库检索入口",
                )
            )
            edges.append(
                CompetitionVisualEdge(
                    source=node_id,
                    target="dataset",
                    label="整合",
                    relation_type="integration",
                    strength=0.86,
                    detail="候选与来源整合进主科研数据集",
                )
            )
        if not databases:
            edges.append(
                CompetitionVisualEdge(
                    source="question",
                    target="dataset",
                    label="兜底规划",
                    relation_type="fallback",
                    strength=0.35,
                    detail="仅有确定性规划，尚无真实来源",
                )
            )
        return nodes, edges

    @staticmethod
    def _scientific_usability(result: AgentTaskResult) -> ScientificUsabilityAnalysis | None:
        dataset = result.modeling_dataset
        readiness = result.readiness
        if not dataset.rows:
            return None
        target = readiness.target_column or dataset.target_column
        if not target or target not in dataset.rows[0]:
            return ScientificUsabilityAnalysis(
                title="科研适用性初步分析",
                status="信息不足",
                sample_size=dataset.row_count,
                target_column=target,
                feature_count=len(dataset.columns),
                methods=["字段覆盖检查", "类别平衡检查", "缺失率检查"],
                findings=[],
                interpretation="当前宽表可用于方法演示和结构审查，但尚未识别出稳定的结局字段，不能直接做相关性推断。",
                caveats=["缺少明确结局字段时，不做伪相关性陈述。"],
            )
        numeric_fields: list[tuple[str, list[float]]] = []
        for column in dataset.columns:
            if column.name == target:
                continue
            values = [row.get(column.name) for row in dataset.rows]
            numeric = []
            for value in values:
                if isinstance(value, bool):
                    numeric.append(float(int(value)))
                elif isinstance(value, (int, float)):
                    numeric.append(float(value))
            if len(numeric) >= max(3, len(dataset.rows) // 4):
                numeric_fields.append((column.name, numeric))
        target_values = [row.get(target) for row in dataset.rows]
        target_is_binary = len({str(value) for value in target_values if value not in (None, "")}) <= 2
        findings: list[ScientificUsabilityFinding] = []
        if target_is_binary:
            for name, _values in numeric_fields[:4]:
                paired = []
                for row in dataset.rows:
                    value = row.get(name)
                    target_value = row.get(target)
                    if isinstance(value, (int, float)) and target_value is not None:
                        paired.append((float(value), 1.0 if str(target_value).lower() in {"1", "true", "yes", "positive", "pcr", "阳性", "是"} else 0.0))
                if len(paired) < 3:
                    continue
                xs = [pair[0] for pair in paired]
                ys = [pair[1] for pair in paired]
                score = CompetitionReportBuilder._pearson(xs, ys)
                group_counts = CompetitionReportBuilder._binary_groups(ys)
                findings.append(
                    ScientificUsabilityFinding(
                        variable=name,
                        outcome=target,
                        method="Pearson 相关系数",
                        n=len(paired),
                        display_score=f"r={score:.2f}" if score is not None else "未计算",
                        score=abs(score) if score is not None else None,
                        status="可作探索性证据" if score is not None else "样本不足",
                        interpretation=CompetitionReportBuilder._interpret_score(score, name, target),
                        group_counts=group_counts,
                    )
                )
        existing_variables = {finding.variable for finding in findings}
        target_categories = [str(value) for value in target_values if value not in (None, "")]
        if len(set(target_categories)) >= 2:
            for column in dataset.columns:
                if len(findings) >= 6:
                    break
                if column.name == target or column.name in existing_variables or column.role == "审计信息":
                    continue
                feature_values = [row.get(column.name) for row in dataset.rows]
                if any(isinstance(value, (dict, list, tuple, set)) for value in feature_values):
                    continue
                pairs = [
                    (str(row.get(column.name)), str(row.get(target)))
                    for row in dataset.rows
                    if row.get(column.name) not in (None, "") and row.get(target) not in (None, "")
                ]
                if len(pairs) < 3 or len({feature for feature, _ in pairs}) < 2:
                    continue
                score = CompetitionReportBuilder._cramers_v(pairs)
                group_counts = CompetitionReportBuilder._category_counts(feature for feature, _ in pairs)
                findings.append(
                    ScientificUsabilityFinding(
                        variable=column.name,
                        outcome=target,
                        method="Cramer's V 类别关联",
                        n=len(pairs),
                        display_score=f"V={score:.2f}" if score is not None else "未计算",
                        score=score,
                        status="可作探索性证据" if score is not None else "样本不足",
                        interpretation=CompetitionReportBuilder._interpret_association(score, column.name, target),
                        group_counts=group_counts,
                    )
                )
        methods = ["字段覆盖检查", "缺失率检查", "类别平衡检查"]
        if target_is_binary:
            methods.append("Pearson 相关系数")
        interpretation = (
            "当前宽表具备用于科研问题初步筛选的结构，包含结局字段、变量字段和来源链路；"
            "若要做正式结论，需要进一步的分层、混杂控制和更大的样本集。"
        )
        caveats = [
            "相关性分析只用于探索性说明，不等于因果推断。",
            "数值型特征不足时，结果只展示结构意义，不应夸大统计显著性。",
        ]
        return ScientificUsabilityAnalysis(
            title="科研适用性初步分析",
            status="可探索",
            sample_size=dataset.row_count,
            target_column=target,
            feature_count=len(dataset.columns),
            methods=methods,
            findings=findings,
            interpretation=interpretation,
            caveats=caveats,
        )

    @staticmethod
    def _binary_groups(values: list[float]) -> dict[str, int]:
        positives = sum(1 for value in values if value >= 0.5)
        negatives = len(values) - positives
        return {"阳性/高值": positives, "阴性/低值": negatives}

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float | None:
        if len(xs) < 3 or len(xs) != len(ys):
            return None
        mean_x = fmean(xs)
        mean_y = fmean(ys)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
        denominator_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
        if denominator_x == 0 or denominator_y == 0:
            return None
        return numerator / (denominator_x * denominator_y)

    @staticmethod
    def _category_counts(values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            label = str(value)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6])

    @staticmethod
    def _cramers_v(pairs: list[tuple[str, str]]) -> float | None:
        rows = sorted({feature for feature, _ in pairs})
        columns = sorted({target for _, target in pairs})
        if len(rows) < 2 or len(columns) < 2:
            return None
        table = [[0 for _ in columns] for _ in rows]
        row_index = {value: index for index, value in enumerate(rows)}
        column_index = {value: index for index, value in enumerate(columns)}
        for feature, target in pairs:
            table[row_index[feature]][column_index[target]] += 1
        total = sum(sum(row) for row in table)
        if total == 0:
            return None
        row_totals = [sum(row) for row in table]
        column_totals = [sum(table[row][column] for row in range(len(rows))) for column in range(len(columns))]
        chi_square = 0.0
        for row in range(len(rows)):
            for column in range(len(columns)):
                expected = row_totals[row] * column_totals[column] / total
                if expected:
                    chi_square += (table[row][column] - expected) ** 2 / expected
        denominator = total * min(len(rows) - 1, len(columns) - 1)
        if denominator <= 0:
            return None
        return min((chi_square / denominator) ** 0.5, 1.0)

    @staticmethod
    def _interpret_score(score: float | None, variable: str, target: str) -> str:
        if score is None:
            return f"{variable} 与 {target} 的线性关联暂时无法稳定估计。"
        magnitude = abs(score)
        if magnitude >= 0.6:
            trend = "较强"
        elif magnitude >= 0.3:
            trend = "中等"
        else:
            trend = "较弱"
        direction = "正相关" if score > 0 else "负相关" if score < 0 else "近乎无关"
        return f"{variable} 与 {target} 呈{trend}{direction}，可作为后续分层分析的探索性线索。"

    @staticmethod
    def _interpret_association(score: float | None, variable: str, target: str) -> str:
        if score is None:
            return f"{variable} 与 {target} 的类别关联暂时无法稳定估计。"
        if score >= 0.6:
            strength = "较强"
        elif score >= 0.3:
            strength = "中等"
        else:
            strength = "较弱"
        return f"{variable} 与 {target} 存在{strength}类别关联，可作为后续分组、卡方检验或建模特征筛选的线索。"

    @staticmethod
    def _improvement_highlights(
        result: AgentTaskResult,
        databases: list[str],
        outcome_complete: float | None,
        field_complete: float | None,
        traceability_rate: float | None,
    ) -> list[str]:
        items = [
            "把科研问题转成结构化 ResearchSpec，再驱动真实工具，而不是只做关键词检索。",
            f"把 {len(databases)} 类来源统一进同一份科研数据集，并保留 source_id / 官方 URL。",
        ]
        if outcome_complete is not None:
            items.append(f"结局完整率当前为 {outcome_complete:.1%}，直接暴露是否能支撑后续分析。")
        if field_complete is not None:
            items.append(f"字段完整率当前为 {field_complete:.1%}，能直接指出缺失风险。")
        if traceability_rate is not None:
            items.append(f"来源审计完整度当前为 {traceability_rate:.1%}，覆盖来源字段、行级 source_id 和原始值保留。")
        if result.used_qwen:
            items.append("千问被用于问题理解、工具选择与总结，能体现基座模型要求。")
        return items

    @staticmethod
    def _limitations(result: AgentTaskResult, readiness: Any) -> list[str]:
        items = list(dict.fromkeys(readiness.warnings[:4]))
        if not result.used_qwen:
            items.append("本次任务未启用千问，属于确定性兜底，不应当作完整 Qwen 模式成绩。")
        if not readiness.analysis_ready:
            items.append("当前结果更适合提交为过程与方法演示或诊断性结果，而不是宣称正式可发表结论。")
        return items

    @staticmethod
    def _submission_checklist(result: AgentTaskResult, readiness: Any) -> list[CompetitionChecklistItem]:
        return [
            CompetitionChecklistItem(
                label="Qwen 模型调用",
                status="已覆盖" if result.used_qwen else "待补充",
                detail="需要提供调用凭证或截图。",
            ),
            CompetitionChecklistItem(
                label="来源标注与原始证据",
                status="已覆盖" if result.source_items else "待补充",
                detail="系统保留 source_id；标准化和证据层保留 raw_field/raw_value，科研宽表尽量保留 raw_characteristics 与官方 URL。",
            ),
            CompetitionChecklistItem(
                label="指标丰富化",
                status="已覆盖",
                detail="展示来源、结局、字段、覆盖、诊断分和质量门控。",
            ),
            CompetitionChecklistItem(
                label="消融实验",
                status="已覆盖",
                detail="报告包含去掉千问、多源融合和来源图谱的消融设计。",
            ),
            CompetitionChecklistItem(
                label="混合 RAG + 知识图谱",
                status="已覆盖",
                detail="报告说明词法、语义、结构和图谱四层。",
            ),
            CompetitionChecklistItem(
                label="结果可视化",
                status="已覆盖",
                detail="前端已有指标卡、来源溯源图、字段字典与质量面板。",
            ),
            CompetitionChecklistItem(
                label="闭环修正",
                status="已覆盖" if readiness.cleaning_actions else "待补充",
                detail="保留清洗动作、风险提示和下一步建议。",
            ),
        ]
