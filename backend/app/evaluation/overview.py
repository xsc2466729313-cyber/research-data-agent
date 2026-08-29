from __future__ import annotations

import json
from math import log2
from pathlib import Path
from typing import Any

from pydantic import Field

from backend.app.models import ApiModel


class EvaluationProtocolStep(ApiModel):
    step_id: str
    title: str
    counterpart: str
    method: str
    how_to_run: str
    status: str


class OverviewMetric(ApiModel):
    key: str
    label: str
    value: float | None = None
    display_value: float | None = None
    target: float | None = None
    display_target: float | None = None
    unit: str = "percent"
    status: str
    reason: str
    headline: str | None = None
    plain_meaning: str | None = None


class RetrievalProbe(ApiModel):
    status: str
    cases: int = Field(ge=0)
    ranking_model: str
    metrics: list[OverviewMetric] = Field(default_factory=list)
    note: str


class TeamReferenceReport(ApiModel):
    available: bool = False
    status: str = "未接入"
    notice: str = ""
    metrics: list[OverviewMetric] = Field(default_factory=list)
    benchmark: RetrievalProbe | None = None


class ToolkitRunReport(ApiModel):
    available: bool = False
    status: str = "待运行"
    notice: str = ""
    quality_gate: str | None = None
    metrics: list[OverviewMetric] = Field(default_factory=list)


class DevelopmentSplitReport(ApiModel):
    available: bool = False
    unofficial: bool = True
    evaluation_id: str | None = None
    status: str = "未加载"
    notice: str = "development 分册实测不得填入正式 SDTI。"
    sdti: float | None = None
    retrieval_f1: float | None = None
    faithfulness: float | None = None
    traceability: float | None = None
    error_f1: float | None = None
    repair_accuracy: float | None = None
    publish_allowed: bool | None = None
    gate: str | None = None


class RetrievalLayerRow(ApiModel):
    dataset: str
    dataset_zh: str = ""
    n: int = Field(ge=0)
    bm25_ndcg: float | None = None
    bge_ndcg: float | None = None
    fusion_ndcg: float | None = None
    bge_delta: float | None = None
    bge_recall_100: float | None = None


class RetrievalLayerReport(ApiModel):
    available: bool = False
    dataset_count: int = 0
    query_count: int = 0
    title: str = "检索层：BM25 vs BGE vs 融合"
    note: str = ""
    bm25_macro: float | None = None
    bge_macro: float | None = None
    fusion_macro: float | None = None
    rows: list[RetrievalLayerRow] = Field(default_factory=list)


class OfficialRunInfo(ApiModel):
    can_run: bool = False
    has_score: bool = False
    evaluation_id: str | None = None
    endpoint: str = "/api/evaluation/official-run"
    notice: str = ""


class EvaluationOverview(ApiModel):
    evaluation_status: str
    official_metrics_allowed: bool
    notice: str
    protocol: list[EvaluationProtocolStep] = Field(default_factory=list)
    official_metrics: list[OverviewMetric] = Field(default_factory=list)
    retrieval_probe: RetrievalProbe
    team_reference: TeamReferenceReport = Field(default_factory=TeamReferenceReport)
    toolkit_run: ToolkitRunReport = Field(default_factory=ToolkitRunReport)
    development_split: DevelopmentSplitReport = Field(default_factory=DevelopmentSplitReport)
    retrieval_layer: RetrievalLayerReport = Field(default_factory=RetrievalLayerReport)
    last_task_id: str | None = None
    goldset_row_counts: dict[str, int] = Field(default_factory=dict)
    official_run: OfficialRunInfo = Field(default_factory=OfficialRunInfo)


