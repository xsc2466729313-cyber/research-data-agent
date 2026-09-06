from __future__ import annotations

from backend.app.v30.graph.service import GraphService
from backend.app.v30.models import FigureUnderstandingResult, FigureUnderstandRequest

FIGURE_TYPES = ("light_curve", "kaplan_meier", "heatmap", "scatter", "workflow", "unknown")
EXTRACTABILITY = ("none", "caption_only", "axes_only", "digitization_possible")
NOTICE = "理解演示，非主表数据。即使可数字化也不写入 CanonicalRecord。"

_LIGHT_CURVE = ("light curve", "light-curve", "lightcurve", "光变", "超新星", "supernova", "magnitude", "sn ia", "ia型")
_KAPLAN = ("kaplan", "meier", "survival curve", "生存曲线", "km curve")
_HEATMAP = ("heatmap", "heat map", "热图")
_SCATTER = ("scatter", "散点")
_WORKFLOW = ("workflow", "flowchart", "流程图", "pipeline diagram")


class SourceIdRequiredError(ValueError):
    pass


class FigureUnderstandingService:
    """Describe a paper figure. Never digitizes pixels or writes CanonicalRecord."""

    def __init__(self, graph: GraphService | None = None) -> None:
        self.graph = graph or GraphService()

    def understand(self, request: FigureUnderstandRequest) -> FigureUnderstandingResult:
        source_id = (request.source_id or "").strip()
        if not source_id:
            raise SourceIdRequiredError("source_id_required")
        blob = " ".join(
            part for part in (request.figure_id, request.caption, request.optional_image_reference) if part
        ).lower()
        figure_type, x_axis, y_axis, extractability, confidence, status, legend = _classify(
            blob, caption=request.caption or ""
        )
        if figure_type not in FIGURE_TYPES or extractability not in EXTRACTABILITY:
            raise ValueError("unsupported figure understanding labels")
        if request.optional_image_reference:
            notice = NOTICE + " 未读取像素，未生成观测数据。"
        else:
            notice = NOTICE
        result = FigureUnderstandingResult(
            source_id=source_id,
            figure_id=request.figure_id,
            caption=request.caption,
            figure_type=figure_type,
            x_axis=x_axis,
            y_axis=y_axis,
            legend_summary=legend,
            extractability=extractability,
            digitization_possible=extractability == "digitization_possible",
            confidence=confidence,
            status=status,
            enters_primary_table=False,
            notice=notice,
            row_count=0,
            generates_data=False,
        )
        graph = self.graph.record_figure(result, graph_id=request.graph_id)
        result.graph_id = graph.graph_id
        return result


def _classify(blob: str, *, caption: str) -> tuple[str, str, str, str, float, str, str]:
    if _has(blob, _LIGHT_CURVE):
        return (
            "light_curve",
            "phase_day",
            "magnitude",
            "digitization_possible",
            0.85,
            "UNDERSTOOD",
            "光变曲线图例：可区分超新星或测光波段，当前不读点。",
        )
    if _has(blob, _KAPLAN):
        return (
            "kaplan_meier",
            "time",
            "survival_probability",
            "digitization_possible",
            0.78,
            "UNDERSTOOD",
            "生存曲线图例：分组对照，数字不进主表。",
        )
    if _has(blob, _HEATMAP):
        return (
            "heatmap",
            "sample",
            "gene",
            "axes_only",
            0.72,
            "UNDERSTOOD",
            "热图轴与色标可描述，像素值不入库。",
        )
    if _has(blob, _SCATTER):
        return (
            "scatter",
            "x",
            "y",
            "digitization_possible",
            0.7,
            "UNDERSTOOD",
            "散点图可人工数字化，当前只保留轴语义。",
        )
    if _has(blob, _WORKFLOW):
        return (
            "workflow",
            "",
            "",
            "none",
            0.7,
            "UNDERSTOOD",
            "流程图不含观测轴，无可提取数据点。",
        )
    if caption.strip():
        return (
            "unknown",
            "",
            "",
            "caption_only",
            0.35,
            "REVIEW",
            "仅有图注文本，图类型未确定。",
        )
    return ("unknown", "", "", "none", 0.2, "REVIEW", "缺少图注，仅能标记来源，不能提取。")


def _has(blob: str, hints: tuple[str, ...]) -> bool:
    return any(token in blob for token in hints)
