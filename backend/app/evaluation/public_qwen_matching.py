"""Qwen-assisted evaluation for the public schema/entity matching layers.

The evaluator keeps public labels outside model prompts.  Schema matching uses
the pinned Valentine tables and bounded value profiles. Entity matching uses
the official DeepMatcher pairs; train examples may be supplied as few-shot
context, while test labels are read only by the local scorer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.app.agent.qwen_client import QwenClient, QwenClientError
from backend.app.evaluation.public_entity import (
    ENTITY_DATASETS,
    EntityMetrics,
    evaluate_entity_pairs,
    load_entity_pairs,
    prepare_entity_dataset,
)
from backend.app.evaluation.public_schema import (
    SCHEMA_DATASETS,
    SchemaMetrics,
    evaluate_schema_matches,
    load_schema_task,
    prepare_schema_dataset,
)


@dataclass(frozen=True)
class QwenAudit:
    api_calls: int
    successful_calls: int
    failed_calls: int
    fallback_items: int
    qwen_items: int
    total_items: int
    batch_size: int
    model: str
    errors: tuple[str, ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _chunks(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[index:index + size]) for index in range(0, len(items), size)]


def _is_account_error(exc: Exception) -> bool:
    return "arrearage" in str(exc).casefold() or "overdue-payment" in str(exc).casefold()


def _bounded_samples(samples: Mapping[str, Sequence[str]], *, value_limit: int = 160) -> dict[str, list[str]]:
    """Keep model context bounded without changing the source tables."""
    return {
        str(column): [str(value)[:value_limit] for value in values[:16]]
        for column, values in samples.items()
    }


def _schema_predictions(
    source_columns: Sequence[str],
    target_columns: Sequence[str],
    values: dict[str, dict[str, Sequence[str]]],
    client: QwenClient,
) -> tuple[set[tuple[str, str]], QwenAudit, list[dict[str, Any]]]:
    item = {
        "item_id": "schema_task",
        "source_columns": list(source_columns),
        "target_columns": list(target_columns),
        "source_value_samples": _bounded_samples(values["source"]),
        "target_value_samples": _bounded_samples(values["target"]),
    }
    started = time.perf_counter()
    errors: list[str] = []
    try:
        result = client.match_schema_batch([item])["schema_task"]
        predictions = {
            (str(row["source_column"]), str(row["target_column"]))
            for row in result
        }
        audit = QwenAudit(1, 1, 0, 0, 1, 1, 1, client.settings.model)
        raw = [{**row, "used_qwen": True, "latency_ms": round((time.perf_counter() - started) * 1000, 3)} for row in result]
    except Exception as exc:
        errors.append(f"schema_task:{type(exc).__name__}:{str(exc)[:180]}")
        predictions = set()
        audit = QwenAudit(1, 0, 1, 1, 0, 1, 1, client.settings.model, tuple(errors))
        raw = []
    return predictions, audit, raw


def _entity_examples(
    train_pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
    *,
    limit_each: int = 6,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for label in (1, 0):
        selected = [pair for pair in train_pairs if pair[2] == label][:limit_each]
        examples.extend(
            {"left": left, "right": right, "label": bool(pair_label)}
            for left, right, pair_label in selected
        )
    return examples


def _entity_predictions(
    test_pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
    train_pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
    client: QwenClient,
    *,
    batch_size: int,
) -> tuple[list[bool], QwenAudit, list[dict[str, Any]]]:
    items = [
        {"pair_id": f"pair_{index:06d}", "left": left, "right": right}
        for index, (left, right, _label) in enumerate(test_pairs)
    ]
    predictions: list[bool] = []
    raw: list[dict[str, Any]] = []
    api_calls = successful = failed = fallback = qwen_items = 0
    errors: list[str] = []
    examples = _entity_examples(train_pairs)
    batches = _chunks(items, batch_size)
    for batch_index, batch in enumerate(batches):
        api_calls += 1
        try:
            decisions = client.match_entity_batch(batch, training_examples=examples)
            batch_predictions: list[bool] = []
            for item in batch:
                decision = decisions.get(item["pair_id"])
                if not isinstance(decision, dict):
                    raise QwenClientError(f"missing decision: {item['pair_id']}")
                prediction = bool(decision.get("match", False))
                batch_predictions.append(prediction)
                raw.append({"pair_id": item["pair_id"], **decision, "used_qwen": True})
            predictions.extend(batch_predictions)
            successful += 1
            qwen_items += len(batch)
        except Exception as exc:
            failed += 1
            account_error = _is_account_error(exc)
            pending_batches = batches[batch_index:] if account_error else [batch]
            remaining = sum(len(item) for item in pending_batches)
            fallback += remaining
            errors.append(f"{batch[0]['pair_id']}-{batch[-1]['pair_id']}:{type(exc).__name__}:{str(exc)[:180]}")
            # A failed Qwen batch is explicitly scored with the same project
            # rule used by the non-LLM evaluator; it is never mislabeled as Qwen.
            from backend.app.evaluation.public_entity import _predict
            for item, pair in zip(
                [entry for pending in pending_batches for entry in pending],
                test_pairs[len(predictions):len(predictions) + remaining],
            ):
                prediction = _predict("project_portability_rule_v1", pair[0], pair[1])
                predictions.append(prediction)
                raw.append({"pair_id": item["pair_id"], "match": prediction, "confidence": None, "used_qwen": False})
            if account_error:
                break
    audit = QwenAudit(
        api_calls, successful, failed, fallback, qwen_items, len(items), batch_size,
        client.settings.model, tuple(errors),
    )
    return predictions, audit, raw


def _entity_metrics_from_predictions(
    pairs: Sequence[tuple[dict[str, str], dict[str, str], int]],
    predictions: Sequence[bool],
) -> EntityMetrics:
    tp = fp = fn = 0
    for prediction, (_left, _right, label) in zip(predictions, pairs):
        if prediction and label == 1:
            tp += 1
        elif prediction and label == 0:
            fp += 1
        elif not prediction and label == 1:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return EntityMetrics(
        precision, recall, f1, tp, fp, fn, len(pairs), sum(label for _l, _r, label in pairs), 0.0
    )


def _write_run(
    *,
    project_root: Path,
    output_root: Path,
    dataset_id: str,
    stage: str,
    manifest: dict[str, Any],
    results: dict[str, Any],
    audit: QwenAudit,
    raw_predictions: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_qwen_{dataset_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": f"public-{stage}-qwen-v1",
        "layer": "external_benchmarks",
        "stage": stage,
        "dataset": manifest,
        "split": "test",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": {"provider": "qwen", "model": audit.model},
        "audit": asdict(audit),
        "baseline_method": baseline,
        "results": {key: asdict(value) if hasattr(value, "__dataclass_fields__") else value for key, value in results.items()},
        "scope_notice": "Generic public matching layer result; not a clinical patient identity or SDTI result.",
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "qwen_predictions.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in raw_predictions) + "\n", encoding="utf-8"
    )
    lines = [f"# {dataset_id} Qwen-assisted {stage}", "", "> Test labels were withheld from Qwen; this is a generic matching-layer result.", ""]
    if stage == "schema_matching":
        lines.extend(["| Method | Precision | Recall | F1 | TP | FP | FN |", "|---|---:|---:|---:|---:|---:|---:|"])
        for method, metrics in results.items():
            lines.append(f"| {method} | {metrics.precision:.4f} | {metrics.recall:.4f} | {metrics.f1:.4f} | {metrics.true_positive} | {metrics.false_positive} | {metrics.false_negative} |")
    else:
        lines.extend(["| Method | Precision | Recall | F1 | TP | FP | FN |", "|---|---:|---:|---:|---:|---:|---:|"])
        for method, metrics in results.items():
            lines.append(f"| {method} | {metrics.precision:.4f} | {metrics.recall:.4f} | {metrics.f1:.4f} | {metrics.true_positive} | {metrics.false_positive} | {metrics.false_negative} |")
    lines.extend([
        "", f"Qwen calls: {audit.successful_calls}/{audit.api_calls}; Qwen items: {audit.qwen_items}/{audit.total_items}; fallback items: {audit.fallback_items}",
        f"Source: {manifest.get('source_url', '')}", f"Test hash: `{manifest.get('test_sha256') or manifest.get('ground_truth_sha256', '')}`", f"Code revision: `{payload['code_revision']}`", "",
    ])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_qwen_schema(*, project_root: Path, dataset_id: str, data_root: Path, output_root: Path, client: QwenClient) -> Path:
    dataset_dir, manifest = prepare_schema_dataset(dataset_id, data_root, download=False)
    source, target, gold, source_samples, target_samples = load_schema_task(dataset_dir)
    qwen_pairs, audit, raw = _schema_predictions(
        source, target, {"source": source_samples, "target": target_samples}, client
    )
    # Reuse the common metric implementation so the Qwen and deterministic
    # methods have exactly the same official-label accounting.
    qwen_metrics = _metrics_for_predictions(source, target, gold, qwen_pairs)
    baseline = evaluate_schema_matches(source, target, gold, "project_schema_v3", source_samples=source_samples, target_samples=target_samples)
    return _write_run(
        project_root=project_root, output_root=output_root, dataset_id=dataset_id, stage="schema_matching",
        manifest={**manifest, "test_sha256": manifest["ground_truth_sha256"]},
        results={"qwen_schema": qwen_metrics, "project_schema_v3": baseline}, audit=audit, raw_predictions=raw,
        baseline={"method": "project_schema_v3", "f1": baseline.f1},
    )


def _metrics_for_predictions(
    source: Sequence[str], target: Sequence[str], gold: set[tuple[str, str]], predictions: set[tuple[str, str]]
) -> SchemaMetrics:
    tp = len(predictions & gold)
    fp = len(predictions - gold)
    fn = len(gold - predictions)
    precision = tp / len(predictions) if predictions else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return SchemaMetrics(precision, recall, f1, tp, fp, fn, len(predictions), len(gold), len(source), len(target), 0.0)


def run_qwen_entity(*, project_root: Path, dataset_id: str, data_root: Path, output_root: Path, client: QwenClient, batch_size: int = 64) -> Path:
    dataset_dir, manifest = prepare_entity_dataset(dataset_id, data_root, download=False)
    train_pairs, _ = load_entity_pairs(dataset_dir, "train")
    test_pairs, stats = load_entity_pairs(dataset_dir, "test")
    predictions, audit, raw = _entity_predictions(test_pairs, train_pairs, client, batch_size=batch_size)
    qwen_metrics = _entity_metrics_from_predictions(test_pairs, predictions)
    baseline = evaluate_entity_pairs(test_pairs, "project_portability_rule_v1")
    data_dir = dataset_dir / "exp_data" / dataset_id.removeprefix("deepmatcher_")
    if not data_dir.exists():
        data_dir = next(path for path in dataset_dir.rglob("train.csv") if path.parent != dataset_dir).parent
    return _write_run(
        project_root=project_root, output_root=output_root, dataset_id=dataset_id, stage="entity_matching",
        manifest={**manifest, "test_sha256": _sha256(data_dir / "test.csv"), "test_pair_count": stats["pair_count"]},
        results={"qwen_entity": qwen_metrics, "project_portability_rule_v1": baseline}, audit=audit, raw_predictions=raw,
        baseline={"method": "project_portability_rule_v1", "f1": baseline.f1},
    )
