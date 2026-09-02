"""Generate the Chinese-only quantitative figures used by the judge-facing paper.

All values are read from the repository's machine-readable evaluation artifacts.
The script changes presentation only; it does not recalculate or alter metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "docs" / "images"
RUN_ROOT = ROOT / "goldset" / "breast_cancer" / "official_candidate" / "evaluation_runs"
BASELINE_PATH = RUN_ROOT / "official-candidate-20260829T132222Z" / "metrics.json"
CURRENT_PATH = RUN_ROOT / "official-candidate-qwen-live-audited-final-20260830" / "metrics.json"
SUMMARY_PATH = ROOT / "evaluation" / "reports" / "qwen38_20260829" / "report_metrics_summary.json"
PUBLIC_COMPARISON_PATH = ROOT / "evaluation" / "PUBLIC_DATASET_COMPARISON_20260902.json"

FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")
FONT = FontProperties(fname=str(FONT_PATH)) if FONT_PATH.exists() else FontProperties()

BLUE = "#2563EB"
TEAL = "#0F766E"
ORANGE = "#D97706"
SLATE = "#64748B"
GRID = "#E2E8F0"
TEXT = "#0F172A"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def style_axis(ax: plt.Axes, *, grid_axis: str = "y") -> None:
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.9, zorder=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#94A3B8")
    ax.tick_params(colors="#475569")


def add_value_labels(ax: plt.Axes, bars, *, digits: int = 2, offset: float = 0.018) -> None:
    for bar in bars:
        value = float(bar.get_height())
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + offset,
            f"{value:.{digits}f}",
            ha="center",
            va="bottom",
            fontsize=10,
            color=TEXT,
            fontproperties=FONT,
        )


def save_system_metrics() -> Path:
    baseline = load(BASELINE_PATH)
    current = load(CURRENT_PATH)
    metrics = [
        ("retrieval_f1", "检索综合值"),
        ("faithfulness", "字段忠实度"),
        ("traceability", "来源可追溯率"),
        ("error_f1", "错误识别综合值"),
        ("repair_accuracy", "自动修复正确率"),
    ]
    labels = [label for _, label in metrics]
    old_values = [float(baseline["metrics"][key]["value"]) for key, _ in metrics]
    new_values = [float(current["metrics"][key]["value"]) for key, _ in metrics]

    fig, ax = plt.subplots(figsize=(13.2, 7.3), facecolor="white")
    y = np.arange(len(labels))
    h = 0.30
    old_bars = ax.barh(y + h / 2, old_values, h, color="#CBD5E1", label="历史版本", zorder=3)
    new_bars = ax.barh(y - h / 2, new_values, h, color=BLUE, label="当前版本", zorder=3)
    for bars in (old_bars, new_bars):
        for bar in bars:
            value = float(bar.get_width())
            ax.text(
                min(value + 0.015, 1.055),
                bar.get_y() + bar.get_height() / 2,
                f"{value:.2f}",
                va="center",
                ha="left",
                fontsize=10,
                color=TEXT,
                fontproperties=FONT,
            )
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.10)
    ax.set_xlabel("指标值（0—1，越高越好）", fontproperties=FONT, fontsize=11)
    style_axis(ax, grid_axis="x")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False, prop=FONT)

    fig.suptitle("五项质量指标的版本对照", x=0.08, y=0.955, ha="left", fontsize=19,
                 fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.900, "在同一组未封存审核样例上复测，只比较系统整体变化", ha="left", fontsize=11,
             color="#475569", fontproperties=FONT)
    old_sdti = float(baseline["metrics"]["sdti"]["value"])
    new_sdti = float(current["metrics"]["sdti"]["value"])
    fig.text(0.08, 0.035, f"科研数据可信整合指数：{old_sdti:.2f}  →  {new_sdti:.2f}", ha="left",
             fontsize=12, color="#0F766E", fontweight="bold", fontproperties=FONT)
    fig.text(0.92, 0.050, "候选观察：仍有 5 个任务需复核", ha="right", fontsize=9.5,
             color="#B91C1C", fontweight="bold", fontproperties=FONT)
    fig.text(0.92, 0.022, "暂不自动发布，不是冻结正式成绩", ha="right", fontsize=9.5,
             color="#B91C1C", fontproperties=FONT)
    fig.subplots_adjust(left=0.20, right=0.96, top=0.80, bottom=0.20)
    path = IMAGE_DIR / "system-metrics-comparison-cn-20260831.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_planner_comparison(summary: dict) -> Path:
    qwen = summary["model_comparison"]["qwen"]
    deepseek = summary["model_comparison"]["deepseek"]
    labels = ["前三条来源覆盖率", "首个相关来源排序得分", "前三条来源排序质量"]
    qwen_values = [qwen["recall_at_3"], qwen["mrr_at_3"], qwen["ndcg_at_3"]]
    deep_values = [deepseek["recall_at_3"], deepseek["mrr_at_3"], deepseek["ndcg_at_3"]]

    fig = plt.figure(figsize=(13.5, 7.2), facecolor="white")
    grid = fig.add_gridspec(1, 2, width_ratios=[2.5, 1.0], wspace=0.22)
    ax = fig.add_subplot(grid[0, 0])
    ax_time = fig.add_subplot(grid[0, 1])
    x = np.arange(len(labels))
    width = 0.32
    qbars = ax.bar(x - width / 2, qwen_values, width, color=BLUE, label="千问 3.8-Max", zorder=3)
    dbars = ax.bar(x + width / 2, deep_values, width, color=ORANGE, label="DeepSeek 对照组", zorder=3)
    add_value_labels(ax, qbars)
    add_value_labels(ax, dbars)
    ax.set_ylim(0, 1.16)
    ax.set_xticks(x, labels, fontproperties=FONT, fontsize=10.5)
    ax.set_ylabel("指标值（0—1，越高越好）", fontproperties=FONT, fontsize=10.5)
    style_axis(ax)
    ax.legend(loc="upper center", ncol=2, frameon=False, prop=FONT)

    times = [qwen["avg_latency_ms"] / 1000, deepseek["avg_latency_ms"] / 1000]
    tbars = ax_time.bar(["千问\n3.8-Max", "DeepSeek\n对照组"], times,
                        color=[BLUE, ORANGE], zorder=3)
    for bar, value in zip(tbars, times, strict=True):
        ax_time.text(bar.get_x() + bar.get_width() / 2, value + 0.6, f"{value:.2f} 秒",
                     ha="center", va="bottom", fontsize=10, color=TEXT, fontproperties=FONT)
    ax_time.set_ylim(0, max(times) * 1.27)
    ax_time.set_ylabel("平均完成时间（越低越好）", fontproperties=FONT, fontsize=10.5)
    ax_time.set_xticks([0, 1], ["千问\n3.8-Max", "DeepSeek\n对照组"], fontproperties=FONT, fontsize=10)
    style_axis(ax_time)

    fig.suptitle("问题规划模型的单因素对照", x=0.07, y=0.958, ha="left", fontsize=19,
                 fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.07, 0.902, "两种模型各完成 3 道题，每题运行 3 次；数据接口、规则和调用上限一致，实际调用由规划决定",
             ha="left", fontsize=11, color="#475569", fontproperties=FONT)
    fig.text(0.07, 0.045, "千问的来源排序更稳定；DeepSeek 的平均完成时间更短。当前系统优先保证来源选得准。",
             ha="left", fontsize=10.3, color="#0F766E", fontweight="bold", fontproperties=FONT)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.79, bottom=0.17)
    path = IMAGE_DIR / "planner-model-comparison-cn-20260831.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_retrieval_comparison(summary: dict, public_summary: dict) -> Path:
    methods = summary["retrieval"]["methods"]
    current = public_summary["retrieval"]["macro"]
    method_values = [
        methods[0],
        methods[1],
        methods[2],
        {
            "ndcg_at_10": current["project_ndcg_at_10"],
            "recall_at_100": current["project_recall_at_100"],
            "mrr_at_10": current["project_mrr_at_10"],
        },
    ]
    labels = [
        "公开基线：BM25",
        "公开基线：BGE-small\n-en-v1.5",
        "本项目历史方法：\nBM25+BGE",
        "本项目当前方法：\nBM25+BGE 名次融合",
    ]
    metric_keys = ["ndcg_at_10", "recall_at_100", "mrr_at_10"]
    metric_labels = ["前十条结果排序质量", "前 100 条结果召回率", "首个相关结果排序得分"]
    colors = [BLUE, TEAL, ORANGE]

    fig, ax = plt.subplots(figsize=(13.4, 7.3), facecolor="white")
    x = np.arange(len(labels))
    width = 0.23
    for index, (key, metric_label, color) in enumerate(zip(metric_keys, metric_labels, colors, strict=True)):
        values = [float(method[key]) for method in method_values]
        bars = ax.bar(x + (index - 1) * width, values, width, label=metric_label, color=color, zorder=3)
        add_value_labels(ax, bars, digits=3, offset=0.012)
    ax.set_ylim(0, 0.76)
    ax.set_xticks(x, labels, fontproperties=FONT, fontsize=11)
    ax.set_ylabel("指标值（越高越好）", fontproperties=FONT, fontsize=11)
    style_axis(ax)
    ax.legend(loc="upper center", ncol=3, frameon=False, prop=FONT)
    fig.suptitle("公开检索基线与本项目方法对照", x=0.08, y=0.958, ha="left", fontsize=19,
                 fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.902, f"公开基线：BM25、BGE；本项目方法：历史分数融合与当前名次融合，共 {summary['retrieval']['query_count']:,} 条查询",
             ha="left", fontsize=11, color="#475569", fontproperties=FONT)
    fig.text(0.08, 0.055, "本项目当前方法按开发集确定 BM25+BGE 名次融合，nDCG@10 宏平均为 0.3915。",
             ha="left", fontsize=10.0, color="#0F766E", fontweight="bold", fontproperties=FONT)
    fig.text(0.08, 0.025, "公开基线 BGE 的 nDCG@10 宏平均为 0.3880；本项目当前方法提升 0.0035。",
             ha="left", fontsize=9.8, color="#475569", fontproperties=FONT)
    fig.subplots_adjust(left=0.09, right=0.96, top=0.80, bottom=0.18)
    path = IMAGE_DIR / "retrieval-method-comparison-cn-20260831.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_query_strategy(summary: dict) -> Path:
    methods = {item["method_id"]: item for item in summary["query_ablation"]["methods"]}
    raw = methods["A_raw"]
    combined = methods["E_rules_qwen"]
    labels = ["前十条结果排序质量", "前 100 条结果召回率", "首个相关结果排序得分"]
    keys = ["ndcg_at_10", "recall_at_100", "mrr_at_10"]
    raw_values = [float(raw[key]) for key in keys]
    combined_values = [float(combined[key]) for key in keys]

    fig, ax = plt.subplots(figsize=(12.8, 6.9), facecolor="white")
    x = np.arange(len(labels))
    width = 0.33
    r_bars = ax.bar(x - width / 2, raw_values, width, color=BLUE, label="保留原问题", zorder=3)
    c_bars = ax.bar(x + width / 2, combined_values, width, color=ORANGE, label="规则与千问组合补充", zorder=3)
    add_value_labels(ax, r_bars, digits=3, offset=0.012)
    add_value_labels(ax, c_bars, digits=3, offset=0.012)
    ax.set_ylim(0, 0.68)
    ax.set_xticks(x, labels, fontproperties=FONT, fontsize=11)
    ax.set_ylabel("指标值（越高越好）", fontproperties=FONT, fontsize=11)
    style_axis(ax)
    ax.legend(loc="upper center", ncol=2, frameon=False, prop=FONT)
    fig.suptitle("查询表达方式决定“前排准确”还是“深层覆盖”", x=0.08, y=0.958, ha="left",
                 fontsize=19, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.902, f"固定检索方法与语料，只比较查询表达；共 {summary['query_ablation']['query_count']} 条查询",
             ha="left", fontsize=11, color="#475569", fontproperties=FONT)
    fig.text(0.08, 0.045, "默认保留原问题以保证前排质量；只有目标来源不足时，才启用组合补充以扩大覆盖。",
             ha="left", fontsize=10.3, color="#0F766E", fontweight="bold", fontproperties=FONT)
    fig.subplots_adjust(left=0.09, right=0.96, top=0.80, bottom=0.19)
    path = IMAGE_DIR / "query-strategy-comparison-cn-20260831.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["axes.unicode_minus"] = False
    summary = load(SUMMARY_PATH)
    public_summary = load(PUBLIC_COMPARISON_PATH)
    outputs = [
        save_system_metrics(),
        save_planner_comparison(summary),
        save_retrieval_comparison(summary, public_summary),
        save_query_strategy(summary),
    ]
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
