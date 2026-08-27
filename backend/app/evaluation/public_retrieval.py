from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from backend.app.retrieval_text_features import retrieval_tokens


BEIR_DATASETS = {
    "beir_scifact": {
        "archive_name": "scifact.zip",
        "folder_name": "scifact",
        "source_id": "beir:scifact",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip",
    },
    "beir_nfcorpus": {
        "archive_name": "nfcorpus.zip",
        "folder_name": "nfcorpus",
        "source_id": "beir:nfcorpus",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip",
    },
    "beir_scidocs": {
        "archive_name": "scidocs.zip",
        "folder_name": "scidocs",
        "source_id": "beir:scidocs",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip",
    },
    "beir_arguana": {
        "archive_name": "arguana.zip",
        "folder_name": "arguana",
        "source_id": "beir:arguana",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/arguana.zip",
    },
    "beir_fiqa": {
        "archive_name": "fiqa.zip",
        "folder_name": "fiqa",
        "source_id": "beir:fiqa",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip",
    },
    "beir_trec_covid": {
        "archive_name": "trec-covid.zip",
        "folder_name": "trec-covid",
        "source_id": "beir:trec-covid",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/trec-covid.zip",
    },
}


@dataclass(frozen=True)
class RetrievalMetrics:
    ndcg_at_10: float
    recall_at_100: float
    mrr_at_10: float
    mean_latency_ms: float
    query_count: int


@dataclass(frozen=True)
class RetrievalConfig:
    """Parameters selected without reading held-out test qrels."""

    k1: float
    b: float
    fit_split: str
    fit_ndcg_at_10: float | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_extract(archive: Path, target: Path) -> None:
    target_resolved = target.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            member_path = (target / member.filename).resolve()
            if target_resolved not in member_path.parents and member_path != target_resolved:
                raise ValueError(f"Unsafe archive member: {member.filename}")
        zipped.extractall(target)


def prepare_beir_dataset(dataset_id: str, data_root: Path, *, download: bool) -> tuple[Path, dict[str, str]]:
    if dataset_id not in BEIR_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset_id}")
    spec = BEIR_DATASETS[dataset_id]
    data_root.mkdir(parents=True, exist_ok=True)
    dataset_dir = data_root / spec["folder_name"]
    archive = data_root / spec["archive_name"]
    if not (dataset_dir / "corpus.jsonl").exists():
        if not download:
            raise FileNotFoundError(
                f"{dataset_id} is missing. Re-run with --download to fetch the official BEIR archive."
            )
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + ".part")
            with urllib.request.urlopen(spec["source_url"], timeout=120) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            partial.replace(archive)
        _safe_extract(archive, data_root)
    required = [dataset_dir / "corpus.jsonl", dataset_dir / "queries.jsonl", dataset_dir / "qrels" / "test.tsv"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"BEIR archive is incomplete: {missing}")
    manifest = {
        "dataset_id": dataset_id,
        "source_id": spec["source_id"],
        "source_url": spec["source_url"],
        "archive_sha256": _sha256(archive) if archive.exists() else "archive-not-retained",
        "corpus_sha256": _sha256(dataset_dir / "corpus.jsonl"),
        "queries_sha256": _sha256(dataset_dir / "queries.jsonl"),
        "qrels_test_sha256": _sha256(dataset_dir / "qrels" / "test.tsv"),
    }
    for split in ("train", "dev"):
        split_path = dataset_dir / "qrels" / f"{split}.tsv"
        if split_path.exists():
            manifest[f"qrels_{split}_sha256"] = _sha256(split_path)
    return dataset_dir, manifest


def _load_qrels(dataset_dir: Path, split: str) -> dict[str, dict[str, int]]:
    path = dataset_dir / "qrels" / f"{split}.tsv"
    if not path.exists():
        return {}
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            query_id = str(row.get("query-id") or row.get("query_id"))
            corpus_id = str(row.get("corpus-id") or row.get("corpus_id"))
            score = int(float(row.get("score") or 0))
            if score > 0:
                qrels[query_id][corpus_id] = score
    return dict(qrels)


