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


class EvaluationOverview(ApiModel):
    evaluation_status: str
    official_metrics_allowed: bool
    notice: str
    protocol: list[EvaluationProtocolStep] = Field(default_factory=list)
    official_metrics: list[OverviewMetric] = Field(default_factory=list)
    retrieval_probe: RetrievalProbe
    team_reference: TeamReferenceReport = Field(default_factory=TeamReferenceReport)
    toolkit_run: ToolkitRunReport = Field(default_factory=ToolkitRunReport)
    last_task_id: str | None = None
    last_model_test_id: str | None = None
    goldset_row_counts: dict[str, int] = Field(default_factory=dict)


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
        how_to_run="先填 goldset/templates。外部基准见 evaluation_toolkit/scripts/download_all.ps1。",
        status="阻断中",
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
# Team zip evaluation artifacts; never treated as frozen Gold Set scores.
TEAM_CORE_PATH = ROOT / "evaluation" / "ai_provisional_core_metrics.json"
TEAM_BENCHMARK_PATH = ROOT / "evaluation" / "results_deepseek" / "comparison.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_team_reference() -> TeamReferenceReport:
    core = _load_json(TEAM_CORE_PATH)
    benchmark = _load_json(TEAM_BENCHMARK_PATH)
    if not core and not benchmark:
        return TeamReferenceReport(
            available=False,
            status="未接入",
            notice="未找到团队评测压缩包中的 evaluation/ 结果文件。",
        )
    label_map = {key: label for key, label, _target, _unit, _reason in OFFICIAL_METRIC_SPECS}
    metrics: list[OverviewMetric] = []
    raw_metrics = (core or {}).get("metrics") or {}
    for key, label, target, unit, _reason in OFFICIAL_METRIC_SPECS:
        item = raw_metrics.get(key) or {}
        value = item.get("value")
        display = None if value is None else (value * 100 if unit == "percent" else value)
        metrics.append(
            OverviewMetric(
                key=key,
                label=label_map.get(key, key),
                value=value,
                display_value=display,
                target=target if unit == "percent" else None,
                display_target=target * 100 if unit == "percent" else target,
                unit=unit,
                status="TEAM_REFERENCE",
                reason=str(item.get("method") or "团队对照页评测产物，仅作方法对照，不是本仓库冻结 Gold Set 成绩。"),
            )
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
            reason="来自团队 evaluation/results_deepseek/comparison.json",
        )
        for key, label in (("recall@1", "Recall@1"), ("recall@3", "Recall@3"), ("recall@5", "Recall@5"), ("ndcg@3", "nDCG@3"))
    ]
    return TeamReferenceReport(
        available=True,
        status="TEAM_REFERENCE",
        notice=str((core or {}).get("notice") or "团队对照评测产物；不得作为本仓库官方 SDTI。"),
        metrics=metrics,
        benchmark=RetrievalProbe(
            status="已接入" if bench_metrics else "无检索对照",
            cases=int(summary.get("cases") or 0),
            ranking_model=str(summary.get("judge_model") or (benchmark or {}).get("metadata", {}).get("judge_model") or "deepseek-chat"),
            metrics=probe_metrics,
            note=f"团队 DeepSeek 探针 {int(summary.get('cases') or 0)} 题；正式 Gold Set 仍未冻结。",
        ),
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


def build_evaluation_overview(
    *,
    latest_task: Any | None = None,
    latest_model_test: Any | None = None,
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
    if gold_ready:
        protocol[4] = protocol[4].model_copy(update={"status": "可提交正式评测"})
    from backend.app.evaluation.toolkit_run import run_toolkit_evaluation

    toolkit_payload = run_toolkit_evaluation(latest_task)
    toolkit = ToolkitRunReport(
        available=bool(toolkit_payload["available"]),
        status=str(toolkit_payload["status"]),
        notice=str(toolkit_payload["notice"]),
        quality_gate=toolkit_payload.get("quality_gate"),
        metrics=list(toolkit_payload.get("metrics") or []),
    )
    notice = (
        "评测方法对齐统一评测方案工具包：清洗、nDCG@10、Schema/Entity Macro-F1、"
        "Task-Adaptive Fitness、Quality Gate。数值只来自本工作台最近一次真实任务和工具包公式。"
        "官方 Gold Set SDTI 在模板为空时保持未评测；不展示外部团队探针分数。"
    )
    return EvaluationOverview(
        evaluation_status="NOT_EVALUATED",
        official_metrics_allowed=False,
        notice=notice,
        protocol=protocol,
        official_metrics=official_unscored_metrics(),
        retrieval_probe=probe,
        team_reference=TeamReferenceReport(available=False, status="已隐藏", notice="页面不再展示团队压缩包探针。"),
        toolkit_run=toolkit,
        last_task_id=getattr(latest_task, "task_id", None),
        last_model_test_id=getattr(latest_model_test, "report_id", None),
        goldset_row_counts=counts,
    )
