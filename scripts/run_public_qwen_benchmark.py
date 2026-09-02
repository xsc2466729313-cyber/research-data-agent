"""Run real Qwen conditions on the public problem, retrieval, and cleaning benchmarks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.qwen_client import QwenClient, QwenClientError
from backend.app.evaluation.public_cleaning import (
    CLEANING_DATASETS,
    _metrics,
    _project_source_anchor_repair_v6,
    evaluate_cleaning,
    load_cleaning_dataset,
    prepare_cleaning_dataset,
)
from backend.app.evaluation.public_problem_understanding import (
    PICO_ELEMENTS,
    _evaluate_labels,
    load_pico_examples,
    prepare_ebm_nlp_dataset,
)
from backend.app.evaluation.public_retrieval import (
    BEIR_DATASETS,
    BM25Index,
    evaluate_retriever,
    load_beir,
    prepare_beir_dataset,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _batches(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _account_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    return "arrearage" in text or "overdue-payment" in text


def run_problem(client: QwenClient, data_root: Path, batch_size: int) -> dict:
    dataset_dir, manifest = prepare_ebm_nlp_dataset(data_root, download=False)
    result: dict[str, object] = {
        "dataset": "ebm_nlp_2_00",
        "split": "professional_test_gold",
        "manifest": manifest,
        "batch_size": batch_size,
        "methods": {},
        "api_calls": 0,
        "api_failures": 0,
        "failure_messages": [],
        "items": 0,
        "account_blocked": False,
    }
    by_element: dict[str, object] = {}
    for element in PICO_ELEMENTS:
        examples = load_pico_examples(dataset_dir, element, "test")
        predictions: dict[str, list[int]] = {}
        batches = list(_batches(
            [{"item_id": pmid, "tokens": tokens} for pmid, tokens, _ in examples],
            batch_size,
        ))
        for batch_number, batch in enumerate(batches, start=1):
            print(f"[problem/{element}] batch {batch_number}/{len(batches)}", flush=True)
            if result["account_blocked"]:
                for item in batch:
                    predictions[str(item["item_id"])] = [0] * len(item["tokens"])
                continue
            result["api_calls"] = int(result["api_calls"]) + 1
            try:
                predictions.update(client.label_pico_batch(batch, element=element))
            except QwenClientError as exc:
                result["api_failures"] = int(result["api_failures"]) + 1
                result["failure_messages"].append(f"{element}:{batch[0]['item_id']}:{type(exc).__name__}:{exc}")
                result["account_blocked"] = _account_error(exc)
                for item in batch:
                    predictions[str(item["item_id"])] = [0] * len(item["tokens"])
        labels = [predictions[pmid] for pmid, _, _ in examples]
        metrics = _evaluate_labels(labels, examples, 0.0)
        by_element[element] = asdict(metrics)
        result["items"] = int(result["items"]) + len(examples)
    macro = {
        key: sum(float(item[key]) for item in by_element.values()) / len(by_element)
        for key in ("precision", "recall", "f1", "mean_latency_ms")
    }
    result["methods"] = {"qwen_batch": {**by_element, "macro": macro}}
    return result


class RewrittenBM25:
    method_id = "qwen_query_rewrite_bm25"
    method_label = "Qwen query rewrite + BM25"

    def __init__(self, base: BM25Index, rewrites: dict[str, str]) -> None:
        self.base = base
        self.rewrites = rewrites
        self.index_build_seconds = 0.0
        self.estimated_cost_usd = 0.0
        self.qwen_invocation_rate = 1.0

    def rank(self, query: str, top_k: int) -> list[str]:
        return self.base.rank(self.rewrites.get(query, query), top_k)


def run_retrieval(
    client: QwenClient,
    data_root: Path,
    dataset_ids: list[str],
    batch_size: int,
) -> dict:
    output: dict[str, object] = {
        "split": "test",
        "batch_size": batch_size,
        "datasets": {},
        "api_calls": 0,
        "api_failures": 0,
        "failure_messages": [],
        "query_count": 0,
        "qwen_native_rewrite_count": 0,
        "raw_query_fallback_count": 0,
        "account_blocked": False,
    }
    for dataset_id in dataset_ids:
        dataset_dir, manifest = prepare_beir_dataset(dataset_id, data_root, download=False)
        corpus, queries, qrels = load_beir(dataset_dir)
        eligible = [query_id for query_id in sorted(qrels) if query_id in queries]
        rewrites: dict[str, str] = {}
        batches = list(_batches(
            [{"item_id": query_id, "query": queries[query_id]} for query_id in eligible],
            batch_size,
        ))
        for batch_number, batch in enumerate(batches, start=1):
            print(f"[retrieval/{dataset_id}] batch {batch_number}/{len(batches)}", flush=True)
            if output["account_blocked"]:
                for item in batch:
                    rewrites[str(item["item_id"])] = str(item["query"])
                output["raw_query_fallback_count"] = int(output["raw_query_fallback_count"]) + len(batch)
                continue
            output["api_calls"] = int(output["api_calls"]) + 1
            try:
                values = client.rewrite_retrieval_batch(batch)
                for item in batch:
                    rewrites[str(item["item_id"])] = values[str(item["item_id"])]
                output["qwen_native_rewrite_count"] = int(output["qwen_native_rewrite_count"]) + len(batch)
            except QwenClientError as exc:
                output["api_failures"] = int(output["api_failures"]) + 1
                output["failure_messages"].append(f"{dataset_id}:{batch[0]['item_id']}:{type(exc).__name__}:{exc}")
                output["account_blocked"] = _account_error(exc)
                for item in batch:
                    rewrites[str(item["item_id"])] = str(item["query"])
                output["raw_query_fallback_count"] = int(output["raw_query_fallback_count"]) + len(batch)
        base = BM25Index(corpus)
        qwen_metrics = evaluate_retriever(
            RewrittenBM25(base, {queries[key]: value for key, value in rewrites.items()}),
            queries,
            qrels,
        )
        baseline = evaluate_retriever(base, queries, qrels)
        output["query_count"] = int(output["query_count"]) + len(eligible)
        output["datasets"][dataset_id] = {
            "manifest": manifest,
            "baseline_bm25": asdict(baseline),
            "qwen_query_rewrite_bm25": asdict(qwen_metrics),
            "rewritten_query_count": len(rewrites),
        }
    return output


def run_cleaning(
    client: QwenClient,
    data_root: Path,
    dataset_ids: list[str],
    batch_size: int,
) -> dict:
    output: dict[str, object] = {
        "split": "aligned_dirty_clean",
        "batch_size": batch_size,
        "datasets": {},
        "api_calls": 0,
        "api_failures": 0,
        "failure_messages": [],
        "row_count": 0,
        "account_blocked": False,
    }
    for dataset_id in dataset_ids:
        dataset_dir, manifest = prepare_cleaning_dataset(dataset_id, data_root, download=False)
        dirty, clean = load_cleaning_dataset(dataset_dir)
        baseline_repaired = evaluate_cleaning(dirty, clean, "project_source_anchor_repair_v6")
        repaired = [row.copy() for row in dirty]
        deterministic = _project_source_anchor_repair_v6(dirty)
        # The model only proposes additional cells; established local repairs
        # remain authoritative and are not overwritten by a model guess.
        repaired = [row.copy() for row in deterministic]
        columns = list(dirty[0])
        batches = list(_batches(dirty, batch_size))
        for start, rows in enumerate(batches):
            print(f"[cleaning/{dataset_id}] batch {start + 1}/{len(batches)}", flush=True)
            batch = [
                {"row_index": index, "values": row}
                for index, row in enumerate(rows)
            ]
            if output["account_blocked"]:
                continue
            output["api_calls"] = int(output["api_calls"]) + 1
            try:
                repairs = client.clean_table_batch(columns=columns, rows=batch)
                for item in repairs:
                    index = start * batch_size + int(item["row_index"])
                    column = str(item["column"])
                    if index < 0 or index >= len(repaired) or column not in columns:
                        continue
                    if repaired[index][column] == dirty[index][column]:
                        repaired[index][column] = str(item["value"])
            except QwenClientError as exc:
                output["api_failures"] = int(output["api_failures"]) + 1
                output["failure_messages"].append(f"{dataset_id}:{start * batch_size}:{type(exc).__name__}:{exc}")
                output["account_blocked"] = _account_error(exc)
        qwen_metrics = _metrics(dirty, clean, repaired, 0.0)
        baseline = baseline_repaired
        output["row_count"] = int(output["row_count"]) + len(dirty)
        output["datasets"][dataset_id] = {
            "manifest": manifest,
            "baseline_project_source_anchor_v6": asdict(baseline),
            "qwen_table_cleaning": asdict(qwen_metrics),
        }
    return output


def write_run(output_root: Path, payload: dict) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_qwen_public_benchmark"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload["evaluation_id"] = run_dir.name
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Public benchmark with real Qwen",
        "",
        "> Qwen saw only raw benchmark inputs. Test labels were used only for final scoring.",
        "",
    ]
    if "problem" in payload:
        macro = payload["problem"]["methods"]["qwen_batch"]["macro"]
        lines.extend([
            "## Problem understanding: EBM-NLP",
            "",
            f"Qwen macro span F1: **{macro['f1']:.4f}**",
            f"API calls: {payload['problem']['api_calls']}; failures: {payload['problem']['api_failures']}",
            "",
        ])
    if "retrieval" in payload:
        lines.extend(["## Retrieval: BEIR", "", "| Dataset | BM25 nDCG@10 | Qwen rewrite nDCG@10 | BM25 Recall@100 | Qwen Recall@100 |", "|---|---:|---:|---:|---:|"])
        for dataset_id, item in payload["retrieval"]["datasets"].items():
            base, qwen = item["baseline_bm25"], item["qwen_query_rewrite_bm25"]
            lines.append(f"| {dataset_id} | {base['ndcg_at_10']:.4f} | {qwen['ndcg_at_10']:.4f} | {base['recall_at_100']:.4f} | {qwen['recall_at_100']:.4f} |")
        lines.extend(["", f"API calls: {payload['retrieval']['api_calls']}; failures: {payload['retrieval']['api_failures']}", ""])
    if "cleaning" in payload:
        lines.extend(["## Cleaning: Raha/HoloClean", "", "| Dataset | v5 Cell F1 | Qwen Cell F1 | v5 Repair Accuracy | Qwen Repair Accuracy |", "|---|---:|---:|---:|---:|"])
        for dataset_id, item in payload["cleaning"]["datasets"].items():
            base, qwen = item["baseline_project_source_anchor_v6"], item["qwen_table_cleaning"]
            lines.append(f"| {dataset_id} | {base['cell_f1']:.4f} | {qwen['cell_f1']:.4f} | {base['repair_accuracy']:.4f} | {qwen['repair_accuracy']:.4f} |")
        lines.extend(["", f"API calls: {payload['cleaning']['api_calls']}; failures: {payload['cleaning']['api_failures']}", ""])
    lines.extend([
        "## Reproducibility",
        "",
        "- Model: real Qwen configured by the local project environment; API key is not stored.",
        "- No test labels, qrels, clean tables, or hidden annotations were sent to Qwen.",
        "- A failed batch produces no repairs/rewrites and is counted as an API failure.",
    ])
    (run_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", action="append", choices=("problem", "retrieval", "cleaning"))
    parser.add_argument("--retrieval-dataset", action="append", choices=sorted(BEIR_DATASETS))
    parser.add_argument("--cleaning-dataset", action="append", choices=sorted(CLEANING_DATASETS))
    parser.add_argument("--problem-batch-size", type=int, default=4)
    parser.add_argument("--retrieval-batch-size", type=int, default=16)
    parser.add_argument("--cleaning-batch-size", type=int, default=24)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    layers = set(args.layer or ("problem", "retrieval", "cleaning"))
    client = QwenClient()
    if not client.available:
        raise SystemExit("Qwen API is not configured; set DASHSCOPE_API_KEY in the local environment.")
    payload: dict[str, object] = {
        "evaluation_version": "public-qwen-v1",
        "layer": "external_benchmarks",
        "model_provider": client.settings.provider,
        "model_name": client.settings.model,
        "test_labels_sent_to_model": False,
    }
    try:
        if "problem" in layers:
            payload["problem"] = run_problem(client, PROJECT_ROOT / "data" / "benchmarks" / "problem", args.problem_batch_size)
        if "retrieval" in layers:
            datasets = args.retrieval_dataset or ["beir_scifact"]
            payload["retrieval"] = run_retrieval(client, PROJECT_ROOT / "data" / "benchmarks" / "beir", datasets, args.retrieval_batch_size)
        if "cleaning" in layers:
            datasets = args.cleaning_dataset or ["raha_flights"]
            payload["cleaning"] = run_cleaning(client, PROJECT_ROOT / "data" / "benchmarks" / "cleaning", datasets, args.cleaning_batch_size)
    finally:
        client.close()
    print(write_run(args.output_root, payload))


if __name__ == "__main__":
    main()
