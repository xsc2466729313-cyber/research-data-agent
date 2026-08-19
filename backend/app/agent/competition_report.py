from __future__ import annotations

from statistics import fmean
from typing import TYPE_CHECKING, Any

from backend.app.agent.models import (
    CompetitionAblationRow,
    CompetitionAlignmentReport,
    CompetitionChecklistItem,
    CompetitionGraphSummary,
    CompetitionMetric,
    CompetitionRagFlowEdge,
    CompetitionRagFlowNode,
    CompetitionRagLayer,
    CompetitionVisualEdge,
    CompetitionVisualNode,
    ScientificUsabilityAnalysis,
    ScientificUsabilityFinding,
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
        traceable_sources = [source for source in sources if source.source_id and source.url]
        traceability_rate = self._ratio(len(traceable_sources), len(sources))
        outcome_complete = (
            None if readiness.target_missing_rate is None else 1 - readiness.target_missing_rate
        )
        field_complete = readiness.field_completeness_rate
        variable_coverage = readiness.requested_variable_coverage_rate
        source_diversity = self._ratio(len(databases), 5)
        analysis_ready = 1.0 if readiness.analysis_ready else 0.0
        diagnostic_score = self._diagnostic_score(
            outcome_complete,
            field_complete,
            traceability_rate,
            variable_coverage,
            source_diversity,
            analysis_ready,
        )
        metrics = [
            self._metric(
                "来源可追溯率",
                traceability_rate,
                "100%",
                "真实来源均保留 official URL 和 source_id。",
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
                "请求变量覆盖率",
                variable_coverage,
                "1.0 最佳",
                "评估科研问题中的关键基因/变量是否在主数据集中出现。",
            ),
            self._metric(
                "数据源多样性",
                source_diversity,
                "多源更利于交叉验证",
                f"当前联通 {len(databases)} 类数据库：{self._join(databases)}。",
            ),
            self._metric("分析可用性", analysis_ready, "1.0 表示可直接开展分析", readiness.status),
            CompetitionMetric(
                name="内部综合诊断分",
                value=None,
                display_value=f"{diagnostic_score:.1f}",
                target="仅作任务诊断，不是官方成绩",
                status="已计算",
                detail="综合来源、完整性、结局匹配、覆盖和可用性。",
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
        graph_nodes, graph_edges = self._visual_graph(result, databases, sources, candidates)
        scientific_usability = self._scientific_usability(result)
        summary = (
            f"当前任务围绕 {result.research_spec.research_goal} 形成了可追溯的科研数据集，"
            f"联通 {len(databases)} 类来源，输出 {dataset.row_count} 行数据与 {len(dataset.columns)} 个字段；"
            f"内部综合诊断分为 {diagnostic_score:.1f}。"
        )
        return CompetitionAlignmentReport(
            competition_name="2026年度中国青年科技创新揭榜挂帅擂台赛",
            track="赛道二·数据场景",
            direction="方向1A · 科学数据查找解析与整合",
            problem_focus=result.research_spec.research_goal,
            metrics=metrics,
            ablation_rows=self._ablation_rows(result, databases),
            rag_layers=self._rag_layers(result, databases),
            knowledge_graph=graph_summary,
            rag_flow_nodes=rag_flow_nodes,
            rag_flow_edges=rag_flow_edges,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            scientific_usability=scientific_usability,
            improvement_highlights=self._improvement_highlights(
                result, databases, outcome_complete, field_complete, traceability_rate
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
        status = "已记录" if name == "数据源多样性" else "达标" if value >= 0.95 else "待提升"
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
            items.append(f"来源可追溯率当前为 {traceability_rate:.1%}，比普通检索更适合提交要求。")
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
