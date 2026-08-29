from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from backend.app.evaluation.overview import OverviewMetric

ROOT = Path(__file__).resolve().parents[3]
_METRICS_PATH = ROOT / "evaluation_toolkit" / "scripts" / "metrics_template.py"


def _load_toolkit_metrics() -> Any:
    spec = importlib.util.spec_from_file_location("evaluation_toolkit_metrics", _METRICS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("未找到 evaluation_toolkit/scripts/metrics_template.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOLKIT = _load_toolkit_metrics()

DIRTY_TOKENS = {
    "NA",
    "N/A",
    "NULL",
    "UNKNOWN",
    "[NOT AVAILABLE]",
    "NOT AVAILABLE",
    "<缺失>",
}

AUDIT_COLUMNS = {"source_id", "raw_characteristics", "study_id"}
MISSING_CELL_TOKENS = {
    "",
    "—",
    "–",
    "-",
    ".",
    "NONE",
    "MISSING",
    "<缺失>",
}


def _is_missing_cell(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return True
    return stripped.upper() in MISSING_CELL_TOKENS or stripped in {"—", "–"}


def _metric(
    key: str,
    label: str,
    value: float | None,
    *,
    unit: str = "percent",
    target: float,
    reason: str,
    headline: str | None = None,
    plain_meaning: str | None = None,
) -> OverviewMetric:
    if value is None:
        display = None
    elif unit == "score":
        display = value
    else:
        display = value * 100
    return OverviewMetric(
        key=key,
        label=label,
        value=value,
        display_value=display,
        target=target if unit == "percent" else None,
        display_target=target * 100 if unit == "percent" else target,
        unit=unit,
        status="TOOLKIT_RUN" if value is not None else "NOT_EVALUATED",
        reason=reason,
        headline=headline,
        plain_meaning=plain_meaning,
    )


def _f1_from_counts(tp: int, fp: int, fn: int) -> dict[str, float]:
    gold = {f"g{i}" for i in range(tp + fn)}
    pred = {f"g{i}" for i in range(tp)} | {f"p{i}" for i in range(fp)}
    return TOOLKIT.precision_recall_f1(gold, pred)


def _cleaning_score(task: Any) -> tuple[float | None, str, str | None, str | None]:
    dataset = getattr(task, "modeling_dataset", None)
    rows = list(getattr(dataset, "rows", None) or [])
    if not rows:
        return None, "当前任务没有宽表，无法按工具包 cell 公式检测残留脏值。空表不算满分。", None, None
    dirty: set[tuple[int, str]] = set()
    filled = 0
    for index, row in enumerate(rows):
        for key, value in row.items():
            if key in AUDIT_COLUMNS or str(key).startswith("raw_"):
                continue
            text = "" if value is None else str(value).strip()
            if _is_missing_cell(text):
                continue
            filled += 1
            if text.upper() in DIRTY_TOKENS:
                dirty.add((index, str(key)))
    if filled <= 0:
        return None, "没有已填写的业务单元格，不能把空表或全缺失表算成清洗满分。", None, None
    remaining = len(dirty) / filled
    score = 1.0 - remaining
    cleaned = int(getattr(getattr(task, "readiness", None), "cleaned_value_count", 0) or 0)
    reason = (
        f"已填业务格 {filled} 个，残留脏词 {len(dirty)} 个；已执行清洗 {cleaned} 处。"
        "这不是字段覆盖，也不是 Hospital/Flights/Beers 的外部 Cell-F1。"
    )
    if score >= 1.0:
        return score, reason, "未发现错误清洗", "已填单元格里没有 NA/NULL 等脏残留；必要字段仍可能缺失。"
    return score, reason, f"{score * 100:.1f}%", reason


def _retrieval_ndcg(task: Any) -> tuple[float | None, str]:
    matches = list(getattr(getattr(task, "competition_report", None), "rag_matches", None) or [])
    if not matches:
        return None, "还没有候选匹配表。先跑真实数据任务。"
    ranked = sorted(matches, key=lambda item: float(getattr(item, "match_score", 0) or 0), reverse=True)
    relevances = [1.0 if getattr(item, "selected", False) else 0.0 for item in ranked]
    if not any(relevances):
        return None, "候选已排序但没有最终选用项，nDCG@10 无相关项。"
    score = float(TOOLKIT.ndcg_at_k(relevances, 10))
    return score, f"按工具包 ndcg_at_k 公式，k=10；候选 {len(ranked)} 个，选用 {int(sum(relevances))} 个。不是 BEIR SciFact 外部榜。"


def _schema_f1(task: Any) -> tuple[float | None, str]:
    design = getattr(task, "study_design", None)
    variables = list(getattr(design, "required_variables", None) or [])
    required = {str(item.variable_id) for item in variables if getattr(item, "required", False) and getattr(item, "variable_id", None)}
    predicted = {
        str(item.variable_id)
        for item in variables
        if getattr(item, "variable_id", None) and (getattr(item, "available", False) or list(getattr(item, "matched_fields", None) or []))
    }
    if not required:
        return None, "研究方案没有标记必选变量，Schema Matching F1 无法计算。"
    stats = TOOLKIT.precision_recall_f1(required, predicted)
    return float(stats["f1"]), (
        f"以本任务 Evaluation Contract 的必选变量为 Gold，已匹配变量为预测；"
        f"P={stats['precision']:.3f} R={stats['recall']:.3f}。不是 Valentine 外部榜。"
    )


def _entity_f1(task: Any) -> tuple[float | None, str]:
    alignment = getattr(task, "data_alignment", None)
    if alignment is None:
        return None, "没有身份对齐报告。"
    patients = int(getattr(alignment, "patient_count", 0) or 0)
    unresolved = int(getattr(alignment, "unresolved_identity_row_count", 0) or 0)
    duplicates = int(getattr(alignment, "duplicate_identity_count", 0) or 0)
    if patients <= 0:
        return None, "对齐报告中没有患者实体。"
    tp = max(patients - unresolved - duplicates, 0)
    stats = _f1_from_counts(tp, duplicates, unresolved)
    return float(stats["f1"]), (
        f"以本队列患者实体为 Gold：唯一对齐 {tp}，重复 {duplicates}，未决 {unresolved}。"
        "低置信度不计入自动合并。不是 DBLP-ACM / Walmart-Amazon 外部榜。"
    )


def _fitness_score(task: Any) -> tuple[float | None, str]:
    report = getattr(getattr(getattr(task, "competition_report", None), "unified_evaluation", None), "task_adaptive_fitness", None)
    if report is None:
        return None, "还没有 Task-Adaptive Fitness 报告。"
    dimensions = list(getattr(report, "dimensions", None) or [])
    values = [float(item.value) * 4 for item in dimensions if getattr(item, "value", None) is not None]
    if len(values) >= 4:
        score = float(TOOLKIT.geometric_fitness(values[:4]))
        return score, "工具包 geometric_fitness：研究相关性、分析充分性、可追溯性、可复用性四维 0–4 分几何平均×100。"
    existing = getattr(report, "fitness_score", None)
    if existing is None:
        return None, "Fitness 维度不足，无法按工具包几何平均汇总。"
    return float(existing), "沿用已计算的任务适配分；维度不足 4 项时不做工具包几何平均。"


def run_toolkit_evaluation(task: Any | None) -> dict[str, Any]:
    if task is None:
        return {
            "available": False,
            "status": "待运行",
            "notice": "先在本工作台跑一次真实数据任务，再按统一评测方案工具包的公式计算清洗、检索、整合、Fitness 和 Quality Gate。",
            "quality_gate": None,
            "metrics": [
                _metric("cleaning_retention", "清洗残留清除率", None, target=0.9, reason="需本工作台宽表"),
                _metric("retrieval_ndcg@10", "检索 nDCG@10", None, target=0.5, reason="需候选匹配表"),
                _metric("integration_macro_f1", "整合 Macro-F1", None, target=0.7, reason="需研究方案与对齐报告"),
                _metric("task_fitness", "任务适配 Fitness", None, unit="score", target=70.0, reason="需 Fitness 四维"),
                _metric("quality_gate", "Quality Gate", None, unit="score", target=1.0, reason="需质量门报告"),
            ],
        }
    cleaning, cleaning_note, cleaning_headline, cleaning_meaning = _cleaning_score(task)
    ndcg, ndcg_note = _retrieval_ndcg(task)
    schema, schema_note = _schema_f1(task)
    entity, entity_note = _entity_f1(task)
    fitness, fitness_note = _fitness_score(task)
    integration = None if schema is None or entity is None else float(TOOLKIT.integration_macro_f1(schema, entity))
    gate = getattr(getattr(task, "quality_gate_report", None), "overall", None)
    gate_value = {"PASS": 1.0, "REVIEW": 0.5, "REJECT": 0.0}.get(str(gate or "").upper())
    integration_reason = (
        f"内部汇总 (Schema F1={schema:.3f} + Entity F1={entity:.3f})/2。不是行业标准指标。"
        if integration is not None
        else "；".join(item for item in (schema_note, entity_note) if item)
    )
    metrics = [
        _metric(
            "cleaning_retention",
            "清洗残留清除率",
            cleaning,
            target=0.9,
            reason=cleaning_note,
            headline=cleaning_headline,
            plain_meaning=cleaning_meaning,
        ),
        _metric("retrieval_ndcg@10", "检索 nDCG@10", ndcg, target=0.5, reason=ndcg_note),
        _metric("integration_macro_f1", "整合 Macro-F1", integration, target=0.7, reason=integration_reason),
        _metric("task_fitness", "任务适配 Fitness", fitness, unit="score", target=70.0, reason=fitness_note),
        _metric(
            "quality_gate",
            "Quality Gate",
            gate_value,
            unit="score",
            target=1.0,
            reason=f"工具包门控输出 {gate or '未判定'}（PASS=1 / REVIEW=0.5 / REJECT=0），不是综合打分。",
        ),
    ]
    measured = sum(1 for item in metrics if item.value is not None)
    return {
        "available": measured > 0,
        "status": "已计算" if measured else "待运行",
        "notice": (
            f"按统一评测方案工具包对本工作台任务 {getattr(task, 'task_id', '')} 计算："
            "清洗残留、nDCG@10、Schema/Entity Macro-F1、Task-Adaptive Fitness、Quality Gate。"
            "Hospital / BEIR / Valentine 外部榜未下载，故不填写那些基准分数。"
        ),
        "quality_gate": gate,
        "metrics": metrics,
    }
