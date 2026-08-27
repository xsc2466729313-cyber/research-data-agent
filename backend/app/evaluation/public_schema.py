"""Reproducible schema-matching evaluation on the public Valentine tasks.

The benchmark is deliberately kept separate from the clinical canonical schema:
it measures whether two generic tables expose columns with the same meaning.
Only the held-out public ``ground_truth.json`` mappings are used for scoring;
the matching methods never inspect those labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


VALENTINE_COMMIT = "5d5163f04da304985bd51a476ccf7653de3979c3"
VALENTINE_REPOSITORY_URL = "https://github.com/delftdata/valentine"
VALENTINE_DATA_ROOT_URL = (
    f"https://raw.githubusercontent.com/delftdata/valentine/{VALENTINE_COMMIT}/experiments/data"
)

# The registry keeps the complete set of official tasks present at the pinned
# Valentine commit.  Each task is scored independently so easy and difficult
# table pairs cannot be hidden by one aggregate number.
SCHEMA_DATASETS: dict[str, dict[str, object]] = {
    "valentine_education_covid_meals": {
        "folder_name": "Education__COVID-19_Free_Meals_Locations",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "Education__COVID-19_Free_Meals_Locations"
        ),
    },
    "valentine_capital_projects": {
        "folder_name": "City_Government__Capital_Projects",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "City_Government__Capital_Projects"
        ),
    },
    "valentine_dcm_street_centerline": {
        "folder_name": "City_Government__DCM_StreetCenterLine",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "City_Government__DCM_StreetCenterLine"
        ),
    },
    "valentine_dpr_athletic_facilities": {
        "folder_name": "City_Government__DPR_AthleticFacilities_001",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "City_Government__DPR_AthleticFacilities_001"
        ),
    },
    "valentine_dsny_disposal_assignments": {
        "folder_name": "City_Government__DSNY_Districts_With_Disposal_Vendor_Assignments",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "City_Government__DSNY_Districts_With_Disposal_Vendor_Assignments"
        ),
    },
    "valentine_energy_benchmarking": {
        "folder_name": "City_Government__NYC_Municipal_Building_Energy_Benchmarking_Results",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "City_Government__NYC_Municipal_Building_Energy_Benchmarking_Results"
        ),
    },
    "valentine_swim_for_life": {
        "folder_name": "Recreation__Swim_for_Life__2016_to_2020",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "Recreation__Swim_for_Life__2016_to_2020"
        ),
    },
    "valentine_street_resurfacing": {
        "folder_name": "Transportation__DOT_In-house_Street_Resurfacing_Projects",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "Transportation__DOT_In-house_Street_Resurfacing_Projects"
        ),
    },
    "valentine_housing_maintenance": {
        "folder_name": "Housing_&_Development__Housing_Maintenance_Code_Complaints_and_Problems",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "Housing_&_Development__Housing_Maintenance_Code_Complaints_and_Problems"
        ),
    },
    "valentine_public_art_inventory": {
        "folder_name": "Housing_&_Development__Public_Design_Commission_Outdoor_Public_Art_Invent",
        "source_id": "github:delftdata/valentine",
        "source_url": (
            f"{VALENTINE_REPOSITORY_URL}/tree/{VALENTINE_COMMIT}/experiments/data/"
            "Housing_&_Development__Public_Design_Commission_Outdoor_Public_Art_Invent"
        ),
    },
}


@dataclass(frozen=True)
class SchemaMetrics:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    predicted_count: int
    gold_count: int
    source_column_count: int
    target_column_count: int
    runtime_ms: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
        partial.replace(destination)
    finally:
        if partial.exists():
            partial.unlink()


def prepare_schema_dataset(
    dataset_id: str,
    data_root: Path,
    *,
    download: bool,
) -> tuple[Path, dict[str, str]]:
    """Ensure one pinned Valentine task is available and return its manifest."""

    if dataset_id not in SCHEMA_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset_id}")
    spec = SCHEMA_DATASETS[dataset_id]
    folder_name = str(spec["folder_name"])
    dataset_dir = data_root / folder_name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    files = {name: dataset_dir / name for name in ("source_table.csv", "target_table.csv", "ground_truth.json")}
    base_url = f"{VALENTINE_DATA_ROOT_URL}/{quote(folder_name, safe='_-.')}"
    if any(not path.exists() for path in files.values()):
        if not download:
            raise FileNotFoundError(
                f"{dataset_id} is missing. Re-run with --download to fetch the pinned Valentine task."
            )
        for name, path in files.items():
            if not path.exists():
                _download(f"{base_url}/{name}", path)
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Valentine task is incomplete: {missing}")
    return dataset_dir, {
        "dataset_id": dataset_id,
        "source_id": str(spec["source_id"]),
        "source_url": str(spec["source_url"]),
        "source_commit": VALENTINE_COMMIT,
        "source_file_url": f"{base_url}/source_table.csv",
        "target_file_url": f"{base_url}/target_table.csv",
        "ground_truth_url": f"{base_url}/ground_truth.json",
        "source_table_sha256": _sha256(files["source_table.csv"]),
        "target_table_sha256": _sha256(files["target_table.csv"]),
        "ground_truth_sha256": _sha256(files["ground_truth.json"]),
    }


def _read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        row = next(csv.reader(handle), None)
    if not row:
        raise ValueError(f"CSV has no header: {path}")
    if len(set(row)) != len(row):
        raise ValueError(f"CSV header contains duplicate columns: {path}")
    return [str(value) for value in row]


def _read_samples(path: Path, *, limit: int = 32) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        for row_index, row in enumerate(reader):
            for column, value in row.items():
                if column is not None and value not in (None, "") and len(samples.setdefault(column, [])) < limit:
                    samples[column].append(str(value))
            # The first rows are sufficient for type/value compatibility and
            # avoid scanning a large public table into memory.
            if row_index + 1 >= limit:
                break
    return samples


def load_schema_task(dataset_dir: Path) -> tuple[list[str], list[str], set[tuple[str, str]], dict[str, list[str]], dict[str, list[str]]]:
    """Load headers, test gold pairs, and bounded value samples."""

    source_columns = _read_header(dataset_dir / "source_table.csv")
    target_columns = _read_header(dataset_dir / "target_table.csv")
    with (dataset_dir / "ground_truth.json").open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("Valentine ground_truth.json does not contain a matches list")
    gold: set[tuple[str, str]] = set()
    for match in matches:
        if not isinstance(match, Mapping):
            raise ValueError(f"Invalid schema match: {match!r}")
        source, target = str(match.get("source_column", "")), str(match.get("target_column", ""))
        if source not in source_columns or target not in target_columns:
            raise ValueError(f"Gold pair references a missing column: {(source, target)!r}")
        gold.add((source, target))
    return (
        source_columns,
        target_columns,
        gold,
        _read_samples(dataset_dir / "source_table.csv"),
        _read_samples(dataset_dir / "target_table.csv"),
    )


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def _tokens(value: str) -> set[str]:
    return set(_normalize(value).split())


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


_TOKEN_ALIASES: dict[str, set[str]] = {
    "id": {"id", "code", "number", "num", "key", "identifier"},
    "code": {"id", "code", "number", "num", "key", "identifier"},
    "number": {"id", "code", "number", "num", "key", "identifier"},
    "name": {"name", "title", "label", "description"},
    "title": {"name", "title", "label", "description"},
    "date": {"date", "time", "day", "year"},
    "time": {"date", "time", "day", "year"},
    "status": {"status", "state", "flag", "condition"},
    "state": {"status", "state", "flag", "condition"},
    "type": {"type", "category", "class", "kind"},
    "category": {"type", "category", "class", "kind"},
    "location": {"location", "address", "street", "site", "place", "borough", "city"},
    "address": {"location", "address", "street", "site", "place", "borough", "city"},
    "city": {"location", "address", "street", "site", "place", "borough", "city", "urban", "zone", "town", "district"},
    "urban": {"urban", "zone", "city", "town", "borough", "district"},
    "zone": {"urban", "zone", "city", "town", "borough", "district"},
    "lat": {"lat", "latitude"},
    "latitude": {"lat", "latitude"},
    "lon": {"lon", "long", "longitude"},
    "longitude": {"lon", "long", "longitude"},
}


_COMPOUND_PARTS = (
    "latitude", "longitude", "address", "street", "borough", "district", "number",
    "school", "city", "site", "state", "status", "system", "code", "name", "title",
    "date", "year", "month", "class", "type", "category", "problem", "building", "block",
    "lot", "id", "key", "urban", "zone", "sf", "fac",
)


def _semantic_tokens(value: str) -> set[str]:
    """Return tokens plus obvious compound-name parts (``siteaddress`` -> site/address)."""

    tokens = _tokens(value)
    expanded = set(tokens)
    for token in tokens:
        for part in _COMPOUND_PARTS:
            if len(part) >= 2 and part != token and part in token:
                expanded.add(part)
    return expanded


def _alias_similarity(left: str, right: str) -> float:
    a, b = _semantic_tokens(left), _semantic_tokens(right)
    if not a or not b:
        return 0.0
    expanded_a = set(a)
    expanded_b = set(b)
    for token in a:
        expanded_a.update(_TOKEN_ALIASES.get(token, {token}))
    for token in b:
        expanded_b.update(_TOKEN_ALIASES.get(token, {token}))
    overlap = expanded_a & expanded_b
    if not overlap:
        return 0.0
    # Normalise by the smaller semantic vocabulary.  This treats a compound
    # name such as ``siteaddress`` as a full match for ``location`` when the
    # source value shape also supports an address interpretation.
    return len(overlap) / min(len(expanded_a), len(expanded_b))


def _value_kind(values: Sequence[str]) -> str:
    if not values:
        return "empty"
    numeric = 0
    for value in values:
        try:
            float(str(value).strip())
            numeric += 1
        except (TypeError, ValueError):
            pass
    if numeric >= max(1, int(0.8 * len(values))):
        return "numeric"
    # Address-like values contain both digits and letters (e.g. ``108
    # MONTROSE AVENUE``), while city/name values are usually short alphabetic
    # strings.  This check supplies useful evidence for ambiguous columns such
    # as ``location`` without referring to benchmark labels.
    with_digits = sum(any(character.isdigit() for character in value) for value in values)
    if with_digits >= max(1, int(0.5 * len(values))) and any(any(character.isalpha() for character in value) for value in values):
        return "address"
    if all(len(str(value).split()) <= 3 for value in values):
        return "short_text"
    return "text"


def _value_compatibility(left: Sequence[str], right: Sequence[str]) -> float:
    left_kind, right_kind = _value_kind(left), _value_kind(right)
    if "empty" in (left_kind, right_kind):
        return 0.0
    if left_kind == right_kind:
        return 1.0
    if {left_kind, right_kind} == {"address", "short_text"}:
        return 0.0
    if {left_kind, right_kind} == {"address", "numeric"}:
        return 0.0
    # Identifier columns sometimes mix numeric and string encodings; do not
    # penalise these as strongly as an address/text to coordinate mismatch.
    return 0.25


def _value_overlap_profile(left: Sequence[str], right: Sequence[str]) -> float:
    """Weak value-set evidence for copied identifiers/categories."""
    left_values = {_normalize(value) for value in left if _normalize(value)}
    right_values = {_normalize(value) for value in right if _normalize(value)}
    if not left_values or not right_values:
        return 0.0
    overlap = len(left_values & right_values) / min(len(left_values), len(right_values))
    return overlap * min(1.0, min(len(left_values), len(right_values)) / 4.0)


def _schema_score(
    source: str,
    target: str,
    source_samples: Mapping[str, Sequence[str]],
    target_samples: Mapping[str, Sequence[str]],
) -> float:
    lexical = _jaccard(source, target)
    alias = _alias_similarity(source, target)
    compatibility = _value_compatibility(source_samples.get(source, ()), target_samples.get(target, ()))
    return 0.50 * lexical + 0.35 * alias + 0.15 * compatibility


def _schema_profile_score(
    source: str,
    target: str,
    source_samples: Mapping[str, Sequence[str]],
    target_samples: Mapping[str, Sequence[str]],
) -> float:
    lexical = _jaccard(source, target)
    alias = _alias_similarity(source, target)
    compatibility = _value_compatibility(source_samples.get(source, ()), target_samples.get(target, ()))
    overlap = _value_overlap_profile(source_samples.get(source, ()), target_samples.get(target, ()))
    return 0.25 * lexical + 0.15 * alias + 0.10 * compatibility + 0.50 * overlap


def predict_schema_matches(
    source_columns: Sequence[str],
    target_columns: Sequence[str],
    method: str,
    *,
    source_samples: Mapping[str, Sequence[str]] | None = None,
    target_samples: Mapping[str, Sequence[str]] | None = None,
) -> set[tuple[str, str]]:
    """Predict one-to-one column pairs without looking at gold labels."""

    source_samples = source_samples or {}
    target_samples = target_samples or {}
    if method == "exact_normalized_name":
        return {
            (source, target)
            for source in source_columns
            for target in target_columns
            if _normalize(source) == _normalize(target) and _normalize(source)
        }
    if method == "token_jaccard":
        threshold = 0.5
        score_fn = lambda source, target: _jaccard(source, target)
    elif method == "project_schema_rule_v1":
        threshold = 0.40
        score_fn = lambda source, target: _schema_score(source, target, source_samples, target_samples)
    elif method == "project_schema_profile_v2":
        threshold = 0.40
        score_fn = lambda source, target: _schema_profile_score(source, target, source_samples, target_samples)
    else:
        raise ValueError(f"Unsupported method: {method}")

    candidates: list[tuple[float, str, str]] = []
    for source in source_columns:
        ranked = sorted(
            ((score_fn(source, target), target) for target in target_columns),
            key=lambda item: (-item[0], item[1]),
        )
        if not ranked or ranked[0][0] < threshold:
            continue
        # A weak tie between generic names is not a trustworthy alignment.
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 1e-12 and ranked[0][0] < 0.8:
            continue
        candidates.append((ranked[0][0], source, ranked[0][1]))
    # Resolve collisions globally by retaining the strongest candidate for each
    # target, making the output a conventional one-to-one schema alignment.
    predictions: set[tuple[str, str]] = set()
    used_targets: set[str] = set()
    for _, source, target in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
        if target not in used_targets:
            predictions.add((source, target))
            used_targets.add(target)
    return predictions


def evaluate_schema_matches(
    source_columns: Sequence[str],
    target_columns: Sequence[str],
    gold: set[tuple[str, str]],
    method: str,
    *,
    source_samples: Mapping[str, Sequence[str]] | None = None,
    target_samples: Mapping[str, Sequence[str]] | None = None,
) -> SchemaMetrics:
    started = time.perf_counter()
    predicted = predict_schema_matches(
        source_columns,
        target_columns,
        method,
        source_samples=source_samples,
        target_samples=target_samples,
    )
    runtime_ms = (time.perf_counter() - started) * 1000
    true_positive = len(predicted & gold)
    false_positive = len(predicted - gold)
    false_negative = len(gold - predicted)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return SchemaMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        predicted_count=len(predicted),
        gold_count=len(gold),
        source_column_count=len(source_columns),
        target_column_count=len(target_columns),
        runtime_ms=runtime_ms,
    )


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def write_schema_run(
    *,
    project_root: Path,
    dataset_id: str,
    manifest: dict[str, str],
    results: dict[str, SchemaMetrics],
    output_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_{dataset_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "public-schema-v1",
        "layer": "external_benchmarks",
        "stage": "schema_integration",
        "dataset": manifest,
        "split": "official_ground_truth_matches",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "methods": list(results),
        "results": {method: asdict(metrics) for method, metrics in results.items()},
        "scope_notice": (
            "Generic schema matching scores on Valentine public tables; not a clinical "
            "canonical-schema, patient identity, or SDTI score."
        ),
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the same column contract as data/evaluation_templates/
    # unified_results_template.csv so this layer can be merged with the other
    # public benchmark outputs without a bespoke adapter.
    fields = [
        "evaluation_id", "evaluation_version", "layer", "stage", "benchmark_or_task",
        "stratum_name", "stratum_value", "method_id", "method_label", "base_model_id",
        "metric", "value", "direction", "unit", "n", "mean", "std", "ci95_low",
        "ci95_high", "run_count", "seed", "dataset_version", "evaluation_contract_id",
        "quality_gate", "publish_allowed", "source_id", "source_url", "raw_field",
        "raw_value", "notes",
    ]
    method_labels = {
        "exact_normalized_name": "Exact normalized name",
        "token_jaccard": "Token Jaccard",
        "project_schema_rule_v1": "Project schema rule v1",
        "project_schema_profile_v2": "Project schema value-profile v2",
    }
    with (run_dir / "unified_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, metrics in results.items():
            for metric_name in ("precision", "recall", "f1", "runtime_ms"):
                value = getattr(metrics, metric_name)
                writer.writerow({
                    "evaluation_id": run_dir.name,
                    "evaluation_version": "public-schema-v1",
                    "layer": "external_benchmarks",
                    "stage": "schema_integration",
                    "benchmark_or_task": dataset_id,
                    "stratum_name": "benchmark_dataset",
                    "stratum_value": dataset_id,
                    "method_id": method,
                    "method_label": method_labels.get(method, method),
                    "base_model_id": "",
                    "metric": f"schema_{metric_name}" if metric_name != "runtime_ms" else metric_name,
                    "value": f"{value:.8f}",
                    "direction": "lower" if metric_name == "runtime_ms" else "higher",
                    "unit": "ms" if metric_name == "runtime_ms" else "ratio",
                    "n": metrics.gold_count,
                    "mean": "",
                    "std": "",
                    "ci95_low": "",
                    "ci95_high": "",
                    "run_count": 1,
                    "seed": "deterministic",
                    "dataset_version": manifest["ground_truth_sha256"][:12],
                    "evaluation_contract_id": "",
                    "quality_gate": "REVIEW",
                    "publish_allowed": "false",
                    "source_id": manifest["source_id"],
                    "source_url": manifest["source_url"],
                    "raw_field": metric_name,
                    "raw_value": f"{value:.12f}",
                    "notes": "Official Valentine ground_truth.json mappings; schema layer only.",
                })
    lines = [
        f"# {dataset_id} schema matching benchmark",
        "",
        "> Generic field-alignment test only; this is not a clinical schema or SDTI result.",
        "",
        "| Method | Precision | Recall | F1 | TP | FP | FN | Runtime |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, metrics in results.items():
        lines.append(
            f"| {method} | {metrics.precision:.4f} | {metrics.recall:.4f} | {metrics.f1:.4f} | "
            f"{metrics.true_positive} | {metrics.false_positive} | {metrics.false_negative} | "
            f"{metrics.runtime_ms:.3f} ms |"
        )
    lines.extend([
        "",
        f"Source: {manifest['source_url']}",
        f"Pinned Valentine commit: `{manifest['source_commit']}`",
        f"Source SHA-256: `{manifest['source_table_sha256']}`",
        f"Target SHA-256: `{manifest['target_table_sha256']}`",
        f"Ground truth SHA-256: `{manifest['ground_truth_sha256']}`",
        f"Code revision: `{payload['code_revision']}`",
        "",
    ])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_public_schema_benchmark(
    *,
    project_root: Path,
    dataset_id: str,
    data_root: Path,
    output_root: Path,
    methods: Iterable[str] = ("exact_normalized_name", "token_jaccard", "project_schema_rule_v1", "project_schema_profile_v2"),
    download: bool,
) -> Path:
    dataset_dir, manifest = prepare_schema_dataset(dataset_id, data_root, download=download)
    source, target, gold, source_samples, target_samples = load_schema_task(dataset_dir)
    results = {
        method: evaluate_schema_matches(
            source,
            target,
            gold,
            method,
            source_samples=source_samples,
            target_samples=target_samples,
        )
        for method in methods
    }
    return write_schema_run(
        project_root=project_root,
        dataset_id=dataset_id,
        manifest=manifest,
        results=results,
        output_root=output_root,
    )
