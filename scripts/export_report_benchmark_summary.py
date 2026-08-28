"""Export measured evaluation artifacts into a report-side evidence summary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = PROJECT_ROOT / "data" / "output" / "evaluation" / "qwen38_full_evaluation_20260829"

DATASET_LABELS = {
    "beir_scifact": ("SciFact", "科学事实核验"),
    "beir_nfcorpus": ("NFCorpus", "生物医学检索"),
    "beir_scidocs": ("SciDocs", "科学论文检索"),
    "beir_arguana": ("ArguAna", "长论证检索"),
    "beir_fiqa": ("FiQA", "金融问答检索"),
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_summary(
    retrieval: dict[str, object],
    query_ablation: dict[str, object],
    planner_comparison: dict[str, object],
    closed_loop: dict[str, object],
) -> dict[str, object]:
    aggregate = retrieval["aggregate"]
    results_by_dataset = retrieval["results_by_dataset"]
    methods = [
        ("project_bm25_tuned_v2", "BM25 对照组"),
        ("vnext_bge_small_en_v1_5", "本项目 BGE 语义检索"),
        ("vnext_bm25_bge_fusion_v1", "本项目 BM25+BGE 融合"),
    ]
    query_count = sum(
        int(row["project_bm25_tuned_v2"]["query_count"])
        for row in results_by_dataset.values()
    )
    retrieval_methods = [
        {
            "method_id": method_id,
            "label": label,
            "ndcg_at_10": float(aggregate[method_id]["ndcg_at_10_macro"]),
            "recall_at_100": float(aggregate[method_id]["recall_at_100_macro"]),
            "mrr_at_10": float(aggregate[method_id]["mrr_at_10_macro"]),
        }
        for method_id, label in methods
    ]
    strata = []
    for dataset_id, (label, domain) in DATASET_LABELS.items():
        rows = results_by_dataset[dataset_id]
        baseline = rows["project_bm25_tuned_v2"]
        project = rows["vnext_bge_small_en_v1_5"]
        strata.append({
            "dataset_id": dataset_id,
            "label": label,
            "domain": domain,
            "query_count": int(baseline["query_count"]),
            "bm25_ndcg_at_10": float(baseline["ndcg_at_10"]),
            "project_ndcg_at_10": float(project["ndcg_at_10"]),
            "delta_ndcg_at_10": float(project["ndcg_at_10"]) - float(baseline["ndcg_at_10"]),
        })

    query_macro = query_ablation["macro_average_equal_weight"]
    ablation = [
        {
            "method_id": method_id,
            "label": label,
            "ndcg_at_10": float(query_macro[method_id]["ndcg_at_10"]),
            "recall_at_100": float(query_macro[method_id]["recall_at_100"]),
            "mrr_at_10": float(query_macro[method_id]["mrr_at_10"]),
        }
        for method_id, label in (
            ("A_raw", "A 原始查询（对照）"),
            ("C_qwen_single", "C Qwen 单查询"),
            ("D_qwen_multi", "D Qwen 多查询"),
            ("E_rules_qwen", "E 规则 + Qwen"),
        )
    ]

    planner_rows = planner_comparison["summary"]
    qwen_key = next(key for key in planner_rows if "Qwen" in key)
    deepseek_key = next(key for key in planner_rows if "DeepSeek" in key)
    qwen = planner_rows[qwen_key]
    deepseek = planner_rows[deepseek_key]
    model_comparison = {
        "protocol": planner_comparison["metadata"]["protocol"],
        "cases_per_group": int(qwen["cases"]),
        "qwen": {
            "label": "本项目 Qwen3.8-Max",
            "recall_at_3": float(qwen["metrics"]["recall@3"]),
            "mrr_at_3": float(qwen["metrics"]["mrr@3"]),
            "ndcg_at_3": float(qwen["metrics"]["ndcg@3"]),
            "avg_latency_ms": float(qwen["metrics"]["avg_latency_ms"]),
        },
        "deepseek": {
            "label": "DeepSeek 替换组",
            "recall_at_3": float(deepseek["metrics"]["recall@3"]),
            "mrr_at_3": float(deepseek["metrics"]["mrr@3"]),
            "ndcg_at_3": float(deepseek["metrics"]["ndcg@3"]),
            "avg_latency_ms": float(deepseek["metrics"]["avg_latency_ms"]),
        },
    }

    rounds = closed_loop["iterations"]
    first, second = rounds[0], rounds[-1]
    loop_summary = {
        "model": second["result"]["model_name"],
        "rounds": int(closed_loop["completed_iterations"]),
        "first": first["metrics"],
        "second": second["metrics"],
        "score_delta": float(second["metrics"]["progress_score"]) - float(first["metrics"]["progress_score"]),
    }

    return {
        "artifact_type": "report_evaluation_summary",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope_notice": "公开 benchmark 与受控 Agent 消融实测；不是临床有效性或正式 SDTI。",
        "formal_sdti": "NOT_EVALUATED",
        "retrieval": {
            "dataset_count": len(strata),
            "query_count": query_count,
            "methods": retrieval_methods,
            "strata": strata,
        },
        "query_ablation": {
            "query_count": sum(int(row["evaluation_query_count"]) for row in query_ablation["datasets"].values()),
            "methods": ablation,
            "decision": "E 组只提高 Recall@100，nDCG@10 下降；生产继续使用 raw/compat 默认。",
        },
        "model_comparison": model_comparison,
        "closed_loop": loop_summary,
        "evidence_files": [
            "evaluation/vnext_retrieval_calibrated_macro_20260828.json",
            "evaluation/reports/qwen38_20260829/query_understanding_ablation.json",
            "evaluation/reports/qwen38_20260829/planner_replacement_ablation.json",
            "evaluation/reports/qwen38_20260829/FINAL_EVALUATION_REPORT_ZH.md",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export measured benchmark data for the evaluation report")
    parser.add_argument("--output", type=Path, default=RUN_ROOT / "report_metrics_summary.json")
    args = parser.parse_args()
    payload = build_summary(
        _load(PROJECT_ROOT / "evaluation" / "vnext_retrieval_calibrated_macro_20260828.json"),
        _load(RUN_ROOT / "query_understanding_ablation.json"),
        _load(PROJECT_ROOT / "data" / "output" / "evaluation" / "planner_replacement_qwen38_20260829" / "planner_replacement_ablation.json"),
        _load(RUN_ROOT / "closed_loop_qwen38_live.json"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "queries": payload["retrieval"]["query_count"], "datasets": payload["retrieval"]["dataset_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
