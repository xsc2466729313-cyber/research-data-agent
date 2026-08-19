from __future__ import annotations

from statistics import fmean
from typing import TYPE_CHECKING, Any

from backend.app.agent.models import (
    CompetitionAblationRow,
    CompetitionAlignmentReport,
    CompetitionChecklistItem,
    CompetitionGraphSummary,
    CompetitionMetric,
    CompetitionRagLayer,
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
