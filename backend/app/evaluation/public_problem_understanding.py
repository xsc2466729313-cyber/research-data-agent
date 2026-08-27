"""Reproducible PICO span evaluation on the public EBM-NLP corpus.

The benchmark measures token-span detection only.  It is a diagnostic for the
problem-understanding layer, not a clinical decision or a breast-cancer Gold
Set score.  Training uses crowd-aggregated labels; the held-out test uses the
separate professional ``gold`` labels supplied by EBM-NLP.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


EBM_NLP_SOURCE_ID = "github:bepnye/EBM-NLP"
EBM_NLP_SOURCE_URL = "https://github.com/bepnye/EBM-NLP"
EBM_NLP_ARCHIVE_URL = "https://github.com/bepnye/EBM-NLP/raw/master/ebm_nlp_2_00.tar.gz"
EBM_NLP_FOLDER = "ebm_nlp_2_00"
PICO_ELEMENTS = ("participants", "interventions", "outcomes")


@dataclass(frozen=True)
class PicoMetrics:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    token_count: int
    positive_count: int
    predicted_positive_count: int
    document_count: int
    mean_latency_ms: float


@dataclass(frozen=True)
class PicoLexiconConfig:
    threshold: float
    min_count: int
    fit_documents: int
    fit_split: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError(f"Unsafe archive member: {member.name}")
        tar.extractall(destination)


def prepare_ebm_nlp_dataset(data_root: Path, *, download: bool) -> tuple[Path, dict[str, str]]:
    data_root.mkdir(parents=True, exist_ok=True)
    archive = data_root / "ebm_nlp_2_00.tar.gz"
    dataset_dir = data_root / EBM_NLP_FOLDER
    required = [
        dataset_dir / "documents",
        dataset_dir / "annotations" / "aggregated" / "starting_spans" / "participants" / "test" / "gold",
    ]
    if any(not path.exists() for path in required):
        if not download:
            raise FileNotFoundError("EBM-NLP is missing. Re-run with --download.")
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + ".part")
            with urllib.request.urlopen(EBM_NLP_ARCHIVE_URL, timeout=120) as response, partial.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
            partial.replace(archive)
        _safe_extract(archive, data_root)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"EBM-NLP archive is incomplete: {missing}")
    manifest = {
        "dataset_id": "ebm_nlp_2_00",
        "source_id": EBM_NLP_SOURCE_ID,
        "source_url": EBM_NLP_SOURCE_URL,
        "archive_url": EBM_NLP_ARCHIVE_URL,
        "archive_sha256": _sha256(archive) if archive.exists() else "archive-not-retained",
    }
    for element in PICO_ELEMENTS:
        for split_path in (
            dataset_dir / "annotations" / "aggregated" / "starting_spans" / element / "train",
            dataset_dir / "annotations" / "aggregated" / "starting_spans" / element / "test" / "gold",
        ):
            split = "train" if split_path.name == "train" else f"test_gold_{element}"
            files = sorted(split_path.glob("*.ann"))
            digest = hashlib.sha256()
            for path in files:
                digest.update(path.name.encode("utf-8"))
                digest.update(path.read_bytes())
            manifest[f"{split}_sha256"] = digest.hexdigest()
            manifest[f"{split}_count"] = str(len(files))
    return dataset_dir, manifest


def _normalise_token(token: str) -> str:
    return re.sub(r"\s+", " ", str(token or "").casefold()).strip()


def _read_tokens(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _read_labels(path: Path) -> list[int]:
    return [int(value.strip()) for value in path.read_text(encoding="utf-8").splitlines() if value.strip()]


def _annotation_dir(dataset_dir: Path, element: str, split: str) -> Path:
    root = dataset_dir / "annotations" / "aggregated" / "starting_spans" / element
    return root / "train" if split == "train" else root / "test" / "gold"


def load_pico_examples(dataset_dir: Path, element: str, split: str) -> list[tuple[str, list[str], list[int]]]:
    if element not in PICO_ELEMENTS:
        raise ValueError(f"Unsupported PICO element: {element}")
    examples: list[tuple[str, list[str], list[int]]] = []
    for annotation in sorted(_annotation_dir(dataset_dir, element, split).glob("*.ann")):
        pmid = annotation.name.split(".", 1)[0]
        token_path = dataset_dir / "documents" / f"{pmid}.tokens"
        if not token_path.exists():
            continue
        tokens, labels = _read_tokens(token_path), _read_labels(annotation)
        if len(tokens) != len(labels):
            raise ValueError(f"Token/label length mismatch for {pmid} ({element}, {split})")
        examples.append((pmid, tokens, labels))
    if not examples:
        raise ValueError(f"No EBM-NLP examples found for {element}/{split}")
    return examples


def _f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _evaluate_labels(predictions: list[list[int]], examples: list[tuple[str, list[str], list[int]]], elapsed_ms: float) -> PicoMetrics:
    tp = fp = fn = token_count = positive_count = predicted_positive_count = 0
    for predicted, (_, tokens, labels) in zip(predictions, examples):
        for output, expected in zip(predicted, labels):
            token_count += 1
            positive_count += expected
            predicted_positive_count += output
            if output and expected:
                tp += 1
            elif output:
                fp += 1
            elif expected:
                fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return PicoMetrics(
        precision=precision,
        recall=recall,
        f1=_f1(tp, fp, fn),
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        token_count=token_count,
        positive_count=positive_count,
        predicted_positive_count=predicted_positive_count,
        document_count=len(examples),
        mean_latency_ms=elapsed_ms / max(1, token_count),
    )


def fit_token_lexicon(examples: list[tuple[str, list[str], list[int]]], *, threshold: float = 0.5, min_count: int = 2) -> dict[str, float]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for _, tokens, labels in examples:
        for token, label in zip(tokens, labels):
            key = _normalise_token(token)
            if not key:
                continue
            counts[key][0] += label
            counts[key][1] += 1
    return {
        token: positive / total
        for token, (positive, total) in counts.items()
        if total >= min_count and positive / total >= threshold
    }


def _predict_lexicon(
    examples: list[tuple[str, list[str], list[int]]],
    lexicon: dict[str, float],
    *,
    threshold: float = 0.5,
) -> list[list[int]]:
    return [
        [int(lexicon.get(_normalise_token(token), 0.0) >= threshold) for token in tokens]
        for _, tokens, _ in examples
    ]


def _fit_context_lexicon(examples: list[tuple[str, list[str], list[int]]], min_count: int = 2) -> dict[str, float]:
    """Estimate local token context probabilities from training labels only."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for _, tokens, labels in examples:
        for index, label in enumerate(labels):
            token = _normalise_token(tokens[index])
            previous = _normalise_token(tokens[index - 1]) if index else "<B>"
            following = _normalise_token(tokens[index + 1]) if index + 1 < len(tokens) else "<E>"
            for key in (f"prev={previous}|{token}", f"next={token}|{following}"):
                counts[key][0] += label
                counts[key][1] += 1
    return {key: positive / total for key, (positive, total) in counts.items() if total >= min_count}


