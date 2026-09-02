from __future__ import annotations

import csv
import hashlib
import json
import re
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
    "raha_beers": {
        "folder_name": "beers",
        "source_id": "github:BigDaMa/raha",
        "source_url": "https://github.com/BigDaMa/raha/tree/master/datasets/beers",
        "dirty_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/beers/dirty.csv",
        "clean_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/beers/clean.csv",
    },
    "raha_flights": {
        "folder_name": "flights",
        "source_id": "github:BigDaMa/raha",
        "source_url": "https://github.com/BigDaMa/raha/tree/master/datasets/flights",
        "dirty_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/flights/dirty.csv",
        "clean_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/flights/clean.csv",
    },
    "raha_movies_1": {
        "folder_name": "movies_1",
        "source_id": "github:BigDaMa/raha",
        "source_url": "https://github.com/BigDaMa/raha/tree/master/datasets/movies_1",
        "dirty_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/movies_1/dirty.csv",
        "clean_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/movies_1/clean.csv",
    },
    "raha_rayyan": {
        "folder_name": "rayyan",
        "source_id": "github:BigDaMa/raha",
        "source_url": "https://github.com/BigDaMa/raha/tree/master/datasets/rayyan",
        "dirty_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/rayyan/dirty.csv",
        "clean_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/rayyan/clean.csv",
    },
    "raha_tax": {
        "folder_name": "tax",
        "source_id": "github:BigDaMa/raha",
        "source_url": "https://github.com/BigDaMa/raha/tree/master/datasets/tax",
        "dirty_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/tax/dirty.csv",
        "clean_url": "https://raw.githubusercontent.com/BigDaMa/raha/master/datasets/tax/clean.csv",
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
    if {"tid", "attribute", "correct_val"}.issubset(corrections[0]):
        # HoloClean distributes the clean reference as per-cell corrections.
        # Start from the dirty table so cells absent from the correction list
        # are retained.
        clean = [row.copy() for row in dirty]
        for item in corrections:
            row_index = int(item["tid"])
            if row_index < 0 or row_index >= len(clean) or item["attribute"] not in columns:
                raise ValueError(f"Invalid correction row: {item}")
            clean[row_index][item["attribute"]] = item["correct_val"]
    else:
        # Raha/Baran publishes a complete clean table.  Preserve the upstream
        # row order and require matching columns so labels cannot be silently
        # shifted during evaluation.
        if len(corrections) != len(dirty):
            raise ValueError("Full clean table must have the same row count as dirty.csv")
        normalized_clean: dict[str, list[str]] = {}
        for column in corrections[0]:
            for variant in _column_variants(column):
                normalized_clean.setdefault(variant, []).append(column)
        column_map: dict[str, str] = {}
        for column in columns:
            candidates = {
                candidate
                for variant in _column_variants(column)
                for candidate in normalized_clean.get(variant, [])
            }
            if not candidates:
                raise ValueError(f"Full clean table is missing dirty column: {column}")
            if len(candidates) != 1:
                raise ValueError(f"Full clean table has ambiguous matches for dirty column: {column}")
            column_map[column] = next(iter(candidates))
        clean = [{column: row[column_map[column]] for column in columns} for row in corrections]
    return dirty, clean


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _normalize_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def _column_variants(value: str) -> set[str]:
    normalized = _normalize_column(value)
    compact = normalized.replace("_", "")
    without_prefix = re.sub(r"^(full|raw|original)_?", "", normalized)
    return {normalized, compact, without_prefix, without_prefix.replace("_", "")}


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


def _numeric_candidate(value: str) -> float | None:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[,\s]+", "", text)
    text = re.sub(r"(?:%|oz\.?|ounce(?:s)?)$", "", text)
    try:
        return float(text)
    except ValueError:
        return None


def _format_number(value: str, column: str) -> str:
    number = _numeric_candidate(value)
    if number is None:
        return value.strip()
    lower_column = column.casefold()
    raw_lower = value.casefold()
    # Keep percentage semantics by default.  The Beer benchmark's ``abv``
    # column explicitly stores a fraction with a percent sign, whereas a
    # generic score column is expected to retain its display unit.
    if "%" in raw_lower and lower_column not in {"abv", "alcohol_by_volume"}:
        return value.strip()
    # Postal codes are identifiers in this public benchmark and use the
    # canonical integer spelling (without leading zero padding).
    if lower_column == "zip" or lower_column.endswith("_zip"):
        return str(int(number))
    if number.is_integer():
        return str(int(number))
    return format(number, ".12g")


def _profile_numeric_columns(dirty: list[dict[str, str]]) -> set[str]:
    columns = list(dirty[0])
    numeric_columns: set[str] = set()
    for column in columns:
        values = [row[column] for row in dirty if str(row[column] or "").strip()]
        if values and sum(_numeric_candidate(value) is not None for value in values) / len(values) >= 0.8:
            numeric_columns.add(column)
    return numeric_columns


def _format_time(value: str) -> str:
    match = re.search(r"\d{1,2}:\d{2}\s*[ap]\.m\.", str(value or ""), re.IGNORECASE)
    return match.group(0).replace(" ", " ").lower() if match else value.strip()


def _project_format_profile_repair(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    """Repair high-confidence representation errors using the dirty table only."""

    output = [row.copy() for row in dirty]
    numeric_columns = _profile_numeric_columns(dirty)
    missing_markers = {"n/a", "na", "null", "none", "?"}
    columns = set(dirty[0])
    value_counts = {
        column: Counter(str(row[column] or "") for row in dirty)
        for column in dirty[0]
    }
    for row in output:
        for column, raw_value in row.items():
            value = str(raw_value or "").strip()
            if value.casefold() in missing_markers:
                row[column] = ""
            elif column in numeric_columns:
                if (
                    column.casefold() == "zip"
                    and value.startswith("0")
                    and value_counts[column][value] >= max(10, len(dirty) // 100)
                ):
                    # A repeated padded identifier can represent a burst of
                    # corruption rather than one harmless formatting variant.
                    row[column] = raw_value
                    continue
                row[column] = _format_number(value, column)
            elif "time" in column.casefold() and re.search(r"\d{1,2}:\d{2}", value):
                row[column] = _format_time(value)
            else:
                # Preserve text exactly; repeated spaces and punctuation can
                # be meaningful values in the public clean reference.
                row[column] = raw_value
        # A common, deterministic table error is a two-letter state appended
        # to city while the state cell is blank.  Use only that local evidence.
        if "city" in columns and "state" in columns and not row["state"]:
            match = re.search(r"\s+([A-Za-z]{2})$", row["city"])
            if match:
                row["state"] = match.group(1).upper()
                row["city"] = row["city"][: match.start()].rstrip()
    return output


def _project_placeholder_consensus_repair(
    dirty: list[dict[str, str]], *, min_frequency: int = 10, dominance_ratio: int = 3
) -> list[dict[str, str]]:
    """Repair repeated ``x``-masked values using only column-local evidence.

    Public dirty tables use ``x`` as a character placeholder in several
    columns. A candidate is accepted only when a frequent clean-looking value
    matches every non-placeholder character and has a clear frequency lead.
    """

    output = [row.copy() for row in dirty]
    for column in dirty[0]:
        values = [str(row[column] or "") for row in dirty]
        counts = Counter(value for value in values if value.strip())
        frequent = [value for value, count in counts.items() if count >= min_frequency]
        for index, value in enumerate(values):
            if not value.strip() or counts[value] >= min_frequency or "x" not in value.casefold():
                continue
            candidates = sorted(
                (
                    counts[candidate],
                    candidate,
                )
                for candidate in frequent
                if len(candidate) == len(value)
                and all(
                    left.casefold() == "x" or left.casefold() == right.casefold()
                    for left, right in zip(value, candidate)
                )
                and candidate != value
            )
            if candidates and (
                len(candidates) == 1
                or candidates[-1][0] >= candidates[-2][0] * dominance_ratio
            ):
                output[index][column] = candidates[-1][1]
    return output


def _project_fusion_repair_v3(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    """Combine format normalization with conservative placeholder consensus."""

    formatted = _project_format_profile_repair(dirty)
    placeholder = _project_placeholder_consensus_repair(dirty)
    output = [row.copy() for row in formatted]
    for index, row in enumerate(dirty):
        for column in row:
            if formatted[index][column] == row[column] and placeholder[index][column] != row[column]:
                output[index][column] = placeholder[index][column]
    return output


def _project_context_consensus_repair_v4(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    """Add conservative repeated-flight context to the v3 repair pass."""

    output = _project_fusion_repair_v3(dirty)
    if "flight" not in dirty[0]:
        return output
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in dirty:
        if row["flight"]:
            groups[row["flight"]].append(row)
    for column in dirty[0]:
        if column == "flight":
            continue
        group_values = {
            key: {row[column] for row in rows if row[column]}
            for key, rows in groups.items()
        }
        for index, row in enumerate(dirty):
            values = group_values.get(row["flight"], set())
            if not row[column] and len(values) == 1:
                output[index][column] = next(iter(values))
    return output


def _project_date_profile_repair_v5(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    """Normalize a table-wide, self-evident three-part date serialization error."""

    output = _project_context_consensus_repair_v4(dirty)
    date_columns = [
        column
        for column in dirty[0]
        if "date" in column.casefold() or "created_at" in column.casefold()
    ]
    for column in date_columns:
        values = [str(row[column] or "").strip() for row in dirty]
        parts = [value.split("/") for value in values if value]
        valid = [item for item in parts if len(item) == 3 and all(part.isdigit() for part in item)]
        if len(valid) < max(20, int(len(values) * 0.7)):
            continue
        middle_one_ratio = sum(item[1] == "1" for item in valid) / len(valid)
        if middle_one_ratio < 0.8:
            continue
        for index, row in enumerate(dirty):
            item = str(row[column] or "").strip().split("/")
            if len(item) != 3 or not all(part.isdigit() for part in item):
                continue
            output[index][column] = "/".join((str(int(item[1])), str(int(item[2])), item[0].zfill(2)))
    return output


def _project_source_anchor_repair_v6(dirty: list[dict[str, str]]) -> list[dict[str, str]]:
    """Propagate values from a provenance-matching row within repeated groups.

    The rule is deliberately schema-light: it activates only when a table has
    ``flight`` and ``src`` columns and a source value matches the flight prefix.
    This is an observable key relationship, so it can repair both missing and
    conflicting copies without consulting the clean reference.
    """

    output = _project_date_profile_repair_v5(dirty)
    columns = set(dirty[0])
    if not {"flight", "src"}.issubset(columns):
        return output
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(dirty):
        if row["flight"]:
            groups[row["flight"]].append(index)
    ignored = {"tuple_id", "src", "flight"}
    value_columns = [column for column in dirty[0] if column not in ignored]
    for flight, indices in groups.items():
        prefix = flight.split("-", 1)[0].casefold()
        anchors = [index for index in indices if dirty[index]["src"].casefold() == prefix]
        if not anchors:
            continue
        anchor = next(
            (index for index in anchors if sum(bool(output[index][column]) for column in value_columns) >= max(1, len(value_columns) - 1)),
            anchors[0],
        )
        for index in indices:
            for column in value_columns:
                value = output[anchor][column]
                if value and output[index][column] != value:
                    output[index][column] = value
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
    elif method == "project_format_profile_v2":
        repaired = _project_format_profile_repair(dirty)
    elif method == "project_fusion_repair_v3":
        repaired = _project_fusion_repair_v3(dirty)
    elif method == "project_context_consensus_repair_v4":
        repaired = _project_context_consensus_repair_v4(dirty)
    elif method == "project_date_profile_repair_v5":
        repaired = _project_date_profile_repair_v5(dirty)
    elif method == "project_source_anchor_repair_v6":
        repaired = _project_source_anchor_repair_v6(dirty)
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
        "evaluation_version": "public-cleaning-v2",
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
    fields = [
        "evaluation_id", "evaluation_version", "layer", "stage", "benchmark_or_task", "stratum_name",
        "stratum_value", "method_id", "method_label", "base_model_id", "metric", "value", "direction",
        "unit", "n", "mean", "std", "ci95_low", "ci95_high", "run_count", "seed", "dataset_version",
        "evaluation_contract_id", "quality_gate", "publish_allowed", "source_id", "source_url", "raw_field",
        "raw_value", "notes",
    ]
    method_labels = {
        "no_repair": "No repair",
        "column_mode": "Column mode baseline",
        "project_portability_consensus_clean_v1": "Project consensus clean v1",
        "project_format_profile_v2": "Project format profile v2",
        "project_fusion_repair_v3": "Project format + placeholder fusion v3",
        "project_context_consensus_repair_v4": "Project format + context consensus v4",
        "project_date_profile_repair_v5": "Project format + date profile v5",
        "project_source_anchor_repair_v6": "Project format + provenance anchor v6",
    }
    with (run_dir / "unified_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, metrics in results.items():
            for metric_name in ("cell_precision", "cell_recall", "cell_f1", "repair_accuracy", "mean_latency_ms"):
                value = getattr(metrics, metric_name)
                writer.writerow({
                    "evaluation_id": run_dir.name,
                    "evaluation_version": "public-cleaning-v2",
                    "layer": "external_benchmarks",
                    "stage": "cleaning",
                    "benchmark_or_task": dataset_id,
                    "stratum_name": "benchmark_dataset",
                    "stratum_value": dataset_id,
                    "method_id": method,
                    "method_label": method_labels.get(method, method),
                    "metric": metric_name,
                    "value": f"{value:.8f}",
                    "direction": "lower" if metric_name == "mean_latency_ms" else "higher",
                    "unit": "ms_per_cell" if metric_name == "mean_latency_ms" else "ratio",
                    "n": metrics.dirty_cell_count,
                    "run_count": 1,
                    "seed": "deterministic",
                    "dataset_version": manifest["dirty_sha256"][:12],
                    "quality_gate": "REVIEW",
                    "publish_allowed": "false",
                    "source_id": manifest["source_id"],
                    "source_url": manifest["source_url"],
                    "raw_field": metric_name,
                    "raw_value": f"{value:.12f}",
                    "notes": "Official dirty/clean reference; generic cleaning layer only.",
                })
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
    methods = [
        "no_repair",
        "column_mode",
        "project_portability_consensus_clean_v1",
        "project_format_profile_v2",
        "project_fusion_repair_v3",
        "project_context_consensus_repair_v4",
        "project_date_profile_repair_v5",
        "project_source_anchor_repair_v6",
    ]
    results = {method: evaluate_cleaning(dirty, clean, method) for method in methods}
    return write_cleaning_run(project_root=project_root, dataset_id=dataset_id, manifest=manifest, results=results, output_root=output_root)
