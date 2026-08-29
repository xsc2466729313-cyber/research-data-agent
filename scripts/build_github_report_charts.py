"""Build reproducible PNG charts for the GitHub benchmark report.

The script intentionally reads the machine-readable benchmark artifact rather
than embedding scores in the chart code. It is a report-development utility;
Matplotlib is not a production backend dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_ROOT / "evaluation" / "github_competitor_benchmark_20260830" / "results.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "images"


def _configure_font() -> None:
    """Prefer an installed CJK font so labels remain readable on Windows."""
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False


def _save_summary(payload: dict, output_dir: Path) -> None:
    modules = [
        ("检索", payload["modules"]["retrieval"]),
        ("字段匹配", payload["modules"]["schema_matching"]),
        ("实体匹配", payload["modules"]["entity_matching"]),
        ("数据清洗", payload["modules"]["cleaning"]),
    ]
    labels = [label for label, _ in modules]
    project = [float(module["project_macro"]) for _, module in modules]
    github = [float(module["github_macro"]) for _, module in modules]

    fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=180)
    x = np.arange(len(labels))
    width = 0.34
    bars_project = ax.bar(x - width / 2, project, width, label="本项目", color="#d95f59")
    bars_github = ax.bar(x + width / 2, github, width, label="GitHub 对照", color="#247c83")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("模块宏平均分（越高越好）")
    ax.set_xticks(x, labels)
    ax.set_title("GitHub 同类项目公开数据集实测对比", loc="left", fontweight="bold", y=1.09, pad=8)
    ax.text(0, 1.025, "同数据、同切分、同指标；模块分数不可相加", transform=ax.transAxes, color="#5f6b6d")
    ax.grid(axis="y", color="#d9e1e2", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=2, loc="upper right")
    for bars in (bars_project, bars_github):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.015, f"{bar.get_height():.3f}",
                    ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_dir / "github-benchmark-summary.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _save_retrieval(payload: dict, output_dir: Path) -> None:
    rows = [row for row in payload["modules"]["retrieval"]["rows"] if row.get("status") == "OK"]
    labels = [row["dataset"].replace("beir_", "").replace("_", " ") for row in rows]
    project = [float(row["project_ndcg_at_10"]) for row in rows]
    bge = [float(row["github_ndcg_at_10"]) for row in rows]
    bm25 = [float(row["bm25_ndcg_at_10"]) for row in rows]

    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=180)
    x = np.arange(len(labels))
    width = 0.25
    ax.bar(x - width, project, width, label="本项目融合", color="#d95f59")
    ax.bar(x, bge, width, label="BGE 单路", color="#247c83")
    ax.bar(x + width, bm25, width, label="BM25", color="#8b9a9c")
    ax.set_ylim(0, 0.78)
    ax.set_ylabel("nDCG@10")
    ax.set_xticks(x, labels)
    ax.set_title("公开检索数据集分层结果", loc="left", fontweight="bold", y=1.09, pad=8)
    ax.text(0, 1.025, "BEIR 五个数据集；本项目融合未在每个数据集都超过单路 BGE", transform=ax.transAxes, color="#5f6b6d")
    ax.grid(axis="y", color="#d9e1e2", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=3, loc="upper right")
    fig.tight_layout()
    fig.savefig(output_dir / "github-retrieval-breakdown.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build charts from the GitHub benchmark JSON artifact.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.results.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _configure_font()
    _save_summary(payload, args.output_dir)
    _save_retrieval(payload, args.output_dir)
    print(args.output_dir / "github-benchmark-summary.png")
    print(args.output_dir / "github-retrieval-breakdown.png")


if __name__ == "__main__":
    main()