PROTOCOL_STEPS = [
    EvaluationProtocolStep(
        step_id="01-subject-run",
        title="被测系统先真实跑题",
        counterpart="工具包：Full Agent 作为 subject，不自己当 Ground Truth",
        method="同一科研问题走完整 Agent：解析、检索、对齐、质量门。不根据评委模型改答案。",
        how_to_run="工作台选择真实数据模式，运行研究协议。",
        status="待运行",
    ),
    EvaluationProtocolStep(
        step_id="02-retrieval-ndcg",
        title="检索用 nDCG@10",
        counterpart="工具包主指标：nDCG@10",
        method="对本模型候选按匹配分排序，最终选用队列为相关项，用工具包 ndcg_at_k 计算。不是 BEIR SciFact 外部榜，也不是冻结 Gold Set Precision。",
        how_to_run="真实任务完成后刷新系统评测；本接口自动从最近一次任务的候选匹配表计算。",
        status="待运行",
    ),
    EvaluationProtocolStep(
        step_id="03-integration-fitness",
        title="整合 F1 与任务适配 Fitness",
        counterpart="工具包：Schema/Entity Macro-F1 + 四维几何平均 Fitness",
        method="必选变量匹配为 Schema Gold；患者唯一对齐/重复/未决为 Entity；Fitness 用研究相关性、分析充分性、可追溯性、可复用性。",
        how_to_run="一次完整任务会同时生成研究方案、对齐报告和 Fitness 合同摘要。",
        status="待运行",
    ),
    EvaluationProtocolStep(
        step_id="04-quality-gate",
        title="Quality Gate 输出门控",
        counterpart="工具包：PASS / REVIEW / REJECT，不做虚构总分",
        method="来源真实性、整合完整性、可追溯性、关键冲突、任务必要条件。消融对照来自同表反事实。",
        how_to_run="查看质量门面板；系统评测展示门控结果与同表消融。",
        status="待运行",
    ),
    EvaluationProtocolStep(
        step_id="05-freeze-sdti",
        title="冻结 Gold Set 后才算正式 SDTI",
        counterpart="工具包外部榜与项目 Gold Set 仍未接入",
        method="三张 Gold CSV 均非空并审核冻结后，才允许 POST /api/evaluation/run。Hospital/BEIR/Valentine 需按工具包脚本另下。",
        how_to_run="正式卷写入 goldset/templates 后，仍须对本卷采集系统观察并 POST /api/evaluation/run。外部基准见 evaluation_toolkit/scripts/download_all.ps1。",
        status="待正式评测",
    ),
]


OFFICIAL_METRIC_SPECS = [
    ("retrieval_precision", "检索精确率", 0.9, "percent", "Pr = TP/(TP+FP)，需冻结 Retrieval Gold"),
    ("retrieval_recall", "检索召回率", 0.9, "percent", "Rr = TP/(TP+FN)，需冻结 Retrieval Gold"),
    ("retrieval_f1", "检索 F1", 0.9, "percent", "2PR/(P+R)，Gold Set 空则未评测"),
    ("faithfulness", "Faithfulness", 0.95, "percent", "忠实保持原始医学语义的字段比例"),
    ("traceability", "Traceability", 1.0, "percent", "关键非空字段具备完整 Evidence 的比例"),
    ("error_precision", "Error Precision", 0.9, "percent", "需 Error Gold 含应检出错误与 clean control"),
    ("error_recall", "Error Recall", 0.9, "percent", "需 Error Gold"),
    ("error_f1", "Error F1", 0.9, "percent", "错误检测 F1"),
    ("repair_accuracy", "Repair Accuracy", 0.9, "percent", "自动修复后正确数 / 自动执行修复数"),
    ("sdti", "SDTI", 90.0, "score", "五分量几何平均×100；任一分量为空则 SDTI 未评测"),
]


def _dcg(relevances: list[float], k: int) -> float:
    return sum(rel / log2(index + 2) for index, rel in enumerate(relevances[:k]))


def _recall_at_k(ranked_relevant: list[int], k: int, total_relevant: int) -> float | None:
    if total_relevant <= 0:
        return None
    return sum(ranked_relevant[:k]) / total_relevant


