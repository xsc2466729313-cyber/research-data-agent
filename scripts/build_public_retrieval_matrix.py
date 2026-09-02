"""Build one multi-method, multi-metric matrix from completed public retrieval runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "evaluation" / "public_benchmarks" / "runs"
JSON_OUTPUT = ROOT / "evaluation" / "public_benchmarks" / "retrieval_matrix_20260903.json"
MD_OUTPUT = ROOT / "evaluation" / "PUBLIC_RETRIEVAL_MATRIX_20260903.md"

DATASET_LABELS = {
    "beir_scifact": "SciFact（科学事实）",
    "beir_nfcorpus": "NFCorpus（营养医学）",
    "beir_scidocs": "SciDocs（科学文献关系）",
    "beir_arguana": "ArguAna（论证检索）",
    "beir_fiqa": "FiQA（金融问题）",
    "beir_trec_covid": "TREC-COVID（医学文献）",
    "beir_quora": "Quora（问题检索）",
}
METHOD_ORDER = [
    "bm25_local_reference",
    "project_bm25_tuned_v2",
    "project_hybrid_hashing_lexical_v1",
    "vnext_bge_small_en_v1_5",
    "vnext_bm25_bge_fusion_v1",
    "vnext_bm25_bge_rrf_v1",
    "vnext_bm25_bge_cross_encoder_v1",
    "vnext_dev_selected_retrieval_v1",
]
METHOD_LABELS = {
    "bm25_local_reference": "公开基线：BM25",
    "project_bm25_tuned_v2": "项目方法：调参 BM25",
    "project_hybrid_hashing_lexical_v1": "项目方法：哈希混合检索",
    "vnext_bge_small_en_v1_5": "公开基线：BGE-small-en-v1.5",
    "vnext_bm25_bge_fusion_v1": "项目方法：BM25+BGE 融合",
    "vnext_bm25_bge_rrf_v1": "项目方法：BM25+BGE 名次融合",
    "vnext_bm25_bge_cross_encoder_v1": "项目方法：BGE 初检索+交叉重排",
    "vnext_dev_selected_retrieval_v1": "项目方法：开发集选择",
}
CORE_METHODS = {
    "bm25_local_reference",
    "project_bm25_tuned_v2",
    "project_hybrid_hashing_lexical_v1",
    "vnext_bge_small_en_v1_5",
    "vnext_bm25_bge_fusion_v1",
}
BATCH_TIMED_METHODS = {
    "vnext_bge_small_en_v1_5",
    "vnext_bm25_bge_fusion_v1",
    "vnext_bm25_bge_rrf_v1",
    "vnext_bm25_bge_cross_encoder_v1",
    "vnext_dev_selected_retrieval_v1",
}
METRIC_COLUMNS = (
    "ndcg_at_10",
    "hit_rate_at_1",
    "hit_rate_at_3",
    "hit_rate_at_5",
    "hit_rate_at_10",
    "recall_at_10",
    "recall_at_100",
    "mrr_at_10",
    "mean_latency_ms",
    "std_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "query_count",
)
DISPLAY_COLUMNS = (
    ("nDCG@10", "ndcg_at_10"),
    ("命中@1", "hit_rate_at_1"),
    ("命中@3", "hit_rate_at_3"),
    ("命中@5", "hit_rate_at_5"),
    ("命中@10", "hit_rate_at_10"),
    ("召回@10", "recall_at_10"),
    ("召回@100", "recall_at_100"),
    ("首条排序", "mrr_at_10"),
    ("平均用时(ms)", "mean_latency_ms"),
    ("用时标准差(ms)", "std_latency_ms"),
    ("P95用时(ms)", "p95_latency_ms"),
    ("查询数", "query_count"),
)


def load_runs() -> dict[str, dict[str, tuple[str, dict[str, Any], dict[str, Any]]]]:
    latest: dict[str, dict[str, tuple[str, dict[str, Any], dict[str, Any]]]] = {}
    for path in RUN_ROOT.glob("*/run.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset = payload.get("dataset", {}).get("dataset_id")
        results = payload.get("results", {})
        if not dataset or not dataset.startswith("beir_") or not results:
            continue
        for method_id, result in results.items():
            complete = "hit_rate_at_1" in result
            marker = f"{int(complete)}:{payload.get('created_at', '')}"
            current = latest.setdefault(dataset, {}).get(method_id)
            if current is None or marker > current[0]:
                latest[dataset][method_id] = (marker, payload, result)
    return latest


def row(dataset: str, method_id: str, result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "dataset_label": DATASET_LABELS.get(dataset, dataset),
        "method_id": method_id,
        "method_label": METHOD_LABELS.get(method_id, result.get("method_label", method_id)),
        "source_id": payload["dataset"].get("source_id"),
        "source_url": payload["dataset"].get("source_url"),
        "evaluation_id": payload.get("evaluation_id"),
        "run_file": f"evaluation/public_benchmarks/runs/{payload.get('evaluation_id')}/run.json",
        **{key: result.get(key) for key in METRIC_COLUMNS},
    }


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(item[key]) for item in rows if item.get(key) is not None]
    return sum(values) / len(values) if values else None


def display_value(item: dict[str, Any], key: str) -> str:
    if item.get("method_id") in BATCH_TIMED_METHODS and key in {"std_latency_ms", "p95_latency_ms"}:
        return "批次均摊，未逐题测量"
    value = item.get(key)
    if value is None:
        return "未记录"
    if key == "query_count":
        return str(int(value))
    return f"{value:.2f}" if "latency" in key else f"{value:.4f}"


def aggregate_display_value(item: dict[str, Any], key: str) -> str:
    if item["method_id"] in BATCH_TIMED_METHODS and key in {"std_latency_ms", "p95_latency_ms"}:
        return "批次均摊"
    value = item.get(f"{key}_macro")
    if value is None:
        return "未记录"
    return f"{value:.2f}" if "latency" in key else f"{value:.4f}"


def main() -> None:
    runs = load_runs()
    rows: list[dict[str, Any]] = []
    for dataset in sorted(runs):
        for method_id in METHOD_ORDER:
            item = runs[dataset].get(method_id)
            if item is None:
                continue
            _marker, payload, result = item
            if "hit_rate_at_1" in result:
                rows.append(row(dataset, method_id, result, payload))

    common_dataset_ids = sorted(
        set.intersection(*[
            {item["dataset"] for item in rows if item["method_id"] == method_id}
            for method_id in CORE_METHODS
        ])
    )
    aggregate: list[dict[str, Any]] = []
    all_completed_aggregate: list[dict[str, Any]] = []
    for method_id in METHOD_ORDER:
        method_rows = [item for item in rows if item["method_id"] == method_id]
        if not method_rows:
            continue
        common_rows = [item for item in method_rows if item["dataset"] in common_dataset_ids]
        aggregate_rows = common_rows or method_rows
        aggregate.append({
            "method_id": method_id,
            "method_label": METHOD_LABELS[method_id],
            "aggregation_scope": "共同任务：" + ", ".join(common_dataset_ids) if common_rows else "该方法全部已完成任务",
            "dataset_count": len({item["dataset"] for item in aggregate_rows}),
            "total_query_count": sum(int(item["query_count"]) for item in aggregate_rows),
            **{f"{key}_macro": mean(aggregate_rows, key) for key in METRIC_COLUMNS if key != "query_count"},
        })
        all_completed_aggregate.append({
            "method_id": method_id,
            "method_label": METHOD_LABELS[method_id],
            "dataset_count": len({item["dataset"] for item in method_rows}),
            "total_query_count": sum(int(item["query_count"]) for item in method_rows),
            **{f"{key}_macro": mean(method_rows, key) for key in METRIC_COLUMNS if key != "query_count"},
        })

    dataset_status = []
    for dataset in sorted(set(runs) | {"beir_quora"}):
        dataset_runs = runs.get(dataset, {})
        payload = next((item[1] for item in dataset_runs.values()), None)
        dataset_rows = [item for item in rows if item["dataset"] == dataset]
        dataset_status.append({
            "dataset": dataset,
            "dataset_label": DATASET_LABELS.get(dataset, dataset),
            "status": "已完成" if any(item["dataset"] == dataset for item in rows) else "未完成",
            "query_count": max((int(item["query_count"]) for item in dataset_rows), default=None),
            "source_id": (payload or {}).get("dataset", {}).get("source_id", "beir:quora" if dataset == "beir_quora" else None),
            "source_url": (payload or {}).get("dataset", {}).get("source_url", "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip" if dataset == "beir_quora" else None),
        })

    payload = {
        "report_id": "PUBLIC_RETRIEVAL_MATRIX_20260903",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "BEIR official test split; same corpus, query set and qrels within each dataset; retrieval layer only.",
        "fairness": {"test_sets_modified": False, "samples_filtered": False, "evaluation_rules_modified": False},
        "metric_direction": {"higher_is_better": [key for key in METRIC_COLUMNS if "latency" not in key], "lower_is_better": ["mean_latency_ms", "std_latency_ms", "p50_latency_ms", "p95_latency_ms"]},
        "dataset_status": dataset_status,
        "common_dataset_ids": common_dataset_ids,
        "aggregate_macro_by_method": aggregate,
        "aggregate_all_completed_by_method": all_completed_aggregate,
        "rows": rows,
        "notes": [
            "宏平均先在每个数据集内计算，再对已完成数据集等权平均；不把不同数据集的分数拼成一个准确率。",
            "命中率表示前 k 条中至少出现一个相关文献的问题比例；召回率表示前 k 条找回该问题全部相关文献的平均比例。",
            "TREC-COVID 已完成关键词三方法；其语义方法因十几万篇文献的 CPU 建索引成本过高，本轮未形成结果，不以估计值填充。",
            "Quora 已完成 BM25 与调参 BM25 的完整测试，但语义方法未形成完整运行，只列分层结果；未完成方法不会用估算值填充。",
            "BGE 和 BM25+BGE 的批量接口只记录批次均摊用时，未逐题测量标准差和 P95；表中明确标注，不把 0 当作波动为零。",
        ],
    }
    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 公开检索统一多方法、多指标对照",
        "",
        "> 范围：BEIR 官方测试划分，检索能力层，不代表临床预测准确率，也不计入 SDTI。每个数据集的测试问题、语料和相关性标注均原样使用。",
        "",
        "## 指标怎么看",
        "",
        "- `nDCG@10`：前十条结果的整体排序质量，越高表示相关文献越靠前。",
        "- `命中@k`：前 k 条中至少找到一篇相关文献的问题比例。",
        "- `召回@k`：前 k 条找回该问题全部相关文献的平均比例，能看出候选覆盖是否充分。",
        "- `首条排序`：第一个相关结果越靠前越高；平均用时、标准差和 P95 越低越稳定。",
        "",
        "## 共同任务宏平均总表",
        "",
        "主表共同任务为五个数据集：SciFact、NFCorpus、SciDocs、ArguAna 和 FiQA；Quora 已完成关键词方法对照但缺少语义方法，不纳入共同宏平均；TREC-COVID 的新增医学结果另列。",
        "| 方法 | 数据集数 | 查询数 | nDCG@10 | 命中@1 | 命中@3 | 命中@5 | 命中@10 | 召回@10 | 召回@100 | 首条排序 | 平均用时(ms) | 用时标准差(ms) | P95用时(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in aggregate:
        lines.append("| " + " | ".join([
            item["method_label"], str(item["dataset_count"]), str(item["total_query_count"]),
            *[aggregate_display_value(item, key) for _label, key in DISPLAY_COLUMNS if key != "query_count"],
        ]) + " |")

    lines += [
        "",
        "## 按数据集分层的同表对照",
        "",
        "同一行中的方法是在同一个公开测试集上比较；方法名称同时注明“公开基线”或“项目方法”，避免把两类方法混在一起。",
        "",
        "| 数据集 | 方法 | nDCG@10 | 命中@1 | 命中@3 | 命中@5 | 命中@10 | 召回@10 | 召回@100 | 首条排序 | 平均用时(ms) | 用时标准差(ms) | P95用时(ms) | 查询数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        if item["dataset"] == "beir_trec_covid":
            continue
        values = [display_value(item, key) for _label, key in DISPLAY_COLUMNS]
        lines.append("| " + " | ".join([item["dataset_label"], item["method_label"], *values]) + " |")

    lines += [
        "",
        "## TREC-COVID 医学补充结果",
        "",
        "TREC-COVID 是新增的医学文献任务，50 个测试问题上只有关键词三种方法完成了本轮运行；语义索引未形成结果，不以估算值填充。",
        "",
        "| 方法 | nDCG@10 | 命中@1 | 命中@3 | 命中@5 | 命中@10 | 召回@10 | 召回@100 | 首条排序 | 平均用时(ms) | 用时标准差(ms) | P95用时(ms) | 查询数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        if item["dataset"] != "beir_trec_covid":
            continue
        values = [display_value(item, key) for _label, key in DISPLAY_COLUMNS]
        lines.append("| " + " | ".join([item["method_label"], *values]) + " |")

    lines += ["", "## 数据集状态", "", "| 数据集 | 查询数 | 状态 | 来源 |", "|---|---:|---|---|"]
    for item in dataset_status:
        query_count = str(item["query_count"]) if item["query_count"] is not None else "未形成结果"
        source = f"[{item['source_id']}]({item['source_url']})" if item["source_url"] else item["source_id"] or "未登记"
        lines.append(f"| {item['dataset_label']} | {query_count} | {item['status']} | {source} |")

    lines += [
        "",
        "## 复现入口",
        "",
        "```powershell",
        "python scripts\\run_public_retrieval_benchmark.py --dataset beir_scifact --method bm25 --method project_bm25_tuned_v2 --method vnext_semantic --method vnext_hybrid --method vnext_rrf",
        "python scripts\\run_public_retrieval_benchmark.py --dataset beir_trec_covid --method bm25 --method project_bm25_tuned_v2 --method project_hybrid",
        "python scripts\\build_public_retrieval_matrix.py",
        "```",
        "",
        "报告引用的运行证据保存在 `evaluation/public_benchmarks/runs/`；每个 `run.json` 保存数据来源、测试划分、哈希、代码版本和逐项指标。",
        "",
    ]
    MD_OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(JSON_OUTPUT)
    print(MD_OUTPUT)


if __name__ == "__main__":
    main()