def _predict_context_lexicon(
    examples: list[tuple[str, list[str], list[int]]],
    token_lexicon: dict[str, float],
    context_lexicon: dict[str, float],
    *,
    token_weight: float = 0.5,
    threshold: float = 0.5,
) -> list[list[int]]:
    output: list[list[int]] = []
    for _, tokens, _ in examples:
        row: list[int] = []
        for index, token in enumerate(tokens):
            normalised = _normalise_token(token)
            previous = _normalise_token(tokens[index - 1]) if index else "<B>"
            following = _normalise_token(tokens[index + 1]) if index + 1 < len(tokens) else "<E>"
            context = (
                context_lexicon.get(f"prev={previous}|{normalised}", 0.0)
                + context_lexicon.get(f"next={normalised}|{following}", 0.0)
            ) / 2.0
            score = token_weight * token_lexicon.get(normalised, 0.0) + (1.0 - token_weight) * context
            row.append(int(score >= threshold))
        output.append(row)
    return output


def _select_lexicon_config(
    examples: list[tuple[str, list[str], list[int]]],
) -> PicoLexiconConfig:
    """Select lexicon sparsity on a deterministic train-only development fold."""

    development = [
        example for example in examples
        if int(hashlib.sha256(example[0].encode("utf-8")).hexdigest()[-2:], 16) % 5 == 0
    ]
    fitting = [example for example in examples if example not in development]
    if not development or not fitting:
        return PicoLexiconConfig(0.5, 2, len(examples), "train")
    best: tuple[float, float, int] | None = None
    for threshold in (0.30, 0.40, 0.50, 0.60, 0.70):
        for min_count in (1, 2, 3, 5):
            lexicon = fit_token_lexicon(fitting, threshold=threshold, min_count=min_count)
            metrics = _evaluate_labels(
                _predict_lexicon(development, lexicon, threshold=threshold),
                development,
                0.0,
            )
            candidate = (metrics.f1, threshold, min_count)
            if best is None or candidate > best:
                best = candidate
    assert best is not None
    return PicoLexiconConfig(best[1], best[2], len(examples), "train_internal_dev")


