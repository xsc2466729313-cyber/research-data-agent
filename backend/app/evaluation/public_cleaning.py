from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


CLEANING_DATASETS = {
    "holoclean_hospital": {
        "folder_name": "hospital",
        "source_id": "github:HoloClean/holoclean",
        "source_url": "https://github.com/HoloClean/holoclean/tree/master/testdata",
        "dirty_url": "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/hospital.csv",
        "clean_url": "https://raw.githubusercontent.com/HoloClean/holoclean/master/testdata/hospital_clean.csv",
    },
}


@dataclass(frozen=True)
class CleaningMetrics:
    cell_precision: float
    cell_recall: float
    cell_f1: float
    repair_accuracy: float
    true_positive: int
    false_positive: int
    false_negative: int
    correct_repairs: int
    automatic_repairs: int
    dirty_cell_count: int
    total_cell_count: int
    mean_latency_ms: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_cleaning_dataset(dataset_id: str, data_root: Path, *, download: bool) -> tuple[Path, dict[str, str]]:
    if dataset_id not in CLEANING_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset_id}")
    spec = CLEANING_DATASETS[dataset_id]
    dataset_dir = data_root / spec["folder_name"]
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dirty_path, clean_path = dataset_dir / "dirty.csv", dataset_dir / "clean.csv"
    if not dirty_path.exists() or not clean_path.exists():
        if not download:
            raise FileNotFoundError(f"{dataset_id} is missing. Re-run with --download.")
        for path, url in ((dirty_path, spec["dirty_url"]), (clean_path, spec["clean_url"])):
            partial = path.with_suffix(path.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
                output.write(response.read())
            partial.replace(path)
    return dataset_dir, {
        "dataset_id": dataset_id,
        "source_id": spec["source_id"],
        "source_url": spec["source_url"],
        "dirty_sha256": _sha256(dirty_path),
        "clean_sha256": _sha256(clean_path),
    }


def load_cleaning_dataset(dataset_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with (dataset_dir / "dirty.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        dirty = list(csv.DictReader(handle))
    with (dataset_dir / "clean.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        corrections = list(csv.DictReader(handle))
    if not dirty or not corrections:
        raise ValueError("Cleaning dataset is empty")
    columns = list(dirty[0])
    # HoloClean distributes the clean reference as per-cell corrections. Start
    # from the dirty table so cells absent from the correction list are retained.
    clean = [row.copy() for row in dirty]
    for item in corrections:
        row_index = int(item["tid"])
        if row_index < 0 or row_index >= len(clean) or item["attribute"] not in columns:
            raise ValueError(f"Invalid correction row: {item}")
        clean[row_index][item["attribute"]] = item["correct_val"]
    return dirty, clean


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _column_mode_repair(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    output = [row.copy() for row in dirty]
    for column in dirty[0]:
        counts = Counter(_normalize(row[column]) for row in dirty if _normalize(row[column]))
        if not counts:
            continue
        mode, mode_count = counts.most_common(1)[0]
        # This deliberately conservative baseline only repairs singleton categorical values.
        if mode_count < 3:
            continue
        for row in output:
            value = _normalize(row[column])
            if value and counts[value] == 1:
                row[column] = mode
    return output


def _project_consensus_repair(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    output = [row.copy() for row in dirty]
    columns = list(dirty[0])
    context_priority = ["ProviderNumber", "MeasureCode", "Condition", "State", "HospitalType", "HospitalOwner"]
    for column in columns:
        contexts = [context for context in context_priority if context in columns and context != column]
        if not contexts:
            continue
        indexes: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for index, row in enumerate(dirty):
            key = tuple(_normalize(row[context]) for context in contexts)
            if all(key):
                indexes[key].append(index)
        for index, row in enumerate(dirty):
            key = tuple(_normalize(row[context]) for context in contexts)
            candidates = indexes.get(key, [])
            if len(candidates) < 2:
                continue
            values = Counter(_normalize(dirty[candidate][column]) for candidate in candidates if _normalize(dirty[candidate][column]))
            if not values:
                continue
            mode, mode_count = values.most_common(1)[0]
            current = _normalize(row[column])
            if current and mode != current and mode_count >= 2 and values[current] == 1:
                output[index][column] = mode
    return output


def _metrics(dirty: list[dict[str, str]], clean: list[dict[str, str]], repaired: list[dict[str, str]], elapsed_ms: float) -> CleaningMetrics:
    columns = list(dirty[0])
    tp = fp = fn = correct_repairs = automatic_repairs = dirty_cells = 0
    total = len(dirty) * len(columns)
    for before, expected, after in zip(dirty, clean, repaired):
        for column in columns:
            is_error = before[column] != expected[column]
            changed = after[column] != before[column]
            if is_error:
                dirty_cells += 1
            if changed:
                automatic_repairs += 1
                if after[column] == expected[column]:
                    correct_repairs += 1
            if changed and is_error and after[column] == expected[column]:
                tp += 1
            elif changed and not is_error:
                fp += 1
            elif is_error and (not changed or after[column] != expected[column]):
                fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return CleaningMetrics(
        cell_precision=precision,
        cell_recall=recall,
        cell_f1=f1,
        repair_accuracy=correct_repairs / automatic_repairs if automatic_repairs else 0.0,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        correct_repairs=correct_repairs,
        automatic_repairs=automatic_repairs,
        dirty_cell_count=dirty_cells,
        total_cell_count=total,
        mean_latency_ms=elapsed_ms / max(1, total),
    )


def evaluate_cleaning(dirty: list[dict[str, str]], clean: list[dict[str, str]], method: str) -> CleaningMetrics:
    started = perf_counter()
    if method == "no_repair":
        repaired = [row.copy() for row in dirty]
    elif method == "column_mode":
        repaired = _column_mode_repair(dirty)
    elif method == "project_portability_consensus_clean_v1":
        repaired = _project_consensus_repair(dirty)
    else:
        raise ValueError(f"Unsupported method: {method}")
    return _metrics(dirty, clean, repaired, (perf_counter() - started) * 1000)


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def write_cleaning_run(*, project_root: Path, dataset_id: str, manifest: dict[str, str], results: dict[str, CleaningMetrics], output_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_{dataset_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "public-cleaning-v1",
        "layer": "external_benchmarks",
        "stage": "cleaning",
        "dataset": manifest,
        "split": "aligned_dirty_clean",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": {method: asdict(metrics) for method, metrics in results.items()},
        "scope_notice": "These are generic cell error detection/repair scores, not medical data quality or SDTI scores.",
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# {dataset_id} data cleaning benchmark",
        "",
        "> This is a generic dirty-cell detection/repair test. It is not a medical data quality or SDTI result.",
        "",
        "| Method | Cell precision | Cell recall | Cell F1 | Repair accuracy | TP | FP | FN | Repairs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, metrics in results.items():
        lines.append(f"| {method} | {metrics.cell_precision:.4f} | {metrics.cell_recall:.4f} | {metrics.cell_f1:.4f} | {metrics.repair_accuracy:.4f} | {metrics.true_positive} | {metrics.false_positive} | {metrics.false_negative} | {metrics.automatic_repairs} |")
    lines.extend(["", f"Source: {manifest['source_url']}", f"Dirty SHA-256: {manifest['dirty_sha256']}", f"Clean SHA-256: {manifest['clean_sha256']}", f"Code revision: {payload['code_revision']}", ""])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_public_cleaning_benchmark(*, project_root: Path, dataset_id: str, data_root: Path, output_root: Path, download: bool) -> Path:
    dataset_dir, manifest = prepare_cleaning_dataset(dataset_id, data_root, download=download)
    dirty, clean = load_cleaning_dataset(dataset_dir)
    methods = ["no_repair", "column_mode", "project_portability_consensus_clean_v1"]
    results = {method: evaluate_cleaning(dirty, clean, method) for method in methods}
    return write_cleaning_run(project_root=project_root, dataset_id=dataset_id, manifest=manifest, results=results, output_root=output_root)