def _ndcg_at_k(ranked_relevant: list[int], k: int) -> float | None:
    if not any(ranked_relevant):
        return None
    actual = _dcg([float(value) for value in ranked_relevant], k)
    ideal = _dcg(sorted((float(value) for value in ranked_relevant), reverse=True), k)
    if ideal <= 0:
        return None
    return actual / ideal


def retrieval_probe_from_matches(matches: list[Any]) -> RetrievalProbe:
    if not matches:
        return RetrievalProbe(
            status="待运行",
            cases=0,
            ranking_model="deterministic-rag-match",
            note="还没有本模型的候选匹配表。先跑真实数据任务。",
        )
    ranked = sorted(matches, key=lambda item: float(getattr(item, "match_score", 0) or 0), reverse=True)
    labels = [1 if getattr(item, "selected", False) else 0 for item in ranked]
    total_relevant = sum(labels)
    recall1 = _recall_at_k(labels, 1, total_relevant)
    recall3 = _recall_at_k(labels, 3, total_relevant)
    recall5 = _recall_at_k(labels, 5, total_relevant)
    ndcg3 = _ndcg_at_k(labels, 3)

    def metric(key: str, label: str, value: float | None) -> OverviewMetric:
        return OverviewMetric(
            key=key,
            label=label,
            value=value,
            display_value=None if value is None else value * 100,
            unit="percent",
            status="DEVELOPMENT_PROBE" if value is not None else "NOT_EVALUATED",
            reason="对本模型候选按匹配分排序，最终选用队列为相关项；不是冻结 Gold Set 成绩。",
        )

    return RetrievalProbe(
        status="已计算" if total_relevant else "无选用项",
        cases=len(ranked),
        ranking_model="deterministic-rag-match",
        metrics=[
            metric("recall@1", "Recall@1", recall1),
            metric("recall@3", "Recall@3", recall3),
            metric("recall@5", "Recall@5", recall5),
            metric("ndcg@3", "nDCG@3", ndcg3),
        ],
        note=(
            f"候选 {len(ranked)} 个，最终选用 {total_relevant} 个。"
            "方法对齐对照页的 Recall@k / nDCG，但排序来自本仓库确定性匹配分，评委不是 DeepSeek。"
        ),
    )