def load_beir(
    dataset_dir: Path,
    qrels_split: str = "test",
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, int]]]:
    corpus: dict[str, str] = {}
    with (dataset_dir / "corpus.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            doc_id = str(row["_id"])
            corpus[doc_id] = " ".join(part for part in (row.get("title", ""), row.get("text", "")) if part).strip()
    queries: dict[str, str] = {}
    with (dataset_dir / "queries.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            queries[str(row["_id"])] = str(row["text"])
    return corpus, queries, _load_qrels(dataset_dir, qrels_split)


def _tokens(text: str) -> list[str]:
    return retrieval_tokens(text)


class BM25Index:
    method_id = "bm25_local_reference"
    method_label = "BM25 local reference"

    def __init__(self, corpus: dict[str, str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.doc_ids = list(corpus)
        self.k1 = k1
        self.b = b
        self.doc_lengths: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, doc_id in enumerate(self.doc_ids):
            counts = Counter(_tokens(corpus[doc_id]))
            self.doc_lengths.append(sum(counts.values()))
            for token, frequency in counts.items():
                self.postings[token].append((index, frequency))
        self.avg_doc_length = sum(self.doc_lengths) / max(1, len(self.doc_lengths))
        self.document_count = len(self.doc_ids)

    def score(self, query: str) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for token in set(_tokens(query)):
            posting = self.postings.get(token, [])
            document_frequency = len(posting)
            if not document_frequency:
                continue
            idf = math.log(1.0 + (self.document_count - document_frequency + 0.5) / (document_frequency + 0.5))
            for doc_index, frequency in posting:
                length_ratio = self.doc_lengths[doc_index] / max(self.avg_doc_length, 1e-12)
                denominator = frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
                scores[doc_index] += idf * frequency * (self.k1 + 1.0) / denominator
        return dict(scores)

    def rank(self, query: str, top_k: int) -> list[str]:
        scores = self.score(query)
        ranked = sorted(scores, key=lambda index: (-scores[index], self.doc_ids[index]))[:top_k]
        return [self.doc_ids[index] for index in ranked]


class TunedBM25Index(BM25Index):
    method_id = "project_bm25_tuned_v2"
    method_label = "Project BM25 tuned v2"


_BM25_CANDIDATES = (
    (1.2, 0.75),
    (1.5, 0.75),
    (1.8, 0.25),
)


def fit_bm25_parameters(
    corpus: dict[str, str],
    queries: dict[str, str],
    dataset_dir: Path,
) -> RetrievalConfig:
    """Choose a small pre-declared BM25 grid on dev, otherwise train qrels."""

    fit_split = "dev" if (dataset_dir / "qrels" / "dev.tsv").exists() else "train"
    fit_qrels = _load_qrels(dataset_dir, fit_split)
    if not fit_qrels:
        return RetrievalConfig(1.5, 0.75, "none", None)
    best: tuple[float, float, float] | None = None
    for k1, b in _BM25_CANDIDATES:
        metrics = evaluate_retriever(BM25Index(corpus, k1=k1, b=b), queries, fit_qrels)
        candidate = (metrics.ndcg_at_10, k1, b)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return RetrievalConfig(best[1], best[2], fit_split, best[0])


class ProjectHybridHashIndex:
    """Efficient benchmark adapter for the project's deterministic hybrid rank formula.

    It reproduces hashing-lexical-v1 cosine similarity and lexical query coverage.
    The graph and section terms are constant for a generic BEIR corpus and therefore
    do not change ranking.
    """

    method_id = "project_hybrid_hashing_lexical_v1"
    method_label = "Project Hybrid (hashing-lexical-v1)"

    def __init__(self, corpus: dict[str, str], *, dimensions: int = 384) -> None:
        self.doc_ids = list(corpus)
        self.dimensions = dimensions
        self.hash_postings: dict[int, list[tuple[int, float]]] = defaultdict(list)
        self.token_postings: dict[str, list[int]] = defaultdict(list)
        for doc_index, doc_id in enumerate(self.doc_ids):
            tokens = _tokens(corpus[doc_id])
            vector = self._sparse_hash(tokens)
            norm = math.sqrt(sum(value * value for value in vector.values()))
            if norm:
                for dimension, value in vector.items():
                    self.hash_postings[dimension].append((doc_index, value / norm))
            for token in set(tokens):
                self.token_postings[token].append(doc_index)

    def _sparse_hash(self, tokens: Iterable[str]) -> dict[int, float]:
        vector: dict[int, float] = defaultdict(float)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            dimension = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[dimension] += sign
        return dict(vector)

    def rank(self, query: str, top_k: int) -> list[str]:
        query_tokens = _tokens(query)
        query_vector = self._sparse_hash(query_tokens)
        query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
        semantic: dict[int, float] = defaultdict(float)
        if query_norm:
            for dimension, value in query_vector.items():
                for doc_index, doc_value in self.hash_postings.get(dimension, []):
                    semantic[doc_index] += value / query_norm * doc_value
        lexical_hits: dict[int, int] = defaultdict(int)
        query_terms = set(query_tokens)
        for token in query_terms:
            for doc_index in self.token_postings.get(token, []):
                lexical_hits[doc_index] += 1
        candidates = set(semantic) | set(lexical_hits)
        denominator = max(1, len(query_terms))
        scores = {
            index: 0.55 * max(0.0, min(1.0, semantic.get(index, 0.0)))
            + 0.30 * min(1.0, lexical_hits.get(index, 0) / denominator)
            for index in candidates
        }
        ranked = sorted(scores, key=lambda index: (-scores[index], self.doc_ids[index]))[:top_k]
        return [self.doc_ids[index] for index in ranked]


def evaluate_retriever(
    retriever: BM25Index | ProjectHybridHashIndex,
    queries: dict[str, str],
    qrels: dict[str, dict[str, int]],
) -> RetrievalMetrics:
    ndcgs: list[float] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    for query_id in sorted(qrels):
        if query_id not in queries:
            continue
        started = time.perf_counter()
        ranking = retriever.rank(queries[query_id], 100)
        latencies.append((time.perf_counter() - started) * 1000)
        relevant = qrels[query_id]
        gains = [relevant.get(doc_id, 0) for doc_id in ranking[:10]]
        dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
        ideal = sorted(relevant.values(), reverse=True)[:10]
        idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
        ndcgs.append(dcg / idcg if idcg else 0.0)
        retrieved_relevant = len(set(ranking[:100]) & set(relevant))
        recalls.append(retrieved_relevant / len(relevant) if relevant else 0.0)
        first_rank = next((rank for rank, doc_id in enumerate(ranking[:10], start=1) if doc_id in relevant), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
    if not ndcgs:
        raise ValueError("No test queries were shared by queries.jsonl and qrels/test.tsv")
    return RetrievalMetrics(
        ndcg_at_10=sum(ndcgs) / len(ndcgs),
        recall_at_100=sum(recalls) / len(recalls),
        mrr_at_10=sum(reciprocal_ranks) / len(reciprocal_ranks),
        mean_latency_ms=sum(latencies) / len(latencies),
        query_count=len(ndcgs),
    )


def _git_revision(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def write_run_artifacts(
    *,
    project_root: Path,
    dataset_id: str,
    manifest: dict[str, str],
    metrics_by_method: dict[str, tuple[str, RetrievalMetrics]],
    method_configs: dict[str, RetrievalConfig] | None = None,
    output_root: Path,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{timestamp}_{dataset_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "public-retrieval-v2",
        "layer": "external_benchmarks",
        "stage": "retrieval",
        "dataset": manifest,
        "split": "test",
        "code_revision": _git_revision(project_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": {
            method_id: {"method_label": label, **asdict(metrics)}
            for method_id, (label, metrics) in metrics_by_method.items()
        },
        "method_configs": {
            method_id: asdict(config) for method_id, config in (method_configs or {}).items()
        },
        "scope_notice": "These are retrieval-layer scores, not full-agent, clinical-validity, or SDTI scores.",
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
    with (run_dir / "unified_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method_id, (label, metrics) in metrics_by_method.items():
            for metric_name in ("ndcg_at_10", "recall_at_100", "mrr_at_10", "mean_latency_ms"):
                value = getattr(metrics, metric_name)
                writer.writerow({
                    "evaluation_id": run_dir.name,
                    "evaluation_version": "public-retrieval-v2",
                    "layer": "external_benchmarks",
                    "stage": "retrieval",
                    "benchmark_or_task": dataset_id,
                    "stratum_name": "benchmark_dataset",
                    "stratum_value": dataset_id,
                    "method_id": method_id,
                    "method_label": label,
                    "metric": metric_name,
                    "value": f"{value:.8f}",
                    "direction": "lower" if metric_name == "mean_latency_ms" else "higher",
                    "unit": "ms_per_query" if metric_name == "mean_latency_ms" else "ratio",
                    "n": metrics.query_count,
                    "run_count": 1,
                    "seed": "deterministic",
                    "dataset_version": manifest["qrels_test_sha256"][:12],
                    "quality_gate": "REVIEW",
                    "publish_allowed": "false",
                    "source_id": manifest["source_id"],
                    "source_url": manifest["source_url"],
                    "raw_field": metric_name,
                    "raw_value": f"{value:.12f}",
                    "notes": "Official BEIR test qrels; retrieval layer only; train/dev qrels are used only for tuned parameter selection.",
                })
    lines = [
        f"# {dataset_id} retrieval benchmark",
        "",
        "> This is a retrieval-layer test. It is not a full-agent, medical-validity, or SDTI result.",
        "",
        "| Method | nDCG@10 | Recall@100 | MRR@10 | Mean latency/query |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, (label, metrics) in metrics_by_method.items():
        lines.append(
            f"| {label} | {metrics.ndcg_at_10:.4f} | {metrics.recall_at_100:.4f} | "
            f"{metrics.mrr_at_10:.4f} | {metrics.mean_latency_ms:.2f} ms |"
        )
    lines.extend([
        "",
        f"Source: {manifest['source_url']}",
        f"Test qrels SHA-256: `{manifest['qrels_test_sha256']}`",
        f"Code revision: `{payload['code_revision']}`",
        "",
    ])
    (run_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir


def run_public_retrieval_benchmark(
    *,
    project_root: Path,
    dataset_id: str,
    data_root: Path,
    output_root: Path,
    methods: Iterable[str],
    download: bool,
) -> Path:
    dataset_dir, manifest = prepare_beir_dataset(dataset_id, data_root, download=download)
    corpus, queries, qrels = load_beir(dataset_dir)
    method_results: dict[str, tuple[str, RetrievalMetrics]] = {}
    method_configs: dict[str, RetrievalConfig] = {}
    tuned_config: RetrievalConfig | None = None
    for method in methods:
        if method == "bm25":
            retriever = BM25Index(corpus)
            method_id = retriever.method_id
        elif method == "project_bm25_tuned_v2":
            if tuned_config is None:
                tuned_config = fit_bm25_parameters(corpus, queries, dataset_dir)
            retriever = TunedBM25Index(corpus, k1=tuned_config.k1, b=tuned_config.b)
            method_id = retriever.method_id
            method_configs[method_id] = tuned_config
        elif method == "project_hybrid":
            retriever = ProjectHybridHashIndex(corpus)
            method_id = retriever.method_id
        else:
            raise ValueError(f"Unsupported method: {method}")
        method_results[method_id] = (retriever.method_label, evaluate_retriever(retriever, queries, qrels))
    return write_run_artifacts(
        project_root=project_root,
        dataset_id=dataset_id,
        manifest=manifest,
        metrics_by_method=method_results,
        method_configs=method_configs,
        output_root=output_root,
    )
