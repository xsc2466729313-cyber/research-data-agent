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
PUBLIC_RESULTS_PATH = ROOT / "evaluation" / "PUBLIC_DATASET_COMPARISON_20260902.json"
RETRIEVAL_MATRIX_PATH = ROOT / "evaluation" / "public_benchmarks" / "retrieval_matrix_20260903.json"
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


def load_latest_chart_results(results: dict) -> dict:
    """Overlay completed Qwen and v6 runs onto the historical chart schema."""
    chart_results = json.loads(json.dumps(results))
    public_results = json.loads(PUBLIC_RESULTS_PATH.read_text(encoding="utf-8"))

    qwen_schema = {}
    for path in RUN_ROOT.glob("*_qwen_valentine_*/run.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset_id = payload.get("dataset", {}).get("dataset_id")
        result = payload.get("results", {}).get("qwen_schema")
        if dataset_id and result and payload.get("audit", {}).get("failed_calls", 1) == 0:
            qwen_schema[dataset_id] = result["f1"]
    for row in chart_results["modules"]["schema_matching"]["rows"]:
        if row["dataset"] in qwen_schema:
            row["project_f1"] = qwen_schema[row["dataset"]]
            row["project_method"] = "千问辅助字段匹配"
    chart_results["modules"]["schema_matching"]["project_macro"] = public_results["headline"]["schema_qwen_macro_f1"]

    v6_cleaning = {}
    for path in RUN_ROOT.glob("*_holoclean_*/run.json"):
        candidates = [path]
        candidates.extend(RUN_ROOT.glob(f"*_{path.parent.name.split('_', 1)[-1].replace('holoclean_', 'raha_')}*/run.json"))
        for candidate in candidates:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            dataset_id = payload.get("dataset", {}).get("dataset_id")
            result = payload.get("results", {}).get("project_source_anchor_repair_v6")
            if dataset_id and result:
                v6_cleaning[dataset_id] = result["cell_f1"]
    for path in RUN_ROOT.glob("*_raha_*/run.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset_id = payload.get("dataset", {}).get("dataset_id")
        result = payload.get("results", {}).get("project_source_anchor_repair_v6")
        if dataset_id and result:
            v6_cleaning[dataset_id] = result["cell_f1"]
    for row in chart_results["modules"]["cleaning"]["rows"]:
        if row["dataset"] in v6_cleaning:
            row["project_f1"] = v6_cleaning[row["dataset"]]
            row["project_exact_repair_f1"] = v6_cleaning[row["dataset"]]
            row["project_method"] = "来源锚点清洗第6版"
    chart_results["modules"]["cleaning"]["project_macro"] = public_results["headline"]["cleaning_v6_macro_cell_f1"]
    return chart_results


def load_enhanced_retrieval(results: dict) -> dict | None:
    dataset_ids = ["beir_scifact", "beir_nfcorpus", "beir_scidocs", "beir_arguana", "beir_fiqa"]
    matrix = json.loads(RETRIEVAL_MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_rows = {
        (row["dataset"], row["method_id"]): row
        for row in matrix["rows"]
    }
    rows = []
    for dataset_id in dataset_ids:
        project = matrix_rows.get((dataset_id, "vnext_bm25_bge_rrf_v1"))
        bge = matrix_rows.get((dataset_id, "vnext_bge_small_en_v1_5"))
        if project is None or bge is None:
            return None
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
            "evaluation_id": project["evaluation_id"],
            "source_id": project["source_id"],
            "source_url": project["source_url"],
            "run_file": project["run_file"],
        })
    return {
        "rows": rows,
        "project_macro": sum(row["project_ndcg_at_10"] for row in rows) / len(rows),
        "github_macro": sum(row["github_ndcg_at_10"] for row in rows) / len(rows),
        "project_recall_macro": sum(row["project_recall_at_100"] for row in rows) / len(rows),
        "project_mrr_macro": sum(row["project_mrr_at_10"] for row in rows) / len(rows),
        "project_latency_mean_ms": sum(row["project_mean_latency_ms"] for row in rows) / len(rows),
    }


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
    labels = [
        "科学检索\n本项目：BM25+BGE 名次融合\n对照：BGE 单路",
        "字段匹配\n本项目：千问辅助\n对照：COMA",
        "实体匹配\n本项目：自适应融合\n对照：RecordLinkage",
        "错误检测\n本项目：来源锚点清洗第6版\n对照：Raha PVD+RVD",
    ]
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
    fig.text(0.08, 0.895, "蓝色为本项目方法，灰色为公开对照方法；每一行使用该公开任务的官方测试划分和通用指标。", ha="left", fontsize=10.5, color=MUTED, fontproperties=FONT)
    fig.text(0.08, 0.055, "结果：千问字段匹配与来源锚点清洗领先；检索小幅领先；实体匹配平均值基本持平。", ha="left", fontsize=10.2, color=RED, fontweight="bold", fontproperties=FONT)
    fig.text(0.92, 0.025, "来源：PUBLIC_DATASET_COMPARISON_20260902.json；成功运行证据", ha="right", fontsize=8.5, color=MUTED, fontproperties=FONT)
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
            ax.text(1.075, index, "相同", va="center", ha="left", fontsize=8.5, color=MUTED, fontproperties=FONT)
        else:
            winner = "本项目" if project[index] > external[index] else "公开对照"
            ax.text(1.075, index, winner, va="center", ha="left", fontsize=8.5, color=TEAL if winner == "本项目" else ORANGE, fontweight="bold", fontproperties=FONT)
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.18)
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
    project_bars = ax.barh(y - height / 2, project, height, color=BLUE, label="本项目名次融合", zorder=3)
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
        ax.text(1.075, index, result, va="center", ha="left", fontsize=9, color=color, fontweight="bold", fontproperties=FONT)
    ax.set_yticks(y, labels, fontproperties=FONT, fontsize=10.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.18)
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("nDCG@10（越高越好）", fontproperties=FONT, fontsize=10.5)
    style_axis(ax)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, prop=FONT)
    fig.suptitle("PB-01 科学检索：名次融合的五集逐题对照", x=0.08, y=0.98, ha="left", fontsize=16, fontweight="bold", color=TEXT, fontproperties=FONT)
    fig.text(0.08, 0.935, "同一公开语料与测试标注；名次融合的五任务宏平均高于 BGE 单路，SciDocs 仍低于对照。", ha="left", fontsize=9.8, color=MUTED, fontproperties=FONT)
    fig.text(0.08, 0.035, "右侧标签只表示本题在该公开任务上的高低，不代表临床有效性或全系统排名。", ha="left", fontsize=9.3, color=MUTED, fontproperties=FONT)
    fig.subplots_adjust(left=0.20, right=0.90, top=0.86, bottom=0.20)
    path = IMAGE_DIR / "public-retrieval-datasets-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def save_failure_map() -> Path:
    rows = [
        ("科学检索", "本项目 BM25+BGE 名次融合 0.3915；\n公开对照 BGE 单路 0.3880", "SciDocs 仍低于 BGE；\n复杂语义关系和候选\n召回限制上限", "整体排序与覆盖略有改善；\n适合扩大相关材料覆盖"),
        ("字段匹配", "本项目千问辅助 0.9018；\n公开对照 COMA 0.7670", "三个任务低于项目规则；\n缩写、布尔列和\n重复值仍会误配", "语义改名更易对齐；\n医学字段继续规则复核"),
        ("实体匹配", "本项目自适应融合 0.7449；\n公开对照字符相似度方法 0.7440", "Walmart-Amazon 等\n表达变化大，召回和\n精度互有损失", "可提供候选对应关系；\n患者关联仍保留人工复核"),
        ("错误检测", "本项目来源锚点清洗第6版 0.9169；\n公开对照 Raha 0.8159", "Rayyan 的字符损坏和\n缺失语义信息仍不能\n由单表证据安全恢复", "有来源锚点时清洗更可靠；\n无证据值不自动猜测"),
    ]
    fig, ax = plt.subplots(figsize=(14.4, 7.3), facecolor="white")
    ax.axis("off")
    columns = [0.03, 0.18, 0.41, 0.70]
    headers = ["能力层", "本项目与公开对照", "差异说明", "对科研使用的意义"]
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
    fig.text(0.04, 0.035, "表中只展示已经完成的公开对照结果；优势与边界均回到实际科研使用场景解释。", fontsize=10, color=RED, fontweight="bold", fontproperties=FONT)
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
    ax.text(0.03, 0.055, "RQ-01 仍需要同一研究或可靠身份对应表中同时具备 HER2、PIK3CA、治疗阶段和患者响应；PB-01—PB-04 的高分不能替代这一医学问题的联合证据。", transform=ax.transAxes, fontsize=10.5, color=RED, fontweight="bold", fontproperties=FONT)
    path = IMAGE_DIR / "public-comparison-question-map-20260902.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["axes.unicode_minus"] = False
    results = load_results()
    chart_results = load_latest_chart_results(results)
    enhanced_retrieval = load_enhanced_retrieval(results)
    paths = [
        save_scorecard(chart_results, enhanced_retrieval),
        save_retrieval_chart(enhanced_retrieval),
        save_dataset_chart(chart_results, "schema_matching", "public-schema-datasets-20260902.png", "PB-02 字段匹配：十个公开任务逐题对照", "同一 Valentine 测试标注；千问只看到表头和值概况，不读取测试答案。", "千问辅助字段匹配", "Valentine COMA", "project_f1", "github_f1", ["Capital Projects", "DCM Street Centerline", "DPR Athletic Facilities", "DSNY Disposal Assignments", "Education COVID Meals", "Energy Benchmarking", "Housing Maintenance", "Public Art Inventory", "Street Resurfacing", "Swim for Life"], digits=3, height=0.22),
        save_dataset_chart(chart_results, "entity_matching", "public-entity-datasets-20260902.png", "PB-03 实体匹配：五个公开任务逐题对照", "同一 DeepMatcher 官方测试划分；公开对照使用字符相似度与逻辑回归。", "本项目自适应融合", "字符相似度对照", "project_f1", "github_f1", ["Amazon-Google", "Beer-RateBeer", "DBLP-ACM", "Fodors-Zagats", "Walmart-Amazon"], digits=3),
        save_dataset_chart(chart_results, "cleaning", "public-cleaning-datasets-20260902.png", "PB-04 错误检测：六个公开任务逐题对照", "同一脏表和干净表；Tax 没有完整公开对照，因此不进入双方共同平均值。", "来源锚点清洗第6版", "Raha PVD+RVD", "project_f1", "github_f1", ["Hospital", "Beers", "Flights", "Movies-1", "Rayyan", "Tax"], digits=3),
        save_failure_map(),
        save_question_map(),
    ]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
