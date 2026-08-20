from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.app.agent.models import AgentTaskResult


class AgentExportFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"
    XLSX = "xlsx"


@dataclass(frozen=True)
class AgentExportedDataset:
    content: bytes
    media_type: str
    filename: str


class AgentDatasetExportService:
    def export(
        self,
        result: AgentTaskResult,
        file_format: AgentExportFormat,
    ) -> AgentExportedDataset:
        dataset = result.modeling_dataset
        if not dataset.rows:
            raise ValueError("当前任务没有可导出的科研数据行。")
        if file_format == AgentExportFormat.CSV:
            content = self._csv(result)
            media_type = "text/csv; charset=utf-8"
        elif file_format == AgentExportFormat.PARQUET:
            content = self._parquet(result)
            media_type = "application/vnd.apache.parquet"
        else:
            content = self._xlsx(result)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return AgentExportedDataset(
            content=content,
            media_type=media_type,
            filename=f"{result.task_id}-科研数据集.{file_format.value}",
        )

    @staticmethod
    def _csv(result: AgentTaskResult) -> bytes:
        columns = [column.name for column in result.modeling_dataset.columns]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in result.modeling_dataset.rows:
            writer.writerow({name: AgentDatasetExportService._scalar(row.get(name)) for name in columns})
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")

    @staticmethod
    def _parquet(result: AgentTaskResult) -> bytes:
        arrays: dict[str, pa.Array] = {}
        for column in result.modeling_dataset.columns:
            values = [
                AgentDatasetExportService._scalar(row.get(column.name))
                for row in result.modeling_dataset.rows
            ]
            if column.data_type == "number":
                numeric = [value for value in values if value is not None]
                use_float = any(isinstance(value, float) for value in numeric)
                arrow_type = pa.float64() if use_float else pa.int64()
                normalized = [
                    (float(value) if use_float else int(value)) if value is not None else None
                    for value in values
                ]
            else:
                arrow_type = pa.string()
                normalized = [str(value) if value is not None else None for value in values]
            arrays[column.name] = pa.array(normalized, type=arrow_type)
        table = pa.table(arrays)
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="snappy")
        return sink.getvalue().to_pybytes()

    def _xlsx(self, result: AgentTaskResult) -> bytes:
        workbook = Workbook()
        data_sheet = workbook.active
        data_sheet.title = "科研数据集"
        columns = result.modeling_dataset.columns
        headers = [column.name for column in columns]
        data_sheet.append(headers)
        for row in result.modeling_dataset.rows:
            data_sheet.append([self._scalar(row.get(name)) for name in headers])
        self._style_table(data_sheet, len(headers))
        data_sheet.freeze_panes = "A2"
        data_sheet.auto_filter.ref = data_sheet.dimensions

        dictionary = workbook.create_sheet("字段字典")
        dictionary.append(["字段名", "中文标注", "数据类型", "科研用途", "来源字段", "说明"])
        for column in columns:
            dictionary.append(
                [
                    column.name,
                    column.label_zh,
                    column.data_type,
                    column.role,
                    column.source_field,
                    column.description,
                ]
            )
        self._style_table(dictionary, 6)
        dictionary.freeze_panes = "A2"

        report = workbook.create_sheet("可科研性报告")
        report.append(["项目", "内容"])
        entries: list[tuple[str, Any]] = [
            ("任务编号", result.task_id),
            ("科研问题", result.research_spec.research_goal),
            ("智能体模式", result.agent_mode),
            ("千问模型", result.model_name),
            ("分析单位", result.modeling_dataset.unit_of_analysis),
            ("数据行数", result.readiness.row_count),
            ("研究变量数", result.readiness.feature_count),
            ("研究结局字段", result.readiness.target_column or "未识别"),
            ("研究结局是否匹配", "是" if result.readiness.target_match else "否"),
            (
                "研究结局完整率",
                "未计算" if result.readiness.target_missing_rate is None else f"{1 - result.readiness.target_missing_rate:.1%}",
            ),
            (
                "全表字段完整率",
                "未计算" if result.readiness.field_completeness_rate is None else f"{result.readiness.field_completeness_rate:.1%}",
            ),
            (
                "请求变量覆盖率",
                "未指定" if result.readiness.requested_variable_coverage_rate is None else f"{result.readiness.requested_variable_coverage_rate:.1%}",
            ),
            ("自动清洗值数", result.readiness.cleaned_value_count),
            ("排除孤立分子记录数", result.readiness.excluded_orphan_record_count),
            ("是否支持科研分析", "是" if result.readiness.analysis_ready else "否"),
            ("分析分组建议", result.readiness.split_strategy),
            ("千问数据总结", result.summary_zh),
        ]
        for label, value in entries:
            report.append([label, value])
        for warning in result.readiness.warnings:
            report.append(["风险提示", warning])
        for action in result.readiness.cleaning_actions:
            report.append(["清洗动作", action])
        for recommendation in result.readiness.recommendations:
            report.append(["建议", recommendation])
        self._style_table(report, 2)
        report.column_dimensions["A"].width = 22
        report.column_dimensions["B"].width = 100
        report.column_dimensions["B"].alignment = Alignment(wrap_text=True, vertical="top")

        sources = workbook.create_sheet("数据来源")
        sources.append(["来源编号", "数据库", "数据编号（Accession）", "官方地址", "状态", "校验值"])
        for item in result.source_items:
            sources.append(
                [
                    item.source_id,
                    item.source_name,
                    item.accession,
                    item.url,
                    item.status,
                    item.checksum,
                ]
            )
        self._style_table(sources, 6)
        sources.freeze_panes = "A2"


        competition = workbook.create_sheet("比赛报告")
        competition.append(["项目", "内容"])
        report = result.competition_report
        if report is not None:
            competition_rows = [
                ("赛道", report.track),
                ("方向", report.direction),
                ("聚焦问题", report.problem_focus),
                ("总体摘要", report.summary),
            ]
            for label, value in competition_rows:
                competition.append([label, value])
            for metric in report.metrics:
                competition.append(["指标", f"{metric.name}｜{metric.display_value}｜{metric.target}｜{metric.detail}"])
            for row in report.ablation_rows:
                competition.append(["消融", f"{row.variant}｜{row.removed_component}｜{row.expected_effect}｜{row.observed_effect}｜{row.note}"])
            for layer in report.rag_layers:
                competition.append(["混合RAG", f"{layer.layer}｜{layer.implementation}｜{layer.why_it_matters}｜{layer.observable_effect}"])
            for node in report.rag_flow_nodes:
                competition.append(["RAG流程节点", f"{node.order}｜{node.layer}｜{node.label}｜{node.status}｜{node.detail}"])
            for edge in report.rag_flow_edges:
                competition.append(["RAG流程边", f"{edge.source} -> {edge.target}｜{edge.label}｜{edge.detail or ''}"])
            for match in report.rag_matches:
                signal_text = "；".join(f"{name}={value:.0%}" for name, value in match.signals.items())
                competition.append(
                    [
                        "RAG库匹配",
                        f"{match.database}｜{match.dataset_name}｜{match.display_score}｜{match.status}｜"
                        f"{'已选用' if match.selected else '候选'}｜{signal_text}｜{match.rationale}",
                    ]
                )
            competition.append(["知识图谱", f"节点 {report.knowledge_graph.node_count}｜边 {report.knowledge_graph.edge_count}｜关系 {', '.join(report.knowledge_graph.relation_types)}"])
            competition.append(["知识图谱", report.knowledge_graph.note])
            for node in report.graph_nodes:
                competition.append(["知识图谱节点", f"{node.node_id}｜{node.label}｜{node.node_type}｜{node.group}｜{node.status or ''}｜{node.detail or ''}"])
            for edge in report.graph_edges:
                competition.append(["知识图谱边", f"{edge.source} -> {edge.target}｜{edge.label}｜{edge.relation_type}｜strength={edge.strength:.2f}｜{edge.detail or ''}"])
            if report.scientific_usability is not None:
                analysis = report.scientific_usability
                competition.append(["科研适用性", f"{analysis.status}｜样本 {analysis.sample_size}｜结局 {analysis.target_column or '未识别'}｜特征 {analysis.feature_count}｜方法 {', '.join(analysis.methods)}"])
                competition.append(["科研适用性", analysis.interpretation])
                for finding in analysis.findings:
                    competition.append(["科研适用性发现", f"{finding.variable} -> {finding.outcome}｜{finding.method}｜n={finding.n}｜{finding.display_score}｜{finding.status}｜{finding.interpretation}"])
                for caveat in analysis.caveats:
                    competition.append(["科研适用性注意", caveat])
            for item in report.improvement_highlights:
                competition.append(["改进", item])
            for item in report.limitations:
                competition.append(["局限", item])
            for item in report.submission_checklist:
                competition.append(["提交核验", f"{item.label}｜{item.status}｜{item.detail}"])
            for item in report.deliverables:
                competition.append(["交付物", item])
        self._style_table(competition, 2)
        competition.column_dimensions["A"].width = 18
        competition.column_dimensions["B"].width = 110
        competition.column_dimensions["B"].alignment = Alignment(wrap_text=True, vertical="top")

        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    @staticmethod
    def _style_table(sheet: Any, column_count: int) -> None:
        fill = PatternFill("solid", fgColor="0F766E")
        for cell in sheet[1]:
            cell.fill = fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for column_index in range(1, column_count + 1):
            values = [str(sheet.cell(row=row, column=column_index).value or "") for row in range(1, min(sheet.max_row, 100) + 1)]
            width = min(max(max((len(value) for value in values), default=8) + 2, 12), 42)
            sheet.column_dimensions[get_column_letter(column_index)].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=False)

    @staticmethod
    def _scalar(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple, set)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return value
