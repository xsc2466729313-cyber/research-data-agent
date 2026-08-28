from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DATASETS = ("beir_scifact", "beir_nfcorpus", "beir_scidocs", "beir_arguana", "beir_fiqa")


def latest_run(root: Path, dataset: str, required_methods: tuple[str, ...] = ("project_bm25_tuned_v2",)) -> dict:
    runs = sorted(root.glob(f"*_{dataset}/run.json"), key=lambda path: path.parent.name, reverse=True)
    for path in runs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("results", {})
        if all(method in results for method in required_methods):
            payload["_artifact"] = str(path.parent.as_posix())
            return payload
    raise FileNotFoundError(f"No comparable BM25/BGE artifact found for {dataset}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize VNext retrieval benchmark artifacts without inventing missing values.")
    parser.add_argument("--runs-root", type=Path, default=Path("evaluation/public_benchmarks/runs"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/vnext_retrieval_macro_20260828.json"))
    args = parser.parse_args()
    methods = ("project_bm25_tuned_v2", "vnext_bge_small_en_v1_5", "vnext_bm25_bge_fusion_v1")
    artifacts: dict[str, dict[str, dict]] = {}
    for dataset in DATASETS:
        artifacts[dataset] = {}
        for method in methods:
            try:
                artifacts[dataset][method] = latest_run(args.runs_root, dataset, (method,))
            except FileNotFoundError:
                continue
    aggregate: dict[str, dict[str, float | int | None]] = {}
    for method in methods:
        rows = [artifacts[dataset][method]["results"][method] for dataset in DATASETS if method in artifacts[dataset]]
        aggregate[method] = {
            "dataset_count": len(rows),
            "ndcg_at_10_macro": sum(row["ndcg_at_10"] for row in rows) / len(rows),
            "recall_at_100_macro": sum(row["recall_at_100"] for row in rows) / len(rows),
            "mrr_at_10_macro": sum(row["mrr_at_10"] for row in rows) / len(rows),
            "mean_latency_ms_macro": sum(row["mean_latency_ms"] for row in rows) / len(rows),
            "index_build_seconds_sum": sum(row.get("index_build_seconds", 0.0) for row in rows),
            "estimated_cost_usd_sum": sum(row.get("estimated_cost_usd", 0.0) for row in rows),
        }
    payload = {
        "report_version": "vnext-retrieval-macro-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "datasets": DATASETS,
        "artifacts": {dataset: {method: artifacts[dataset][method]["_artifact"] for method in methods if method in artifacts[dataset]} for dataset in DATASETS},
        "results_by_dataset": {
            dataset: {method: artifacts[dataset][method]["results"].get(method) for method in methods if method in artifacts[dataset]}
            for dataset in DATASETS
        },
        "aggregate": aggregate,
        "scope_notice": "Retrieval-layer BEIR test metrics only; not clinical validity, full-agent quality, or SDTI.",
        "limitations": [
            "Methods are aggregated only over datasets with a real run.json result; missing method results are not estimated.",
            "No CrossEncoder result is included because its model download was incomplete and no proxy score is substituted.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# VNext Retrieval 五组公开 Benchmark 汇总",
        "",
        "> 仅为检索层 BEIR test 指标，不是临床有效性、全 Agent 质量或 SDTI 成绩。",
        "",
        "| 方法 | 数据集数 | nDCG@10 宏平均 | Recall@100 宏平均 | MRR@10 宏平均 | 平均查询延迟 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "project_bm25_tuned_v2": "Tuned BM25",
        "vnext_bge_small_en_v1_5": "VNext BGE-small-en-v1.5",
        "vnext_bm25_bge_fusion_v1": "VNext BM25+BGE Fusion",
    }
    for method in methods:
        row = aggregate[method]
        report.append(f"| {labels[method]} | {row['dataset_count']} | {row['ndcg_at_10_macro']:.4f} | {row['recall_at_100_macro']:.4f} | {row['mrr_at_10_macro']:.4f} | {row['mean_latency_ms_macro']:.2f} ms |")
    report.extend([
        "",
        "## 结论",
        "",
        "- BGE 与校准融合的结果按实际完成任务汇总；提升幅度因任务而异，不能外推为临床性能。",
        "- 融合权重只使用 train/dev qrels 选择，test qrels 仅用于最终报告；缺失任务不补值。",
        "- 当前没有 CrossEncoder 真实结果；下载、运行和评测完成前不报告 reranker 提升。",
        "",
        "## 可追溯产物",
        "",
    ])
    for dataset in DATASETS:
        for method in methods:
            if method in artifacts[dataset]:
                report.append(f"- `{dataset}` / `{method}`: `{artifacts[dataset][method]['_artifact']}`")
    report.extend([
        "",
        "## 限制",
        "",
        "- 所有数值均从 `run.json` 读取；缺失结果保持缺失，没有估算或补值。",
    ])
    report_path = args.output.with_suffix(".md")
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(args.output)
    print(report_path)


if __name__ == "__main__":
    main()
