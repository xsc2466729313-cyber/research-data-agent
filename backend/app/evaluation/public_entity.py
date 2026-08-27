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
    "deepmatcher_beer_ratebeer": {
        "archive_name": "beer_ratebeer.zip",
        "folder_name": "beer_ratebeer",
        "source_id": "github:anhaidgroup/deepmatcher",
        "source_url": "https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md",
        "download_url": "http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Beer/beer_exp_data.zip",
    },
    "deepmatcher_fodors_zagats": {
        "archive_name": "fodors_zagats.zip",
        "folder_name": "fodors_zagats",
        "source_id": "github:anhaidgroup/deepmatcher",
        "source_url": "https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md",
        "download_url": "http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Fodors-Zagats/fodors_zagat_exp_data.zip",
    },
    "deepmatcher_amazon_google": {
        "archive_name": "amazon_google.zip",
        "folder_name": "amazon_google",
        "source_id": "github:anhaidgroup/deepmatcher",
        "source_url": "https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md",
        "download_url": "http://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Amazon-Google/amazon_google_exp_data.zip",
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


@dataclass(frozen=True)
class EntityRuleConfig:
    """Parameters selected on train/validation pairs only."""

    title_word_weight: float
    title_char_weight: float
    title_containment_weight: float
    field_max_weight: float
    exact_field_weight: float
    threshold: float
    fit_split: str = "train_valid"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _entity_data_dir(dataset_dir: Path) -> Path:
    """Return the directory containing the official table and split CSVs.

    DeepMatcher archives are not completely uniform: most structured datasets
    use ``exp_data/`` while Amazon-Google stores the same files at the archive
    root.  The benchmark still reads the upstream train/valid/test files in
    either layout.
    """

    nested = dataset_dir / "exp_data"
    return nested if nested.exists() else dataset_dir


def prepare_entity_dataset(dataset_id: str, data_root: Path, *, download: bool) -> tuple[Path, dict[str, str]]:
    if dataset_id not in ENTITY_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset_id}")
    spec = ENTITY_DATASETS[dataset_id]
    data_root.mkdir(parents=True, exist_ok=True)
    dataset_dir = data_root / spec["folder_name"]
    archive = data_root / spec["archive_name"]
    data_dir = _entity_data_dir(dataset_dir)
    test_path = data_dir / "test.csv"
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
    data_dir = _entity_data_dir(dataset_dir)
    required = [data_dir / name for name in ("tableA.csv", "tableB.csv", "test.csv")]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Entity archive is incomplete: {missing}")
    return dataset_dir, {
        "dataset_id": dataset_id,
        "source_id": spec["source_id"],
        "source_url": spec["source_url"],
        "archive_sha256": _sha256(archive) if archive.exists() else "archive-not-retained",
        "table_a_sha256": _sha256(data_dir / "tableA.csv"),
        "table_b_sha256": _sha256(data_dir / "tableB.csv"),
        "test_sha256": _sha256(data_dir / "test.csv"),
    }


