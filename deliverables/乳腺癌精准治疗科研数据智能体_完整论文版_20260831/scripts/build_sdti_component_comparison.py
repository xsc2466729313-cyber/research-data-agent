"""Build the report chart from the two machine-readable official-candidate runs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "goldset" / "breast_cancer" / "official_candidate" / "evaluation_runs"
BASELINE_PATH = RUN_ROOT / "official-candidate-20260829T132222Z" / "metrics.json"
CANDIDATE_PATH = RUN_ROOT / "official-candidate-qwen-live-audited-final-20260830" / "metrics.json"
CANDIDATE_AUDIT_PATH = RUN_ROOT / "official-candidate-qwen-live-audited-final-20260830" / "AUDIT.json"
OUTPUT_PATH = ROOT / "docs" / "images" / "sdti-component-comparison-20260830.png"

METRICS = [
    ("retrieval_f1", "检索 F1"),
    ("faithfulness", "忠实率"),
    ("traceability", "可追溯率"),
    ("error_f1", "错误检测 F1"),
    ("repair_accuracy", "修复正确率"),
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    baseline = load(BASELINE_PATH)
    candidate = load(CANDIDATE_PATH)
    candidate_audit = load(CANDIDATE_AUDIT_PATH)

    keys = [key for key, _ in METRICS]
    labels = [label for _, label in METRICS]
    baseline_values = [baseline["metrics"][key]["value"] for key in keys]
    candidate_values = [candidate["metrics"][key]["value"] for key in keys]
    targets = [candidate["metrics"][key]["target"] for key in keys]

    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = FontProperties(fname=str(font_path)) if font_path.exists() else FontProperties()
    plt.rcParams["axes.unicode_minus"] = False

    y = np.arange(len(labels))
    bar_height = 0.28
    fig, ax = plt.subplots(figsize=(12.5, 7.2), facecolor="white")
    ax.set_facecolor("white")

    baseline_bars = ax.barh(
        y + bar_height / 2,
        baseline_values,
        height=bar_height,
        color="#D8DEE8",
        edgecolor="#64748B",
        linewidth=1.0,
        hatch="///",
        label="历史基线",
        zorder=2,
    )
    candidate_bars = ax.barh(
        y - bar_height / 2,
        candidate_values,
        height=bar_height,
        color="#2F6BDE",
        edgecolor="#1E3A8A",
        linewidth=1.0,
        label="严格千问 LIVE 候选",
        zorder=3,
    )
    ax.scatter(
        targets,
        y,
        marker="D",
        s=58,
        facecolors="white",
        edgecolors="#111827",
        linewidths=1.5,
        label="目标门槛",
        zorder=5,
    )

    for bars in (baseline_bars, candidate_bars):
        for bar in bars:
            value = bar.get_width()
            ax.text(
                min(value + 0.014, 1.055),
                bar.get_y() + bar.get_height() / 2,
                f"{value:.2f}",
                va="center",
                ha="left",
                color="#111827",
                fontsize=10,
                fontproperties=font,
            )

    ax.set_yticks(y, labels, fontproperties=font, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.10)
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("指标值（0—1，越高越好）", fontproperties=font, fontsize=11)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8, zorder=1)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#94A3B8")
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors="#475569")

    fig.suptitle(
        "五维质量指标：历史基线与严格千问 LIVE 候选观察",
        x=0.08,
        y=0.955,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color="#0F172A",
        fontproperties=font,
    )
    fig.text(
        0.08,
        0.895,
        "同一 official_candidate 审核卷；候选卷尚未封存，指标是回归观察而非最终竞赛成绩",
        ha="left",
        fontsize=10,
        color="#475569",
        fontproperties=font,
    )
    legend = ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.23),
        ncol=3,
        frameon=False,
        prop=font,
    )
    for text in legend.get_texts():
        text.set_color("#334155")

    baseline_sdti = baseline["metrics"]["sdti"]["value"]
    candidate_sdti = candidate["metrics"]["sdti"]["value"]
    question_count = candidate["execution"]["question_count"]
    source_validation = candidate_audit["source_validation"]
    valid_source_count = sum(1 for item in source_validation if item.get("valid"))
    source_count = len(source_validation)
    fig.text(
        0.08,
        0.060,
        (
            f"历史回归点 {baseline_sdti:.2f}；严格 LIVE 候选回归点 {candidate_sdti:.2f}。"
            "二者使用同一未封存审核卷，不构成独立泛化或单模块增益结论。"
        ),
        ha="left",
        fontsize=9.7,
        color="#9A3412",
        fontweight="bold",
        fontproperties=font,
    )
    fig.text(
        0.08,
        0.032,
        (
            f"严格 LIVE 候选实际调用千问 {question_count}/{question_count} 次；"
            f"当次 {valid_source_count}/{source_count} 个受控来源地址通过校验。"
        ),
        ha="left",
        fontsize=9.7,
        color="#1E3A8A",
        fontweight="bold",
        fontproperties=font,
    )
    fig.text(
        0.92,
        0.045,
        "来源：两次 metrics.json",
        ha="right",
        fontsize=9,
        color="#64748B",
        fontproperties=font,
    )

    fig.subplots_adjust(left=0.20, right=0.96, top=0.79, bottom=0.22)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
