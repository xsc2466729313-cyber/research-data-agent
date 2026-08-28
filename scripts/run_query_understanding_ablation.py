"""Run the query-understanding A-E ablation without leaking qrels to planning.

Qwen groups require a precomputed JSON plan cache. Missing plans are reported as
NOT_EVALUATED instead of silently receiving the baseline query.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_retrieval import (  # noqa: E402
    BEIR_DATASETS,
    QueryUnderstandingIndex,
    TunedBM25Index,
    evaluate_retriever,
    fit_bm25_parameters,
    load_beir,
    prepare_beir_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run A-E query-understanding ablation")
    parser.add_argument("--dataset", action="append", choices=sorted(BEIR_DATASETS), required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "beir")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--plan-cache", type=Path, default=None, help="JSON mapping raw query or query_id to RetrievalQueryPlan")
    args = parser.parse_args()
    raw_cache = json.loads(args.plan_cache.read_text(encoding="utf-8")) if args.plan_cache else {}
    plan_cache = raw_cache.get("entries", raw_cache) if isinstance(raw_cache, dict) else {}
    output: dict[str, object] = {
        "artifact_type": "query_understanding_ablation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "methods": {
            "A_raw": {"status": "EVALUATED", "description": "tuned BM25 on original query"},
            "B_rules": {"status": "EVALUATED", "description": "rules queries + RRF"},
            "C_qwen_single": {"status": "NOT_EVALUATED" if not plan_cache else "EVALUATED"},
            "D_qwen_multi": {"status": "NOT_EVALUATED" if not plan_cache else "EVALUATED"},
            "E_rules_qwen": {"status": "NOT_EVALUATED" if not plan_cache else "EVALUATED"},
        },
        "datasets": {},
        "notice": "Retrieval-layer diagnostics only; no clinical or SDTI claim. Qwen groups require an external plan cache and never receive qrels.",
    }
    for dataset_id in args.dataset:
        dataset_dir, manifest = prepare_beir_dataset(dataset_id, args.data_root, download=args.download)
        corpus, queries, qrels = load_beir(dataset_dir)
        config = fit_bm25_parameters(corpus, queries, dataset_dir)
        base = TunedBM25Index(corpus, k1=config.k1, b=config.b)
        planners = {"query": plan_cache}

        def planner(query: str):
            record = planners["query"].get(query)
            if not record:
                raise KeyError("Missing Qwen plan for query")
            if isinstance(record, dict) and record.get("status") != "VALID":
                raise ValueError("Qwen plan is not validated")
            return record.get("plan") if isinstance(record, dict) else record

        indexes = {
            "A_raw": base,
            "B_rules": QueryUnderstandingIndex(base, "rules"),
        }
        required_queries = [queries[query_id] for query_id in qrels if query_id in queries]
        complete_plan_cache = bool(plan_cache) and all(
            isinstance(plan_cache.get(query), dict) and plan_cache[query].get("status") == "VALID"
            for query in required_queries
        )
        if complete_plan_cache:
            indexes.update({
                "C_qwen_single": QueryUnderstandingIndex(base, "qwen_single", planner=planner),
                "D_qwen_multi": QueryUnderstandingIndex(base, "qwen_multi_validated", planner=planner),
                "E_rules_qwen": QueryUnderstandingIndex(base, "rules_qwen", planner=planner),
            })
        dataset_results: dict[str, object] = {"manifest": manifest, "bm25_config": {"k1": config.k1, "b": config.b}, "qwen_plan_cache_complete": complete_plan_cache, "results": {}}
        for method_id, index in indexes.items():
            dataset_results["results"][method_id] = {
                "status": "EVALUATED",
                **evaluate_retriever(index, queries, qrels).__dict__,
                "fallback_count": getattr(index, "fallback_count", 0),
            }
        output["datasets"][dataset_id] = dataset_results
    # Aggregate only completed dataset runs. This is an equal-weight macro
    # summary; it never participates in parameter fitting or method choice.
    metric_names = ("ndcg_at_10", "recall_at_100", "mrr_at_10", "mean_latency_ms")
    macro: dict[str, object] = {}
    for method_id in ("A_raw", "B_rules", "C_qwen_single", "D_qwen_multi", "E_rules_qwen"):
        rows = [
            dataset["results"][method_id]
            for dataset in output["datasets"].values()
            if method_id in dataset.get("results", {}) and dataset["results"][method_id].get("status") == "EVALUATED"
        ]
        if not rows:
            macro[method_id] = {"status": "NOT_EVALUATED"}
            continue
        macro[method_id] = {
            "status": "EVALUATED",
            "dataset_count": len(rows),
            **{name: sum(float(row[name]) for row in rows) / len(rows) for name in metric_names},
        }
    baseline = macro.get("A_raw")
    if isinstance(baseline, dict) and baseline.get("status") == "EVALUATED":
        for method_id, row in macro.items():
            if method_id == "A_raw" or not isinstance(row, dict) or row.get("status") != "EVALUATED":
                continue
            row["delta_vs_A"] = {
                name: float(row[name]) - float(baseline[name]) for name in metric_names
            }
    output["macro_average_equal_weight"] = macro
    destination = args.output or PROJECT_ROOT / "evaluation" / "query_understanding" / f"ablation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(destination), "datasets": args.dataset, "qwen_plan_cache": bool(plan_cache)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