def _read_table(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _tokens(value: str) -> set[str]:
    return set(_normalize(value).split())


def _primary_text_value(row: dict[str, str]) -> str:
    preferred = {"title", "name", "beer_name", "product_name", "restaurant_name"}
    for field, value in row.items():
        if field.casefold() in preferred and str(value or "").strip():
            return str(value)
    return ""


def load_entity_pairs(
    dataset_dir: Path,
    split: str = "test",
) -> tuple[list[tuple[dict[str, str], dict[str, str], int]], dict[str, int]]:
    data_dir = _entity_data_dir(dataset_dir)
    table_a = _read_table(data_dir / "tableA.csv")
    table_b = _read_table(data_dir / "tableB.csv")
    pairs: list[tuple[dict[str, str], dict[str, str], int]] = []
    if split not in {"train", "valid", "test"}:
        raise ValueError(f"Unsupported entity split: {split}")
    split_path = data_dir / f"{split}.csv"
    if not split_path.exists():
        raise FileNotFoundError(f"Entity split is missing: {split_path}")
    with split_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            left = table_a.get(row["ltable_id"])
            right = table_b.get(row["rtable_id"])
            if left is None or right is None:
                raise ValueError(f"Test pair references missing row: {row}")
            pairs.append((left, right, int(row["label"])))
    return pairs, {
        "split": split,
        "pair_count": len(pairs),
        "positive_count": sum(label for _, _, label in pairs),
    }


def _title_similarity(left: dict[str, str], right: dict[str, str]) -> float:
    a, b = _tokens(_primary_text_value(left)), _tokens(_primary_text_value(right))
    return len(a & b) / len(a | b) if a and b else 0.0


def _title_containment(left: dict[str, str], right: dict[str, str]) -> float:
    a, b = _tokens(_primary_text_value(left)), _tokens(_primary_text_value(right))
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


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


def _character_similarity(left: str, right: str, *, n: int = 3) -> float:
    left_value, right_value = _normalize(left), _normalize(right)
    if not left_value or not right_value:
        return 0.0
    left_grams = {left_value[index:index + n] for index in range(max(0, len(left_value) - n + 1))}
    right_grams = {right_value[index:index + n] for index in range(max(0, len(right_value) - n + 1))}
    return len(left_grams & right_grams) / len(left_grams | right_grams) if left_grams and right_grams else 0.0


def _rule_features(left: dict[str, str], right: dict[str, str]) -> tuple[float, float, float, float, float]:
    """Extract domain-independent title and supporting-field evidence."""

    title_word = _title_similarity(left, right)
    title_char = _character_similarity(_primary_text_value(left), _primary_text_value(right))
    title_containment = _title_containment(left, right)
    field_scores: list[float] = []
    exact_fields = 0
    for field in left.keys():
        if field == "id" or field == "title" or field not in right:
            continue
        left_value, right_value = _normalize(left.get(field, "")), _normalize(right.get(field, ""))
        if not left_value or not right_value:
            continue
        score = 1.0 if left_value == right_value else _token_jaccard(left_value, right_value)
        field_scores.append(score)
        exact_fields += int(left_value == right_value)
    field_max = max(field_scores, default=0.0)
    exact_fraction = exact_fields / len(field_scores) if field_scores else 0.0
    return title_word, title_char, title_containment, field_max, exact_fraction


def _token_jaccard(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens and right_tokens else 0.0


def _predict(
    method: str,
    left: dict[str, str],
    right: dict[str, str],
    *,
    rule_config: EntityRuleConfig | None = None,
) -> bool:
    if method == "exact_title":
        left_title, right_title = _primary_text_value(left), _primary_text_value(right)
        return bool(_normalize(left_title)) and _normalize(left_title) == _normalize(right_title)
    if method == "title_jaccard":
        return _title_similarity(left, right) >= 0.8
    if method == "project_portability_rule_v1":
        title = _title_similarity(left, right)
        fields = _field_similarity(left, right)
        # Require a strong title signal or agreement across the other identity fields.
        return title >= 0.72 or (title >= 0.45 and fields >= 0.62)
    if method == "project_learned_entity_v2":
        config = rule_config or EntityRuleConfig(0.35, 0.20, 0.15, 0.20, 0.10, 0.70)
        title_word, title_char, title_containment, field_max, exact_fraction = _rule_features(left, right)
        score = (
            config.title_word_weight * title_word
            + config.title_char_weight * title_char
            + config.title_containment_weight * title_containment
            + config.field_max_weight * field_max
            + config.exact_field_weight * exact_fraction
        )
        return score >= config.threshold
    raise ValueError(f"Unsupported method: {method}")


def evaluate_entity_pairs(
    pairs: list[tuple[dict[str, str], dict[str, str], int]],
    method: str,
    *,
    rule_config: EntityRuleConfig | None = None,
) -> EntityMetrics:
    tp = fp = fn = 0
    latencies: list[float] = []
    for left, right, label in pairs:
        started = time.perf_counter()
        predicted = _predict(method, left, right, rule_config=rule_config)
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


def fit_entity_rule(
    train_pairs: list[tuple[dict[str, str], dict[str, str], int]],
    valid_pairs: list[tuple[dict[str, str], dict[str, str], int]],
) -> EntityRuleConfig:
    """Select a small, fixed hypothesis class on held-in development data."""

    candidates = (
        (0.45, 0.25, 0.00, 0.20, 0.10),
        (0.40, 0.20, 0.00, 0.25, 0.15),
        (0.35, 0.15, 0.00, 0.25, 0.25),
        (0.35, 0.25, 0.00, 0.15, 0.25),
        (0.30, 0.20, 0.00, 0.20, 0.30),
        (0.35, 0.20, 0.15, 0.20, 0.10),
        (0.30, 0.15, 0.20, 0.20, 0.15),
        (0.25, 0.15, 0.25, 0.20, 0.15),
        (0.30, 0.10, 0.30, 0.15, 0.15),
        (0.20, 0.10, 0.30, 0.20, 0.20),
    )
    development = valid_pairs or train_pairs
    feature_rows = [(_rule_features(left, right), label) for left, right, label in development]

    def score(features: tuple[float, float, float, float, float], weights: tuple[float, float, float, float, float]) -> float:
        return sum(value * weight for value, weight in zip(features, weights))

    best: tuple[float, float, float, tuple[float, float, float, float, float]] | None = None
    for weights in candidates:
        scored = [(score(features, weights), label) for features, label in feature_rows]
        for threshold_index in range(20, 101):
            threshold = threshold_index / 100
            tp = sum(value >= threshold and label == 1 for value, label in scored)
            fp = sum(value >= threshold and label == 0 for value, label in scored)
            fn = sum(value < threshold and label == 1 for value, label in scored)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            candidate = (f1, precision, threshold, weights)
            # Prefer higher precision on F1 ties, then the more conservative
            # threshold.  All choices are made on train/valid only.
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    if best is None:
        raise ValueError("Cannot fit entity rule on an empty development split")
    return EntityRuleConfig(*best[3], threshold=best[2])


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def write_entity_run(
    *,
    project_root: Path,
    dataset_id: str,
    manifest: dict[str, str],
    results: dict[str, EntityMetrics],
    method_configs: dict[str, EntityRuleConfig],
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
        "method_configs": {method: asdict(config) for method, config in method_configs.items()},
        "results": {method: asdict(metrics) for method, metrics in results.items()},
        "scope_notice": "These are generic entity-matching layer scores, not patient identity or clinical validity scores.",
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "evaluation_id", "evaluation_version", "layer", "stage", "benchmark_or_task",
        "stratum_name", "stratum_value", "method_id", "method_label", "base_model_id",
        "metric", "value", "direction", "unit", "n", "mean", "std", "ci95_low",
        "ci95_high", "run_count", "seed", "dataset_version", "evaluation_contract_id",
        "quality_gate", "publish_allowed", "source_id", "source_url", "raw_field",
        "raw_value", "notes",
    ]
    labels = {
        "exact_title": "Exact title",
        "title_jaccard": "Title token Jaccard",
        "project_portability_rule_v1": "Project portability rule v1",
        "project_learned_entity_v2": "Project learned entity rule v2",
    }
    with (run_dir / "unified_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, metrics in results.items():
            for metric_name in ("precision", "recall", "f1", "mean_latency_ms"):
                value = getattr(metrics, metric_name)
                writer.writerow({
                    "evaluation_id": run_dir.name,
                    "evaluation_version": "public-entity-v2",
                    "layer": "external_benchmarks",
                    "stage": "entity_matching",
                    "benchmark_or_task": dataset_id,
                    "stratum_name": "benchmark_dataset",
                    "stratum_value": dataset_id,
                    "method_id": method,
                    "method_label": labels.get(method, method),
                    "metric": metric_name,
                    "value": f"{value:.8f}",
                    "direction": "lower" if metric_name == "mean_latency_ms" else "higher",
                    "unit": "ms_per_pair" if metric_name == "mean_latency_ms" else "ratio",
                    "n": metrics.pair_count,
                    "run_count": 1,
                    "seed": "deterministic",
                    "dataset_version": manifest["test_sha256"][:12],
                    "quality_gate": "REVIEW",
                    "publish_allowed": "false",
                    "source_id": manifest["source_id"],
                    "source_url": manifest["source_url"],
                    "raw_field": metric_name,
                    "raw_value": f"{value:.12f}",
                    "notes": "Official DeepMatcher test split; train/valid used only for v2 rule fitting.",
                })
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
    train_pairs, _ = load_entity_pairs(dataset_dir, "train")
    valid_pairs, _ = load_entity_pairs(dataset_dir, "valid")
    test_pairs, _ = load_entity_pairs(dataset_dir, "test")
    learned_config = fit_entity_rule(train_pairs, valid_pairs)
    methods = ["exact_title", "title_jaccard", "project_portability_rule_v1", "project_learned_entity_v2"]
    results = {
        method: evaluate_entity_pairs(
            test_pairs,
            method,
            rule_config=learned_config if method == "project_learned_entity_v2" else None,
        )
        for method in methods
    }
    data_dir = _entity_data_dir(dataset_dir)
    manifest = {
        **manifest,
        "train_sha256": _sha256(data_dir / "train.csv"),
        "valid_sha256": _sha256(data_dir / "valid.csv"),
    }
    return write_entity_run(
        project_root=project_root,
        dataset_id=dataset_id,
        manifest=manifest,
        results=results,
        method_configs={"project_learned_entity_v2": learned_config},
        output_root=output_root,
    )