ROOT = Path(__file__).resolve().parents[3]
DEVELOPMENT_QWEN_METRICS = (
    ROOT
    / "goldset"
    / "breast_cancer"
    / "development"
    / "evaluation_runs"
    / "development-xsc-qwen-live-20260829"
    / "metrics.json"
)
# Optional Qwen-reviewed retrieval artifact; never treated as a frozen Gold Set score.
TEAM_BENCHMARK_PATH = ROOT / "evaluation" / "results_qwen_review" / "comparison.json"
RETRIEVAL_LAYER_PATH = ROOT / "evaluation" / "vnext_retrieval_calibrated_macro_20260828.json"
RETRIEVAL_LAYER_DATASETS = (
    ("beir_scifact", "SciFact", "科学事实"),
    ("beir_nfcorpus", "NFCorpus", "生物医学文献"),
    ("beir_scidocs", "SciDocs", "科学论文"),
    ("beir_arguana", "ArguAna", "论辩检索"),
    ("beir_fiqa", "FiQA", "财经问答"),
)
RETRIEVAL_LAYER_METHODS = {
    "bm25": "project_bm25_tuned_v2",
    "bge": "vnext_bge_small_en_v1_5",
    "fusion": "vnext_bm25_bge_fusion_v1",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_team_reference() -> TeamReferenceReport:
    benchmark = _load_json(TEAM_BENCHMARK_PATH)
    if not benchmark:
        return TeamReferenceReport(
            available=False,
            status="未接入",
            notice="未找到当前千问评审产物；旧 AI 代理核心指标不会接入当前总览。",
        )
    summary = ((benchmark or {}).get("summary") or {})
    bench_metrics = summary.get("metrics") or {}
    probe_metrics = [
        OverviewMetric(
            key=key,
            label=label,
            value=bench_metrics.get(key),
            display_value=None if bench_metrics.get(key) is None else float(bench_metrics[key]) * 100,
            unit="percent",
            status="TEAM_REFERENCE",
            reason="来自 evaluation/results_qwen_review/comparison.json；仅作检索诊断。",
        )
        for key, label in (("recall@1", "Recall@1"), ("recall@3", "Recall@3"), ("recall@5", "Recall@5"), ("ndcg@3", "nDCG@3"))
    ]
    return TeamReferenceReport(
        available=True,
        status="TEAM_REFERENCE",
        notice="千问统一评审产物；不得作为冻结 Gold Set、正式 Faithfulness 或 SDTI。",
        metrics=[],
        benchmark=RetrievalProbe(
            status="已接入" if bench_metrics else "无检索对照",
            cases=int(summary.get("cases") or 0),
            ranking_model=str(summary.get("judge_model") or (benchmark or {}).get("metadata", {}).get("judge_model") or "qwen-plus"),
            metrics=probe_metrics,
            note=f"千问评审检索探针 {int(summary.get('cases') or 0)} 题；正式 Gold Set 仍未冻结。",
        ),
    )


def load_development_split() -> DevelopmentSplitReport:
    payload = _load_json(DEVELOPMENT_QWEN_METRICS)
    if not payload:
        return DevelopmentSplitReport()
    metrics = payload.get("metrics") or {}
    safety = payload.get("safety") or {}

    def _value(key: str) -> float | None:
        item = metrics.get(key) or {}
        value = item.get("value") if isinstance(item, dict) else None
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    return DevelopmentSplitReport(
        available=True,
        unofficial=True,
        evaluation_id=str(payload.get("evaluation_id") or "development-xsc-qwen-live-20260829"),
        status="DEVELOPMENT_ONLY",
        notice=(
            "千问 LIVE Agent 在 development 分册上的实测。不是 frozen_test，"
            "不得当作正式 SDTI。"
        ),
        sdti=_value("sdti"),
        retrieval_f1=_value("retrieval_f1"),
        faithfulness=_value("faithfulness"),
        traceability=_value("traceability"),
        error_f1=_value("error_f1"),
        repair_accuracy=_value("repair_accuracy"),
        publish_allowed=bool(safety.get("publish_allowed")) if "publish_allowed" in safety else None,
        gate=str(safety["gate"]) if safety.get("gate") else None,
    )


def _optional_float(payload: dict[str, Any] | None, key: str) -> float | None:
    if not payload:
        return None
    value = payload.get(key)
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def load_retrieval_layer() -> RetrievalLayerReport:
    payload = _load_json(RETRIEVAL_LAYER_PATH)
    if not payload:
        return RetrievalLayerReport()
    results = payload.get("results_by_dataset") or {}
    aggregate = payload.get("aggregate") or {}
    if not isinstance(results, dict):
        results = {}
    if not isinstance(aggregate, dict):
        aggregate = {}
    rows: list[RetrievalLayerRow] = []
    query_count = 0
    for dataset_id, label, label_zh in RETRIEVAL_LAYER_DATASETS:
        item = results.get(dataset_id) or {}
        if not isinstance(item, dict):
            continue
        bm25 = item.get(RETRIEVAL_LAYER_METHODS["bm25"]) or {}
        bge = item.get(RETRIEVAL_LAYER_METHODS["bge"]) or {}
        fusion = item.get(RETRIEVAL_LAYER_METHODS["fusion"]) or {}
        if not isinstance(bm25, dict):
            bm25 = {}
        if not isinstance(bge, dict):
            bge = {}
        if not isinstance(fusion, dict):
            fusion = {}
        n = int(bm25.get("query_count") or bge.get("query_count") or 0)
        query_count += n
        bm25_ndcg = _optional_float(bm25, "ndcg_at_10")
        bge_ndcg = _optional_float(bge, "ndcg_at_10")
        fusion_ndcg = _optional_float(fusion, "ndcg_at_10")
        bge_delta = None if bm25_ndcg is None or bge_ndcg is None else bge_ndcg - bm25_ndcg
        rows.append(
            RetrievalLayerRow(
                dataset=label,
                dataset_zh=label_zh,
                n=n,
                bm25_ndcg=bm25_ndcg,
                bge_ndcg=bge_ndcg,
                fusion_ndcg=fusion_ndcg,
                bge_delta=bge_delta,
                bge_recall_100=_optional_float(bge, "recall_at_100"),
            )
        )
    if not rows:
        return RetrievalLayerReport()
    bm25_row = aggregate.get(RETRIEVAL_LAYER_METHODS["bm25"])
    bge_row = aggregate.get(RETRIEVAL_LAYER_METHODS["bge"])
    fusion_row = aggregate.get(RETRIEVAL_LAYER_METHODS["fusion"])
    return RetrievalLayerReport(
        available=True,
        dataset_count=len(rows),
        query_count=query_count,
        title="检索层：BM25 vs BGE vs 融合",
        note=f"{len(rows)} 个公开检索集 · {query_count} 题",
        bm25_macro=_optional_float(bm25_row if isinstance(bm25_row, dict) else {}, "ndcg_at_10_macro"),
        bge_macro=_optional_float(bge_row if isinstance(bge_row, dict) else {}, "ndcg_at_10_macro"),
        fusion_macro=_optional_float(fusion_row if isinstance(fusion_row, dict) else {}, "ndcg_at_10_macro"),
        rows=rows,
    )


def official_unscored_metrics() -> list[OverviewMetric]:
    return [
        OverviewMetric(
            key=key,
            label=label,
            value=None,
            display_value=None,
            target=target if unit == "percent" else None,
            display_target=target * 100 if unit == "percent" else target,
            unit=unit,
            status="NOT_EVALUATED",
            reason=reason,
        )
        for key, label, target, unit, reason in OFFICIAL_METRIC_SPECS
    ]


def official_metrics_from_payload(payload: dict[str, Any]) -> list[OverviewMetric]:
    metrics = payload.get("metrics") or {}
    rows: list[OverviewMetric] = []
    for key, label, target, unit, reason in OFFICIAL_METRIC_SPECS:
        item = metrics.get(key) or {}
        if not isinstance(item, dict):
            item = {}
        raw = item.get("value")
        try:
            value = None if raw is None else float(raw)
        except (TypeError, ValueError):
            value = None
        status = str(item.get("status") or ("EVALUATED" if value is not None else "NOT_EVALUATED"))
        if unit == "percent":
            display = None if value is None else value * 100
            display_target = target * 100
        else:
            display = value
            display_target = target
        rows.append(
            OverviewMetric(
                key=key,
                label=label,
                value=value,
                display_value=display,
                target=target if unit == "percent" else None,
                display_target=display_target,
                unit=unit,
                status=status,
                reason=str(item.get("reason") or reason),
            )
        )
    return rows


def build_evaluation_overview(
    *,
    latest_task: Any | None = None,
    goldset_row_counts: dict[str, int] | None = None,
) -> EvaluationOverview:
    counts = goldset_row_counts or {}
    gold_ready = all(int(counts.get(name, 0) or 0) > 0 for name in ("retrieval_gold.csv", "field_gold.csv", "error_gold.csv"))
    protocol = [step.model_copy() for step in PROTOCOL_STEPS]
    matches = list(getattr(getattr(latest_task, "competition_report", None), "rag_matches", None) or [])
    probe = retrieval_probe_from_matches(matches)
    if latest_task is not None:
        protocol[0] = protocol[0].model_copy(update={"status": "已完成"})
        protocol[1] = protocol[1].model_copy(update={"status": probe.status})
        protocol[2] = protocol[2].model_copy(update={"status": "已计算"})
        protocol[3] = protocol[3].model_copy(update={"status": str(getattr(getattr(latest_task, "quality_gate_report", None), "overall", None) or "已观测")})
    from backend.app.evaluation.official_run import latest_official_metrics
    from backend.app.evaluation.toolkit_run import run_toolkit_evaluation

    official_payload = latest_official_metrics()
    sdti_item = ((official_payload or {}).get("metrics") or {}).get("sdti") or {}
    official_has_score = (
        gold_ready
        and isinstance(sdti_item, dict)
        and sdti_item.get("value") is not None
    )
    if gold_ready and official_has_score:
        protocol[4] = protocol[4].model_copy(
            update={
                "status": "已出正式分",
                "how_to_run": (
                    "正式卷已对本套 official_candidate 跑过系统观察与评分。"
                    "可再点「开始正式评测」重跑；development 分册成绩不得填入。"
                ),
            }
        )
    elif gold_ready:
        protocol[4] = protocol[4].model_copy(
            update={
                "status": "可提交正式评测",
                "how_to_run": (
                    "正式卷已写入 goldset/templates。点「开始正式评测」采集系统观察并出正式 SDTI；"
                    "development 分册成绩不得填入。"
                ),
            }
        )
    toolkit_payload = run_toolkit_evaluation(latest_task)
    toolkit = ToolkitRunReport(
        available=bool(toolkit_payload["available"]),
        status=str(toolkit_payload["status"]),
        notice=str(toolkit_payload["notice"]),
        quality_gate=toolkit_payload.get("quality_gate"),
        metrics=list(toolkit_payload.get("metrics") or []),
    )
    if official_has_score:
        official_metrics = official_metrics_from_payload(official_payload or {})
        evaluation_status = str(official_payload.get("evaluation_status") or "EVALUATED")
        notice = (
            "评测方法对齐统一评测方案工具包：清洗、nDCG@10、Schema/Entity Macro-F1、"
            "Task-Adaptive Fitness、Quality Gate。正式 SDTI 来自对本套 official_candidate 的系统观察，"
            "不是 development 分册，也不是 sealed frozen_test。"
        )
        official_run = OfficialRunInfo(
            can_run=True,
            has_score=True,
            evaluation_id=str(official_payload.get("evaluation_id") or ""),
            notice="正式卷已跑过评测。可重新跑以更新观察。",
        )
    else:
        official_metrics = official_unscored_metrics()
        evaluation_status = "NOT_EVALUATED"
        notice = (
            "评测方法对齐统一评测方案工具包：清洗、nDCG@10、Schema/Entity Macro-F1、"
            "Task-Adaptive Fitness、Quality Gate。数值只来自本工作台最近一次真实任务和工具包公式。"
            + (
                "正式 Gold Set 已写入 goldset/templates。点「开始正式评测」对本卷采集观察并出正式 SDTI；"
                "development 分册实测单独展示且不得进正式栏。"
                if gold_ready
                else "官方 Gold Set SDTI 在模板为空时无法计算；development 分册实测单独展示且不得进正式栏。"
            )
        )
        official_run = OfficialRunInfo(
            can_run=gold_ready,
            has_score=False,
            notice="正式考卷已就位时，点「开始正式评测」会真跑采集与评分。" if gold_ready else "正式考卷尚未写入入口。",
        )
    return EvaluationOverview(
        evaluation_status=evaluation_status,
        official_metrics_allowed=official_has_score,
        notice=notice,
        protocol=protocol,
        official_metrics=official_metrics,
        retrieval_probe=probe,
        team_reference=TeamReferenceReport(available=False, status="已隐藏", notice="页面不再展示团队压缩包探针。"),
        toolkit_run=toolkit,
        development_split=load_development_split(),
        retrieval_layer=load_retrieval_layer(),
        last_task_id=getattr(latest_task, "task_id", None),
        goldset_row_counts=counts,
        official_run=official_run,
    )
