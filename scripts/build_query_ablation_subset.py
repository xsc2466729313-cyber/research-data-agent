"""Freeze a deterministic, length-stratified BEIR query subset for ablation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_retrieval import BEIR_DATASETS, prepare_beir_dataset  # noqa: E402
from backend.app.retrieval_text_features import retrieval_tokens  # noqa: E402
from scripts.build_qwen_query_plan_cache import load_queries_without_qrels  # noqa: E402


def load_test_query_ids(dataset_dir: Path) -> set[str]:
    query_ids: set[str] = set()
    with (dataset_dir / "qrels" / "test.tsv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            query_id = str(row.get("query-id") or row.get("query_id") or "").strip()
            score = float(row.get("score") or 0)
            if query_id and score > 0:
                query_ids.add(query_id)
    return query_ids


def select_length_stratified_queries(
    queries: dict[str, str],
    eligible_ids: set[str],
    *,
    count: int,
    seed: str,
) -> list[dict[str, object]]:
    eligible = [
        (query_id, len(retrieval_tokens(queries[query_id])))
        for query_id in eligible_ids
        if query_id in queries
    ]
    eligible.sort(key=lambda item: (item[1], item[0]))
    if count > len(eligible):
        raise ValueError(f"Requested {count} queries from only {len(eligible)} eligible queries")

    boundaries = (len(eligible) // 3, 2 * len(eligible) // 3)
    buckets = {
        "short": eligible[: boundaries[0]],
        "medium": eligible[boundaries[0] : boundaries[1]],
        "long": eligible[boundaries[1] :],
    }
    base, remainder = divmod(count, 3)
    allocations = {
        label: base + (1 if index < remainder else 0)
        for index, label in enumerate(("short", "medium", "long"))
    }
    selected: list[dict[str, object]] = []
    for label, bucket in buckets.items():
        ranked = sorted(
            bucket,
            key=lambda item: hashlib.sha256(f"{seed}:{label}:{item[0]}".encode()).hexdigest(),
        )
        for query_id, token_count in ranked[: allocations[label]]:
            selected.append({"query_id": query_id, "stratum": label, "token_count": token_count})
    return sorted(selected, key=lambda item: (str(item["stratum"]), str(item["query_id"])))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a frozen BEIR ablation query subset")
    parser.add_argument("--dataset", action="append", choices=sorted(BEIR_DATASETS), required=True)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "beir")
    parser.add_argument("--queries-per-dataset", type=int, default=15)
    parser.add_argument("--seed", default="20260829")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.queries_per_dataset < 3:
        parser.error("--queries-per-dataset must be at least 3")

    datasets: dict[str, object] = {}
    for dataset_id in args.dataset:
        dataset_dir, source = prepare_beir_dataset(dataset_id, args.data_root, download=False)
        queries = load_queries_without_qrels(dataset_dir)
        eligible_ids = load_test_query_ids(dataset_dir)
        selected = select_length_stratified_queries(
            queries,
            eligible_ids,
            count=args.queries_per_dataset,
            seed=f"{args.seed}:{dataset_id}",
        )
        datasets[dataset_id] = {
            "source_id": source["source_id"],
            "source_url": source["source_url"],
            "queries_sha256": source["queries_sha256"],
            "qrels_test_sha256": source["qrels_test_sha256"],
            "eligible_query_count": len(eligible_ids & set(queries)),
            "selected_query_count": len(selected),
            "selected": selected,
        }

    payload = {
        "artifact_type": "query_ablation_subset_manifest",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_method": "deterministic SHA-256 sampling within query-token-length tertiles",
        "seed": args.seed,
        "leakage_notice": "Only query IDs identify the held-out subset; relevance document IDs and gains are never provided to the query planner.",
        "datasets": datasets,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "datasets": len(datasets), "queries": sum(item["selected_query_count"] for item in datasets.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
