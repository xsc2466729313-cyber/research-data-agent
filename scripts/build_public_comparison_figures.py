"""Build clear, reproducible public-comparison figures from the saved result artifact."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "evaluation" / "github_competitor_benchmark_20260830" / "results.json"
RUN_ROOT = ROOT / "evaluation" / "public_benchmarks" / "runs"
IMAGE_DIR = ROOT / "docs" / "images"
FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")
FONT = FontProperties(fname=str(FONT_PATH)) if FONT_PATH.exists() else FontProperties()

TEXT = "#172033"
MUTED = "#526174"
BLUE = "#2166C2"
TEAL = "#168A8A"
ORANGE = "#D97706"
RED = "#B42318"
GRID = "#D9E1EA"
LIGHT = "#F5F8FB"


def load_results() -> dict:
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def load_enhanced_retrieval(results: dict) -> dict | None:
    dataset_ids = ["beir_scifact", "beir_nfcorpus", "beir_scidocs", "beir_arguana", "beir_fiqa"]
    rows = []
    for dataset_id in dataset_ids:
        candidates = []
        for path in RUN_ROOT.glob(f"*_{dataset_id}/run.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "vnext_bm25_bge_cross_encoder_v1" in payload.get("results", {}):
                candidates.append((payload.get("created_at", ""), path, payload))
        if not candidates:
            return None
        _, path, payload = max(candidates, key=lambda item: item[0])
        current = payload["results"]
        project = current["vnext_bm25_bge_cross_encoder_v1"]
        bge = current["vnext_bge_small_en_v1_5"]
        rows.append({
            "dataset": dataset_id,
            "project_method": project["method_label"],
            "project_ndcg_at_10": project["ndcg_at_10"],
            "project_recall_at_100": project["recall_at_100"],
            "project_mrr_at_10": project["mrr_at_10"],
            "project_mean_latency_ms": project["mean_latency_ms"],
            "github_method": bge["method_label"],
            "github_ndcg_at_10": bge["ndcg_at_10"],
            "github_recall_at_100": bge["recall_at_100"],
            "github_mrr_at_10": bge["mrr_at_10"],
            "github_mean_latency_ms": bge["mean_latency_ms"],
            "query_count": project["query_count"],
            "evaluation_id": payload["evaluation_id"],
            "created_at": payload["created_at"],
            "code_revision": payload["code_revision"],
            "source_id": payload["dataset"]["source_id"],
            "source_url": payload["dataset"]["source_url"],
            "archive_sha256": payload["dataset"].get("archive_sha256"),
            "corpus_sha256": payload["dataset"].get("corpus_sha256"),
            "queries_sha256": payload["dataset"].get("queries_sha256"),
            "qrels_test_sha256": payload["dataset"]["qrels_test_sha256"],
            "run_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        })
    return {
        "rows": rows,
        "project_macro": sum(row["project_ndcg_at_10"] for row in rows) / len(rows),
        "github_macro": sum(row["github_ndcg_at_10"] for row in rows) / len(rows),
        "project_recall_macro": sum(row["project_recall_at_100"] for row in rows) / len(rows),
        "project_mrr_macro": sum(row["project_mrr_at_10"] for row in rows) / len(rows),
        "project_latency_mean_ms": sum(row["project_mean_latency_ms"] for row in rows) / len(rows),
    }


def save_enhanced_retrieval_summary(results: dict, enhanced_retrieval: dict | None) -> Path | None:
    if enhanced_retrieval is None:
        return None
    path = ROOT / "evaluation" / "public_benchmarks" / "enhanced_retrieval_20260902.json"
    payload = {
        "evaluation_id": "public-retrieval-enhanced-20260902",
        "created_at": "2026-09-02",
        "scope": "BEIR test split; retrieval-layer comparison only; not clinical validity or SDTI.",
        "metric": "nDCG@10",
        "project_method": "BM25 + BGE + CrossEncoder",
        "public_comparison_method": "BGE-small-en-v1.5",
        "historical_baseline": {
            "method": "BM25 + BGE fusion",
            "macro_ndcg_at_10": results["modules"]["retrieval"]["project_macro"],
            "source_file": "evaluation/github_competitor_benchmark_20260830/results.json",
        },
        "project_macro_ndcg_at_10": enhanced_retrieval["project_macro"],
        "public_macro_ndcg_at_10": enhanced_retrieval["github_macro"],
        "project_recall_at_100_macro": enhanced_retrieval["project_recall_macro"],
        "project_mrr_at_10_macro": enhanced_retrieval["project_mrr_macro"],
        "project_mean_latency_ms": enhanced_retrieval["project_latency_mean_ms"],
        "datasets": enhanced_retrieval["rows"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def style_axis(ax) -> None:
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#9AA8B8")
    ax.tick_params(axis="y", length=0, colors=MUTED)
    ax.tick_params(axis="x", colors=MUTED)


def label_bars(ax, bars, *, digits: int = 3, values: list[float] | None = None) -> None:
    for index, bar in enumerate(bars):
        value = bar.get_width()
        if values is not None and math.isnan(values[index]):
            continue
        ax.text(
            value + 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.{digits}f}",
            va="center",
            ha="left",
            fontsize=9.5,
            color=TEXT,
            fontproperties=FONT,
        )


def save_scorecard(results: dict, enhanced_retrieval: dict | None) -> Path:
    modules = results["modules"]
    labels = ["科学检索", "字段匹配", "实体匹配", "错误检测"]
    project = [
        enhanced_retrieval["project_macro"] if enhanced_retrieval else modules["retrieval"]["project_macro"],
        modules["schema_matching"]["project_macro"],
        modules["entity_matching"]["project_macro"],
        modules["cleaning"]["project_macro"],
    ]
    external = [
        modules["retrieval"]["github_macro"],
        modules["schema_matching"]["github_macro"],
        modules["entity_matching"]["github_macro"],
        modules["cleaning"]["github_macro"],
    ]
    fig, ax = plt.subplots(figsize=(12.8, 7.1), facecolor="white")
    y = np.arange(len(labels))
    height = 0.30
    project_bars = ax.barh(y - height / 2, project, height, color=BLUE, label="本项目主方法", zorder=3)
    external_bars = ax.barh(y + height / 2, external, height, color="#B8C3D1", label="公开对照方法", zorder=2)
    label_bars(ax, project_bars)
    label_bars(ax, external_bars)
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=12)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("宏平均主指标（越高越好；不同模块不可相加）", fontproperties=FONT, fontsize=10.5)
    style_axis(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.25), ncol=2, frameon=False, prop=FONT)
    fig.suptitle("公开能力对照总览：每一行回答一个独立问题", x=0.08, y=0.96, ha="left", fontsize=18, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.895, "同一公开数据、同一测试划分、同一指标；蓝色领先的行才表示本项目在该模块宏平均更高。", ha="left", fontsize=10.5, color=MUTED, fontproperties=FONT)
    fig.text(0.08, 0.055, "结果：字段匹配、实体匹配略占优；检索接近但略低；错误检测明显落后，不能用一个总分掩盖短板。", ha="left", fontsize=10.2, color=RED, fontweight="bold", fontproperties=FONT)
    fig.text(0.92, 0.025, "来源：历史结果 results.json；增强结果 enhanced_retrieval_20260902.json", ha="right", fontsize=8.5, color=MUTED, fontproperties=FONT)
    fig.subplots_adjust(left=0.14, right=0.96, top=0.80, bottom=0.22)
    path = IMAGE_DIR / "public-comparison-scorecard-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_dataset_chart(results: dict, module: str, filename: str, title: str, subtitle: str, project_label: str, external_label: str, project_key: str, external_key: str, labels: list[str], *, digits: int = 3, height: float = 0.28) -> Path:
    rows = [row for row in results["modules"][module]["rows"] if row.get("status") == "OK"]
    project = [float(row[project_key]) for row in rows]
    external = [float(row[external_key]) if row.get(external_key) is not None else math.nan for row in rows]
    valid = [index for index, value in enumerate(external) if not math.isnan(value)]
    fig_height = max(6.2, 1.0 + len(rows) * 0.52)
    fig, ax = plt.subplots(figsize=(13.0, fig_height), facecolor="white")
    y = np.arange(len(rows))
    project_bars = ax.barh(y - height / 2, project, height, color=BLUE, label=project_label, zorder=3)
    external_bars = ax.barh(y + height / 2, [0 if math.isnan(value) else value for value in external], height, color="#B8C3D1", label=external_label, zorder=2)
    label_bars(ax, project_bars, digits=digits)
    label_bars(ax, external_bars, digits=digits, values=external)
    for index in range(len(rows)):
        if index not in valid:
            ax.text(0.015, index + height / 2, "未评测", va="center", ha="left", fontsize=9, color=MUTED, fontproperties=FONT)
        elif abs(project[index] - external[index]) < 0.001:
            ax.text(1.01, index, "相同", va="center", ha="left", fontsize=8.5, color=MUTED, fontproperties=FONT)
        else:
            winner = "本项目" if project[index] > external[index] else "公开对照"
            ax.text(1.01, index, winner, va="center", ha="left", fontsize=8.5, color=TEAL if winner == "本项目" else ORANGE, fontweight="bold", fontproperties=FONT)
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("F1 或 nDCG@10（越高越好）", fontproperties=FONT, fontsize=10.5)
    style_axis(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False, prop=FONT)
    fig.suptitle(title, x=0.08, y=0.985, ha="left", fontsize=16, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.94, subtitle, ha="left", fontsize=9.8, color=MUTED, fontproperties=FONT)
    fig.text(0.08, 0.035, "右侧标签只表示本题在该公开任务上的高低，不代表临床有效性，也不代表所有任务的整体排名。", ha="left", fontsize=9.3, color=MUTED, fontproperties=FONT)
    fig.subplots_adjust(left=0.22, right=0.90, top=0.87, bottom=0.22)
    path = IMAGE_DIR / filename
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_retrieval_chart(enhanced_retrieval: dict | None) -> Path:
    results = enhanced_retrieval or {"rows": []}
    rows = results["rows"]
    project = [float(row["project_ndcg_at_10"]) for row in rows]
    external = [float(row["github_ndcg_at_10"]) for row in rows]
    labels = ["SciFact", "NFCorpus", "SciDocs", "ArguAna", "FiQA"]
    fig, ax = plt.subplots(figsize=(13.0, 7.2), facecolor="white")
    y = np.arange(len(rows))
    height = 0.28
    project_bars = ax.barh(y - height / 2, project, height, color=BLUE, label="本项目重排增强", zorder=3)
    external_bars = ax.barh(y + height / 2, external, height, color="#B8C3D1", label="BGE 单路公开对照", zorder=2)
    label_bars(ax, project_bars)
    label_bars(ax, external_bars)
    for index, (left, right) in enumerate(zip(project, external, strict=True)):
        if abs(left - right) < 0.001:
            result = "相同"
            color = MUTED
        else:
            result = "本项目" if left > right else "公开对照"
            color = TEAL if result == "本项目" else ORANGE
        ax.text(1.01, index, result, va="center", ha="left", fontsize=9, color=color, fontweight="bold", fontproperties=FONT)
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=10.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("nDCG@10（越高越好）", fontproperties=FONT, fontsize=10.5)
    style_axis(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, prop=FONT)
    fig.suptitle("PB-01 科学检索：加入重排后的五集逐题对照", x=0.08, y=0.98, ha="left", fontsize=16, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.935, "同一公开语料与测试 qrels；重排提高了融合基线，但五集宏平均仍低于 BGE 单路。", ha="left", fontsize=9.8, color=MUTED, fontproperties=FONT)
    fig.text(0.08, 0.035, "右侧标签只表示本题在该公开任务上的高低，不代表临床有效性或全系统排名。", ha="left", fontsize=9.3, color=MUTED, fontproperties=FONT)
    fig.subplots_adjust(left=0.20, right=0.90, top=0.86, bottom=0.20)
    path = IMAGE_DIR / "public-retrieval-datasets-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_failure_map() -> Path:
    rows = [
        ("科学检索", "重排增强 0.3818；\nBGE 0.3880", "重排在\nSciDocs、ArguAna\n仍未改善前排质量", "先按开发集选择\n融合或单路，再用\n独立测试集确认"),
        ("字段匹配", "本项目 0.7994；\nCOMA 0.7670", "缩写、布尔列和\n重复值仍造成误匹配", "报告 Wrong Auto-Match；\n高风险字段进入 REVIEW"),
        ("实体匹配", "本项目 0.7449；\nRecordLinkage 0.7440", "Walmart-Amazon 等\n表达变化大，召回和\n精度互有损失", "扩大训练/验证范围；\n患者关联保留 unresolved"),
        ("错误检测", "本项目 0.5726；\nRaha 0.8159", "Flights、Rayyan 的\n缺失和语义错误不能\n由单表格式唯一推断", "增加跨列约束；检测与修复\n分开，低置信度送审"),
    ]
    fig, ax = plt.subplots(figsize=(14.4, 7.3), facecolor="white")
    ax.axis("off")
    columns = [0.03, 0.18, 0.41, 0.70]
    headers = ["能力层", "真实对照", "为什么当前不好/不占优", "下一步怎样提升"]
    widths = [0.14, 0.21, 0.23, 0.28]
    for x, header in zip(columns, headers, strict=True):
        ax.text(x, 0.92, header, transform=ax.transAxes, fontsize=11, color=MUTED, fontweight="bold", fontproperties=FONT)
    for index, row in enumerate(rows):
        y = 0.78 - index * 0.18
        if index % 2 == 0:
            ax.add_patch(plt.Rectangle((0.02, y - 0.075), 0.94, 0.13, transform=ax.transAxes, facecolor=LIGHT, edgecolor="none", zorder=0))
        for x, value, width in zip(columns, row, widths, strict=True):
            color = RED if index in {0, 3} and x == columns[1] else TEXT
            ax.text(x, y, value, transform=ax.transAxes, fontsize=9.7, color=color, va="center", fontproperties=FONT)
    fig.suptitle("公开对照失败地图：差距来自哪里，怎样改才算真实提升", x=0.04, y=0.98, ha="left", fontsize=18, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.04, 0.035, "改进方向是下一轮可验证假设，不把尚未运行的方案写成现有成绩。", fontsize=10, color=RED, fontweight="bold", fontproperties=FONT)
    path = IMAGE_DIR / "public-comparison-failure-map-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_question_map() -> Path:
    fig, ax = plt.subplots(figsize=(14.4, 8.0), facecolor="white")
    ax.axis("off")
    ax.text(0.03, 0.94, "原始科研问题与公开对照题号对应关系", transform=ax.transAxes, fontsize=19, fontweight="bold", color=TEXT, fontproperties=FONT)
    ax.text(0.03, 0.885, "原始问题保留为 RQ-01；公共数据集只验证其中可拆出的通用能力，不冒充已经回答了患者级医学关联。", transform=ax.transAxes, fontsize=11, color=MUTED, fontproperties=FONT)
    ax.add_patch(plt.Rectangle((0.03, 0.68), 0.94, 0.14, transform=ax.transAxes, facecolor="#EAF2FF", edgecolor="#8CB4E8", linewidth=1.2))
    ax.text(0.05, 0.77, "RQ-01 原始科研问题", transform=ax.transAxes, fontsize=11, color=BLUE, fontweight="bold", fontproperties=FONT)
    ax.text(0.05, 0.715, "在 HER2 阳性乳腺癌中，PIK3CA 突变是否与新辅助治疗响应相关？", transform=ax.transAxes, fontsize=13, color=TEXT, fontweight="bold", fontproperties=FONT)
    items = [
        ("PB-01", "科学检索", "能否把相关论文排到前十？", "BEIR；nDCG@10", "只验证‘找材料’"),
        ("PB-02", "字段匹配", "两张表的不同列名是否表示同一字段？", "Valentine；Schema F1", "只验证‘看懂列’"),
        ("PB-03", "实体匹配", "两条记录是否指向同一实体？", "DeepMatcher；Entity F1", "只验证‘判断记录’"),
        ("PB-04", "错误检测", "能否找出错误单元且不误伤正确值？", "Raha/HoloClean；Cell F1", "只验证‘检查表’"),
    ]
    for index, (code, capability, question, metric, boundary) in enumerate(items):
        x = 0.03 + (index % 2) * 0.48
        y = 0.49 - (index // 2) * 0.22
        ax.add_patch(plt.Rectangle((x, y), 0.44, 0.16, transform=ax.transAxes, facecolor="white", edgecolor="#C9D4E0", linewidth=1.0))
        ax.text(x + 0.02, y + 0.12, f"{code}  {capability}", transform=ax.transAxes, fontsize=11, color=TEAL, fontweight="bold", fontproperties=FONT)
        ax.text(x + 0.02, y + 0.075, question, transform=ax.transAxes, fontsize=10.5, color=TEXT, fontproperties=FONT)
        ax.text(x + 0.02, y + 0.035, f"指标：{metric}；边界：{boundary}", transform=ax.transAxes, fontsize=9.2, color=MUTED, fontproperties=FONT)
    ax.annotate("拆分验证", xy=(0.50, 0.67), xytext=(0.50, 0.61), xycoords="axes fraction", textcoords="axes fraction", ha="center", color=ORANGE, fontsize=10.5, fontweight="bold", fontproperties=FONT, arrowprops={"arrowstyle": "->", "color": ORANGE, "lw": 1.5})
    ax.text(0.03, 0.055, "RQ-01 仍需要同一研究/可靠 crosswalk 中同时具备 HER2、PIK3CA、治疗阶段和患者响应；PB-01—PB-04 的高分不能替代这一医学问题的联合证据。", transform=ax.transAxes, fontsize=10.5, color=RED, fontweight="bold", fontproperties=FONT)
    path = IMAGE_DIR / "public-comparison-question-map-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["axes.unicode_minus"] = False
    results = load_results()
    enhanced_retrieval = load_enhanced_retrieval(results)
    summary_path = save_enhanced_retrieval_summary(results, enhanced_retrieval)
    paths = [
        save_scorecard(results, enhanced_retrieval),
        save_retrieval_chart(enhanced_retrieval),
        save_dataset_chart(results, "schema_matching", "public-schema-datasets-20260902.png", "PB-02 字段匹配：十个公开任务逐题对照", "同一 Valentine ground truth；公开对照固定为 COMA，其他公开算法保留在机器可读结果中。", "本项目 V3", "Valentine COMA", "project_f1", "github_f1", ["Capital Projects", "DCM Street Centerline", "DPR Athletic Facilities", "DSNY Disposal Assignments", "Education COVID Meals", "Energy Benchmarking", "Housing Maintenance", "Public Art Inventory", "Street Resurfacing", "Swim for Life"], digits=3, height=0.22),
        save_dataset_chart(results, "entity_matching", "public-entity-datasets-20260902.png", "PB-03 实体匹配：五个公开任务逐题对照", "同一 DeepMatcher 官方测试划分；公开对照用 RecordLinkage 的 Jaro-Winkler + logistic。", "本项目自适应融合", "RecordLinkage", "project_f1", "github_f1", ["Amazon-Google", "Beer-RateBeer", "DBLP-ACM", "Fodors-Zagats", "Walmart-Amazon"], digits=3),
        save_dataset_chart(results, "cleaning", "public-cleaning-datasets-20260902.png", "PB-04 错误检测：六个公开任务逐题对照", "同一 dirty/clean 表；主指标是错误单元检测 F1，Tax 因公开对照未运行而不进入双方宏平均。", "本项目融合", "Raha PVD+RVD", "project_f1", "github_f1", ["Hospital", "Beers", "Flights", "Movies-1", "Rayyan", "Tax"], digits=3),
        save_failure_map(),
        save_question_map(),
    ]
    for path in paths:
        print(path)
    if summary_path:
        print(summary_path)


if __name__ == "__main__":
    main()