def evaluate_pico_dataset(
    dataset_dir: Path,
) -> tuple[dict[str, dict[str, PicoMetrics]], dict[str, dict[str, PicoLexiconConfig]]]:
    train_by_element = {element: load_pico_examples(dataset_dir, element, "train") for element in PICO_ELEMENTS}
    test_by_element = {element: load_pico_examples(dataset_dir, element, "test") for element in PICO_ELEMENTS}
    v1_lexicons = {
        element: fit_token_lexicon(train_by_element[element])
        for element in PICO_ELEMENTS
    }
    v2_configs = {
        element: _select_lexicon_config(train_by_element[element])
        for element in PICO_ELEMENTS
    }
    v2_lexicons = {
        element: fit_token_lexicon(
            train_by_element[element],
            threshold=v2_configs[element].threshold,
            min_count=v2_configs[element].min_count,
        )
        for element in PICO_ELEMENTS
    }
    context_lexicons = {
        element: _fit_context_lexicon(train_by_element[element], v2_configs[element].min_count)
        for element in PICO_ELEMENTS
    }
    methods: dict[str, dict[str, PicoMetrics]] = {
        "zero_prediction": {},
        "token_lexicon_v1": {},
        "project_pico_lexicon_v2": {},
        "project_pico_context_v3": {},
    }
    configs: dict[str, dict[str, PicoLexiconConfig]] = {
        "token_lexicon_v1": {
            element: PicoLexiconConfig(0.5, 2, len(train_by_element[element]), "train")
            for element in PICO_ELEMENTS
        },
        "project_pico_lexicon_v2": v2_configs,
        "project_pico_context_v3": v2_configs,
    }
    for element in PICO_ELEMENTS:
        test_examples = test_by_element[element]
        started = time.perf_counter()
        zero = [[0] * len(tokens) for _, tokens, _ in test_examples]
        methods["zero_prediction"][element] = _evaluate_labels(zero, test_examples, (time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        methods["token_lexicon_v1"][element] = _evaluate_labels(
            _predict_lexicon(test_examples, v1_lexicons[element]), test_examples, (time.perf_counter() - started) * 1000
        )
        started = time.perf_counter()
        methods["project_pico_lexicon_v2"][element] = _evaluate_labels(
            _predict_lexicon(
                test_examples,
                v2_lexicons[element],
                threshold=v2_configs[element].threshold,
            ),
            test_examples,
            (time.perf_counter() - started) * 1000,
        )
        started = time.perf_counter()
        methods["project_pico_context_v3"][element] = _evaluate_labels(
            _predict_context_lexicon(
                test_examples,
                v2_lexicons[element],
                context_lexicons[element],
                token_weight=0.5,
                threshold=v2_configs[element].threshold,
            ),
            test_examples,
            (time.perf_counter() - started) * 1000,
        )
    return methods, configs


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def _macro_metrics(metrics: dict[str, PicoMetrics]) -> PicoMetrics:
    values = list(metrics.values())
    return PicoMetrics(
        precision=sum(item.precision for item in values) / len(values),
        recall=sum(item.recall for item in values) / len(values),
        f1=sum(item.f1 for item in values) / len(values),
        true_positive=sum(item.true_positive for item in values),
        false_positive=sum(item.false_positive for item in values),
        false_negative=sum(item.false_negative for item in values),
        token_count=sum(item.token_count for item in values),
        positive_count=sum(item.positive_count for item in values),
        predicted_positive_count=sum(item.predicted_positive_count for item in values),
        document_count=sum(item.document_count for item in values),
        mean_latency_ms=sum(item.mean_latency_ms for item in values) / len(values),
    )


def write_problem_run(
    *,
    project_root: Path,
    manifest: dict[str, str],
    results: dict[str, dict[str, PicoMetrics]],
    configs: dict[str, dict[str, PicoLexiconConfig]],
    output_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_ebm_nlp_2_00"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "public-problem-understanding-v1",
        "layer": "external_benchmarks",
        "stage": "problem_understanding",
        "dataset": manifest,
        "split": "professional_test_gold",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method_configs": {
            method: {element: asdict(config) for element, config in by_element.items()}
            for method, by_element in configs.items()
        },
        "results": {
            method: {element: asdict(metrics) for element, metrics in by_element.items()}
            | {"macro": asdict(_macro_metrics(by_element))}
            for method, by_element in results.items()
        },
        "scope_notice": "PICO token-span diagnostic only; not a clinical or breast-cancer Gold Set score.",
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "evaluation_id", "evaluation_version", "layer", "stage", "benchmark_or_task", "stratum_name",
        "stratum_value", "method_id", "method_label", "base_model_id", "metric", "value", "direction",
        "unit", "n", "mean", "std", "ci95_low", "ci95_high", "run_count", "seed", "dataset_version",
        "evaluation_contract_id", "quality_gate", "publish_allowed", "source_id", "source_url", "raw_field",
        "raw_value", "notes",
    ]
    labels = {
        "zero_prediction": "Zero prediction baseline",
        "token_lexicon_v1": "Train token lexicon v1",
        "project_pico_lexicon_v2": "Project PICO lexicon v2",
        "project_pico_context_v3": "Project PICO context v3",
    }
    with (run_dir / "unified_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, by_element in results.items():
            for element, metrics in {**by_element, "macro": _macro_metrics(by_element)}.items():
                for metric_name in ("precision", "recall", "f1", "mean_latency_ms"):
                    value = getattr(metrics, metric_name)
                    writer.writerow({
                        "evaluation_id": run_dir.name,
                        "evaluation_version": "public-problem-understanding-v1",
                        "layer": "external_benchmarks",
                        "stage": "problem_understanding",
                        "benchmark_or_task": "ebm_nlp_2_00",
                        "stratum_name": "pico_element",
                        "stratum_value": element,
                        "method_id": method,
                        "method_label": labels[method],
                        "metric": f"span_{metric_name}" if metric_name != "mean_latency_ms" else metric_name,
                        "value": f"{value:.8f}",
                        "direction": "lower" if metric_name == "mean_latency_ms" else "higher",
                        "unit": "ms_per_token" if metric_name == "mean_latency_ms" else "ratio",
                        "n": metrics.document_count,
                        "run_count": 1,
                        "seed": "deterministic",
                        "dataset_version": manifest.get("test_gold_participants_sha256", "")[:12],
                        "quality_gate": "REVIEW",
                        "publish_allowed": "false",
                        "source_id": manifest["source_id"],
                        "source_url": manifest["source_url"],
                        "raw_field": metric_name,
                        "raw_value": f"{value:.12f}",
                        "notes": "Train crowd-aggregated labels fit lexicon; professional test gold used once for scoring.",
                    })
    lines = [
        "# EBM-NLP problem-understanding benchmark",
        "",
        "> Token-span PICO diagnostic only; not a clinical or breast-cancer Gold Set result.",
        "",
        "| Method | P span F1 | I span F1 | O span F1 | Macro F1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for method, by_element in results.items():
        lines.append(
            f"| {labels[method]} | {by_element['participants'].f1:.4f} | {by_element['interventions'].f1:.4f} | "
            f"{by_element['outcomes'].f1:.4f} | {_macro_metrics(by_element).f1:.4f} |"
        )
    lines.extend([
        "",
        f"Source: {manifest['source_url']}",
        f"Archive SHA-256: `{manifest['archive_sha256']}`",
        f"Code revision: `{payload['code_revision']}`",
        "",
    ])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_public_problem_benchmark(*, project_root: Path, data_root: Path, output_root: Path, download: bool) -> Path:
    dataset_dir, manifest = prepare_ebm_nlp_dataset(data_root, download=download)
    results, configs = evaluate_pico_dataset(dataset_dir)
    return write_problem_run(
        project_root=project_root,
        manifest=manifest,
        results=results,
        configs=configs,
        output_root=output_root,
    )
