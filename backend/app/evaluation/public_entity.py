from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import time
import urllib.request
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ENTITY_DATASETS = {
    "deepmatcher_dblp_acm": {
        "archive_name": "dblp_acm.zip",
        "folder_name": "dblp_acm",
        "source_id": "github:anhaidgroup/deepmatcher",
        "source_url": "https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md",
        "download_url": "https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/DBLP-ACM/dblp_acm_exp_data.zip",
    },
    "deepmatcher_walmart_amazon": {
        "archive_name": "walmart_amazon.zip",
        "folder_name": "walmart_amazon",
        "source_id": "github:anhaidgroup/deepmatcher",
        "source_url": "https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md",
        "download_url": "https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Walmart-Amazon/walmart_amazon_exp_data.zip",
    },
}


@dataclass(frozen=True)
class EntityMetrics:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    pair_count: int
    positive_count: int
    mean_latency_ms: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_entity_dataset(dataset_id: str, data_root: Path, *, download: bool) -> tuple[Path, dict[str, str]]:
    if dataset_id not in ENTITY_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset_id}")
    spec = ENTITY_DATASETS[dataset_id]
    data_root.mkdir(parents=True, exist_ok=True)
    dataset_dir = data_root / spec["folder_name"]
    archive = data_root / spec["archive_name"]
    test_path = dataset_dir / "exp_data" / "test.csv"
    if not test_path.exists():
        if not download:
            raise FileNotFoundError(f"{dataset_id} is missing. Re-run with --download.")
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + ".part")
            with urllib.request.urlopen(spec["download_url"], timeout=120) as response, partial.open("wb") as output:
                output.write(response.read())
            partial.replace(archive)
        with zipfile.ZipFile(archive) as zipped:
            root = dataset_dir.resolve()
            for member in zipped.infolist():
                target = (dataset_dir / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise ValueError(f"Unsafe archive member: {member.filename}")
            zipped.extractall(dataset_dir)
    required = [dataset_dir / "exp_data" / name for name in ("tableA.csv", "tableB.csv", "test.csv")]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Entity archive is incomplete: {missing}")
    return dataset_dir, {
        "dataset_id": dataset_id,
        "source_id": spec["source_id"],
        "source_url": spec["source_url"],
        "archive_sha256": _sha256(archive) if archive.exists() else "archive-not-retained",
        "table_a_sha256": _sha256(dataset_dir / "exp_data" / "tableA.csv"),
        "table_b_sha256": _sha256(dataset_dir / "exp_data" / "tableB.csv"),
        "test_sha256": _sha256(dataset_dir / "exp_data" / "test.csv"),
    }


def _read_table(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _tokens(value: str) -> set[str]:
    return set(_normalize(value).split())


def load_entity_pairs(dataset_dir: Path) -> tuple[list[tuple[dict[str, str], dict[str, str], int]], dict[str, int]]:
    table_a = _read_table(dataset_dir / "exp_data" / "tableA.csv")
    table_b = _read_table(dataset_dir / "exp_data" / "tableB.csv")
    pairs: list[tuple[dict[str, str], dict[str, str], int]] = []
    with (dataset_dir / "exp_data" / "test.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            left = table_a.get(row["ltable_id"])
            right = table_b.get(row["rtable_id"])
            if left is None or right is None:
                raise ValueError(f"Test pair references missing row: {row}")
            pairs.append((left, right, int(row["label"])))
    return pairs, {"pair_count": len(pairs), "positive_count": sum(label for _, _, label in pairs)}


def _title_similarity(left: dict[str, str], right: dict[str, str]) -> float:
    a, b = _tokens(left.get("title", "")), _tokens(right.get("title", ""))
    return len(a & b) / len(a | b) if a and b else 0.0


def _field_similarity(left: dict[str, str], right: dict[str, str]) -> float:
    fields = [field for field in left.keys() if field != "id" and field in right]
    if not fields:
        return 0.0
    values = []
    for field in fields:
        left_value, right_value = _normalize(left.get(field, "")), _normalize(right.get(field, ""))
        if not left_value or not right_value:
            values.append(0.0)
        elif left_value == right_value:
            values.append(1.0)
        else:
            left_tokens, right_tokens = set(left_value.split()), set(right_value.split())
            values.append(len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens and right_tokens else 0.0)
    return sum(values) / len(values)


def _predict(method: str, left: dict[str, str], right: dict[str, str]) -> bool:
    if method == "exact_title":
        return bool(_normalize(left.get("title", ""))) and _normalize(left.get("title", "")) == _normalize(right.get("title", ""))
    if method == "title_jaccard":
        return _title_similarity(left, right) >= 0.8
    if method == "project_portability_rule_v1":
        title = _title_similarity(left, right)
        fields = _field_similarity(left, right)
        # Require a strong title signal or agreement across the other identity fields.
        return title >= 0.72 or (title >= 0.45 and fields >= 0.62)
    raise ValueError(f"Unsupported method: {method}")


def evaluate_entity_pairs(pairs: list[tuple[dict[str, str], dict[str, str], int]], method: str) -> EntityMetrics:
    tp = fp = fn = 0
    latencies: list[float] = []
    for left, right, label in pairs:
        started = time.perf_counter()
        predicted = _predict(method, left, right)
        latencies.append((time.perf_counter() - started) * 1000)
        if predicted and label == 1:
            tp += 1
        elif predicted and label == 0:
            fp += 1
        elif not predicted and label == 1:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return EntityMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        pair_count=len(pairs),
        positive_count=sum(label for _, _, label in pairs),
        mean_latency_ms=sum(latencies) / max(1, len(latencies)),
    )


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def write_entity_run(
    *,
    project_root: Path,
    dataset_id: str,
    manifest: dict[str, str],
    results: dict[str, EntityMetrics],
    output_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_{dataset_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "public-entity-v1",
        "layer": "external_benchmarks",
        "stage": "entity_matching",
        "dataset": manifest,
        "split": "test",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": {method: asdict(metrics) for method, metrics in results.items()},
        "scope_notice": "These are generic entity-matching layer scores, not patient identity or clinical validity scores.",
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# {dataset_id} entity matching benchmark",
        "",
        "> This is a generic entity-matching layer test. It is not a patient identity or clinical-validity result.",
        "",
        "| Method | Precision | Recall | F1 | TP | FP | FN | Mean latency/pair |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, metrics in results.items():
        lines.append(f"| {method} | {metrics.precision:.4f} | {metrics.recall:.4f} | {metrics.f1:.4f} | {metrics.true_positive} | {metrics.false_positive} | {metrics.false_negative} | {metrics.mean_latency_ms:.4f} ms |")
    lines.extend(["", f"Source: {manifest['source_url']}", f"Test SHA-256: `{manifest['test_sha256']}`", f"Code revision: `{payload['code_revision']}`", ""])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_public_entity_benchmark(*, project_root: Path, dataset_id: str, data_root: Path, output_root: Path, download: bool) -> Path:
    dataset_dir, manifest = prepare_entity_dataset(dataset_id, data_root, download=download)
    pairs, _ = load_entity_pairs(dataset_dir)
    methods = ["exact_title", "title_jaccard", "project_portability_rule_v1"]
    results = {method: evaluate_entity_pairs(pairs, method) for method in methods}
    return write_entity_run(project_root=project_root, dataset_id=dataset_id, manifest=manifest, results=results, output_root=output_root)
