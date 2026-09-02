"""Build the planner-model comparison figure from the saved Qwen 3.8 report."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "evaluation" / "reports" / "qwen38_20260829" / "report_metrics_summary.json"
OUTPUT_PATH = ROOT / "docs" / "images" / "planner-model-comparison-20260831.png"


def main() -> None:
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    comparison = payload["model_comparison"]
    qwen = comparison["qwen"]
    deepseek = comparison["deepseek"]

    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = FontProperties(fname=str(font_path)) if font_path.exists() else FontProperties()
    plt.rcParams["axes.unicode_minus"] = False

    metric_labels = ["Recall@3", "MRR@3", "nDCG@3"]
    qwen_values = [qwen["recall_at_3"], qwen["mrr_at_3"], qwen["ndcg_at_3"]]
    deepseek_values = [
        deepseek["recall_at_3"],
        deepseek["mrr_at_3"],
        deepseek["ndcg_at_3"],
    ]

    fig = plt.figure(figsize=(12.8, 6.9), facecolor="white")
    grid = fig.add_gridspec(1, 2, width_ratios=[2.4, 1.0], wspace=0.22)
    ax = fig.add_subplot(grid[0, 0])
    ax_latency = fig.add_subplot(grid[0, 1])

    x = np.arange(len(metric_labels))
    width = 0.32
    qwen_bars = ax.bar(
        x - width / 2,
        qwen_values,
        width,
        color="#2F6BDE",
        edgecolor="#1E3A8A",
        linewidth=1.0,
        label="Qwen3.8-Max",
        zorder=3,
    )
    deepseek_bars = ax.bar(
        x + width / 2,
        deepseek_values,
        width,
        color="#F4C26B",
        edgecolor="#9A6700",
        linewidth=1.0,
        hatch="//",
        label="DeepSeek 替换组",
        zorder=3,
    )

    for bars in (qwen_bars, deepseek_bars):
        for bar in bars:
            value = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.025,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=10,
                color="#111827",
                fontproperties=font,
            )

    ax.set_xticks(x, metric_labels, fontproperties=font, fontsize=11)
    ax.set_ylim(0, 1.16)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("来源排序指标（0—1，越高越好）", fontproperties=font, fontsize=10.5)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8, zorder=1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#94A3B8")
    ax.tick_params(colors="#475569")
    ax.legend(loc="upper center", ncol=2, frameon=False, prop=font)

    methods = ["Qwen3.8-Max", "DeepSeek\n替换组"]
    latency_seconds = [qwen["avg_latency_ms"] / 1000, deepseek["avg_latency_ms"] / 1000]
    latency_bars = ax_latency.bar(
        methods,
        latency_seconds,
        color=["#2F6BDE", "#F4C26B"],
        edgecolor=["#1E3A8A", "#9A6700"],
        linewidth=1.0,
        zorder=3,
    )
    latency_bars[1].set_hatch("//")
    for bar, value in zip(latency_bars, latency_seconds, strict=True):
        ax_latency.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.7,
            f"{value:.2f}s",
            ha="center",
            va="bottom",
            fontsize=10,
            color="#111827",
            fontproperties=font,
        )
    ax_latency.set_ylim(0, max(latency_seconds) * 1.26)
    ax_latency.set_ylabel("平均任务延迟（秒，越低越好）", fontproperties=font, fontsize=10.5)
    ax_latency.set_xticks(range(len(methods)), methods, fontproperties=font, fontsize=10)
    ax_latency.grid(axis="y", color="#E5E7EB", linewidth=0.8, zorder=1)
    ax_latency.spines[["top", "right"]].set_visible(False)
    ax_latency.spines[["left", "bottom"]].set_color("#94A3B8")
    ax_latency.tick_params(colors="#475569")

    fig.suptitle(
        "中间规划模型替换实验",
        x=0.07,
        y=0.965,
        ha="left",
        fontsize=18,
        fontweight="bold",
        color="#0F172A",
        fontproperties=font,
    )
    fig.text(
        0.07,
        0.905,
        "3 条乳腺癌科研题 × 每题 3 次 × 2 组；只替换问题解析、规划与工具选择模型",
        ha="left",
        fontsize=10.5,
        color="#475569",
        fontproperties=font,
    )
    fig.text(
        0.07,
        0.055,
        "两组均完成 9/9 次运行；Qwen 的 top-3 来源排序更稳定，DeepSeek 的平均延迟更低。小样本不外推通用排名。",
        ha="left",
        fontsize=9.8,
        color="#7C2D12",
        fontweight="bold",
        fontproperties=font,
    )
    fig.text(
        0.93,
        0.025,
        "来源：evaluation/reports/qwen38_20260829/report_metrics_summary.json",
        ha="right",
        fontsize=8.8,
        color="#64748B",
        fontproperties=font,
    )

    fig.subplots_adjust(left=0.075, right=0.96, top=0.80, bottom=0.17)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
