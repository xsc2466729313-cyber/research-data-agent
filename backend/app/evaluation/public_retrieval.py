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

import numpy as np

from backend.app.retrieval_text_features import retrieval_tokens
from backend.app.evaluation.semantic_retrieval import (
    CrossEncoderBenchmarkIndex,
    DevelopmentSelectedBenchmarkIndex,
    HybridSemanticBenchmarkIndex,
    ReciprocalRankFusionBenchmarkIndex,
    SentenceTransformerBenchmarkIndex,
)
from backend.app.vnext_config import load_vnext_config
from backend.app.retrieval.query_understanding import (
    build_rule_plan,
    reciprocal_rank_fusion,
    validate_query_plan,
)


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
    "beir_quora": {
        "archive_name": "quora.zip",
        "folder_name": "quora",
        "source_id": "beir:quora",
        "source_url": "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip",
    },
}


@dataclass(frozen=True)
class RetrievalMetrics:
    ndcg_at_10: float
    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    precision_at_10: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    recall_at_100: float
    hit_rate_at_1: float
    hit_rate_at_3: float
    hit_rate_at_5: float
    hit_rate_at_10: float
    mrr_at_10: float
    mean_latency_ms: float
    std_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    query_count: int
    index_build_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    qwen_invocation_rate: float = 0.0


@dataclass(frozen=True)
class RetrievalConfig:
    """Parameters selected without reading held-out test qrels."""

    k1: float
    b: float
    fit_split: str
    fit_ndcg_at_10: float | None


@dataclass(frozen=True)
class HybridWeightConfig:
    lexical_weight: float
    dense_weight: float
    fit_split: str
    fit_ndcg_at_10: float | None


@dataclass(frozen=True)
class RRFConfig:
    lexical_weight: float
    dense_weight: float
    rrf_k: int
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
        self._doc_lengths = np.asarray(self.doc_lengths, dtype=np.float64)
        self._posting_arrays = {
            token: (
                np.asarray([item[0] for item in posting], dtype=np.int32),
                np.asarray([item[1] for item in posting], dtype=np.float64),
                math.log(1.0 + (self.document_count - len(posting) + 0.5) / (len(posting) + 0.5)),
            )
            for token, posting in self.postings.items()
        }

    def _score_array(self, query: str) -> np.ndarray:
        scores = np.zeros(self.document_count, dtype=np.float64)
        for token in set(_tokens(query)):
            posting = self._posting_arrays.get(token)
            if posting is None:
                continue
            doc_indices, frequencies, idf = posting
            length_ratio = self._doc_lengths[doc_indices] / max(self.avg_doc_length, 1e-12)
            denominator = frequencies + self.k1 * (1.0 - self.b + self.b * length_ratio)
            scores[doc_indices] += idf * frequencies * (self.k1 + 1.0) / denominator
        return scores

    def score(self, query: str) -> dict[int, float]:
        scores = self._score_array(query)
        indices = np.flatnonzero(scores > 0.0)
        return {int(index): float(scores[index]) for index in indices}

    def rank(self, query: str, top_k: int) -> list[str]:
        scores = self._score_array(query)
        positive = np.flatnonzero(scores > 0.0)
        if len(positive) > top_k:
            candidate_positions = np.argpartition(-scores[positive], top_k - 1)[:top_k]
            candidates = positive[candidate_positions].tolist()
        else:
            candidates = positive.tolist()
        ranked = sorted(candidates, key=lambda index: (-scores[index], self.doc_ids[index]))
        return [self.doc_ids[index] for index in ranked]


class QueryUnderstandingIndex:
    """A transparent wrapper that changes only query construction and fusion."""

    def __init__(self, base: BM25Index, mode: str, planner=None) -> None:
        self.base = base
        self.mode = mode
        self.planner = planner
        self.doc_ids = base.doc_ids
        self.method_id = f"{base.method_id}_query_{mode}"
        self.method_label = f"{base.method_label} + query understanding ({mode})"
        self.index_build_seconds = getattr(base, "index_build_seconds", 0.0)
        self.estimated_cost_usd = getattr(base, "estimated_cost_usd", 0.0)
        self.qwen_invocation_rate = 0.0 if planner is None else 1.0
        self.fallback_count = 0

    def reset_query_cache(self) -> None:
        reset = getattr(self.base, "reset_query_cache", None)
        if callable(reset):
            reset()

    def rank(self, query: str, top_k: int) -> list[str]:
        queries = self._queries(query)
        if len(queries) == 1:
            return self.base.rank(queries[0], top_k)
        rankings = [self.base.rank(item, 100) for item in queries]
        index_by_id = {doc_id: index for index, doc_id in enumerate(self.doc_ids)}
        index_rankings = [[index_by_id[item] for item in ranking if item in index_by_id] for ranking in rankings]
        fused = reciprocal_rank_fusion(index_rankings, k=60, top_k=top_k)
        return [self.doc_ids[index] for index, _score in fused]

    def _queries(self, query: str) -> list[str]:
        if self.mode == "raw":
            return [query.strip()]
        if self.mode == "rules":
            checked = validate_query_plan(build_rule_plan(query), query)
            return checked.accepted_queries or [query.strip()]
        if self.planner is None:
            self.fallback_count += 1
            return [query.strip()]
        try:
            checked = validate_query_plan(self.planner(query), query)
            if checked.fallback_used:
                self.fallback_count += 1
            accepted = checked.accepted_queries or [query.strip()]
            if self.mode == "rules_qwen":
                rules = validate_query_plan(build_rule_plan(query), query).accepted_queries
                return list(dict.fromkeys([*rules, *accepted]))
            return accepted[:1] if self.mode == "qwen_single" else accepted
        except Exception:
            self.fallback_count += 1
            return [query.strip()]


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


def fit_hybrid_weights(
    lexical: TunedBM25Index,
    semantic: SentenceTransformerBenchmarkIndex,
    queries: dict[str, str],
    dataset_dir: Path,
) -> HybridWeightConfig:
    """Tune fusion weights on train/dev only; test qrels are never inspected."""
    fit_split = "dev" if (dataset_dir / "qrels" / "dev.tsv").exists() else "train"
    fit_qrels = _load_qrels(dataset_dir, fit_split)
    if not fit_qrels:
        return HybridWeightConfig(0.55, 0.45, "none", None)
    best: tuple[float, float, float] | None = None
    for lexical_weight in (0.0, 0.25, 0.5, 0.75, 1.0):
        dense_weight = 1.0 - lexical_weight
        candidate_index = HybridSemanticBenchmarkIndex(
            lexical, semantic, lexical_weight=lexical_weight, dense_weight=dense_weight
        )
        score = evaluate_retriever(candidate_index, queries, fit_qrels).ndcg_at_10
        candidate = (score, lexical_weight, dense_weight)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return HybridWeightConfig(best[1], best[2], fit_split, best[0])


def fit_rrf_parameters(
    lexical: TunedBM25Index,
    semantic: SentenceTransformerBenchmarkIndex,
    queries: dict[str, str],
    dataset_dir: Path,
) -> RRFConfig:
    """Choose rank-fusion parameters on train/dev qrels only."""
    fit_split = "dev" if (dataset_dir / "qrels" / "dev.tsv").exists() else "train"
    fit_qrels = _load_qrels(dataset_dir, fit_split)
    if not fit_qrels:
        return RRFConfig(0.5, 0.5, 60, "none", None)
    best: tuple[float, float, float, int] | None = None
    for lexical_weight in (0.25, 0.5, 0.75):
        dense_weight = 1.0 - lexical_weight
        for rrf_k in (10, 30, 60, 100):
            candidate = ReciprocalRankFusionBenchmarkIndex(
                lexical,
                semantic,
                lexical_weight=lexical_weight,
                dense_weight=dense_weight,
                rrf_k=rrf_k,
            )
            score = evaluate_retriever(candidate, queries, fit_qrels).ndcg_at_10
            choice = (score, lexical_weight, dense_weight, -rrf_k)
            if best is None or choice > best:
                best = choice
    assert best is not None
    return RRFConfig(best[1], best[2], -best[3], fit_split, best[0])


def select_development_retriever(
    candidates: dict[str, object],
    queries: dict[str, str],
    dataset_dir: Path,
) -> tuple[str, str, float | None, str]:
    """Select a candidate without inspecting held-out test qrels."""

    fit_split = "dev" if (dataset_dir / "qrels" / "dev.tsv").exists() else "train"
    fit_qrels = _load_qrels(dataset_dir, fit_split)
    if not fit_qrels:
        return "semantic", fit_split, None, "no train/dev qrels; fixed semantic fallback"
    scores = {
        name: evaluate_retriever(candidate, queries, fit_qrels).ndcg_at_10
        for name, candidate in candidates.items()
    }
    selected_name = max(scores, key=lambda name: (scores[name], name == "semantic"))
    return selected_name, fit_split, scores[selected_name], json.dumps(scores, sort_keys=True)


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
    reset = getattr(retriever, "reset_query_cache", None)
    if callable(reset):
        reset()
    ndcgs: list[float] = []
    precision_by_k: dict[int, list[float]] = {k: [] for k in (1, 3, 5, 10)}
    recall_by_k: dict[int, list[float]] = {k: [] for k in (1, 3, 5, 10, 100)}
    hit_by_k: dict[int, list[float]] = {k: [] for k in (1, 3, 5, 10)}
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    eligible_queries = [query_id for query_id in sorted(qrels) if query_id in queries]
    batch_rank = getattr(retriever, "rank_many", None)
    batch_rankings: dict[str, list[str]] = {}
    batch_latency_share = 0.0
    if callable(batch_rank):
        batch_started = time.perf_counter()
        rankings = batch_rank([queries[query_id] for query_id in eligible_queries], 100)
        batch_latency_share = (time.perf_counter() - batch_started) * 1000 / max(1, len(eligible_queries))
        batch_rankings = dict(zip(eligible_queries, rankings))
    for query_id in eligible_queries:
        started = time.perf_counter()
        ranking = batch_rankings.get(query_id) or retriever.rank(queries[query_id], 100)
        latencies.append(batch_latency_share + (time.perf_counter() - started) * 1000)
        relevant = qrels[query_id]
        gains = [relevant.get(doc_id, 0) for doc_id in ranking[:10]]
        dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
        ideal = sorted(relevant.values(), reverse=True)[:10]
        idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
        ndcgs.append(dcg / idcg if idcg else 0.0)
        relevant_ids = set(relevant)
        for k in (1, 3, 5, 10):
            retrieved_relevant = len(set(ranking[:k]) & relevant_ids)
            precision_by_k[k].append(retrieved_relevant / k)
            recall_by_k[k].append(retrieved_relevant / len(relevant) if relevant else 0.0)
            hit_by_k[k].append(float(retrieved_relevant > 0))
        retrieved_relevant = len(set(ranking[:100]) & relevant_ids)
        recall_by_k[100].append(retrieved_relevant / len(relevant) if relevant else 0.0)
        first_rank = next((rank for rank, doc_id in enumerate(ranking[:10], start=1) if doc_id in relevant), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
    if not ndcgs:
        raise ValueError("No test queries were shared by queries.jsonl and qrels/test.tsv")
    mean_latency = sum(latencies) / len(latencies)
    sorted_latencies = sorted(latencies)
    return RetrievalMetrics(
        ndcg_at_10=sum(ndcgs) / len(ndcgs),
        precision_at_1=sum(precision_by_k[1]) / len(ndcgs),
        precision_at_3=sum(precision_by_k[3]) / len(ndcgs),
        precision_at_5=sum(precision_by_k[5]) / len(ndcgs),
        precision_at_10=sum(precision_by_k[10]) / len(ndcgs),
        recall_at_1=sum(recall_by_k[1]) / len(ndcgs),
        recall_at_3=sum(recall_by_k[3]) / len(ndcgs),
        recall_at_5=sum(recall_by_k[5]) / len(ndcgs),
        recall_at_10=sum(recall_by_k[10]) / len(ndcgs),
        recall_at_100=sum(recall_by_k[100]) / len(ndcgs),
        hit_rate_at_1=sum(hit_by_k[1]) / len(ndcgs),
        hit_rate_at_3=sum(hit_by_k[3]) / len(ndcgs),
        hit_rate_at_5=sum(hit_by_k[5]) / len(ndcgs),
        hit_rate_at_10=sum(hit_by_k[10]) / len(ndcgs),
        mrr_at_10=sum(reciprocal_ranks) / len(reciprocal_ranks),
        mean_latency_ms=mean_latency,
        std_latency_ms=math.sqrt(sum((value - mean_latency) ** 2 for value in latencies) / len(latencies)),
        p50_latency_ms=sorted_latencies[max(0, math.ceil(len(sorted_latencies) * 0.50) - 1)],
        p95_latency_ms=sorted_latencies[max(0, math.ceil(len(sorted_latencies) * 0.95) - 1)],
        query_count=len(ndcgs),
        index_build_seconds=float(getattr(retriever, "index_build_seconds", 0.0)),
        estimated_cost_usd=float(getattr(retriever, "estimated_cost_usd", 0.0)),
        qwen_invocation_rate=float(getattr(retriever, "qwen_invocation_rate", 0.0)),
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
    method_configs: dict[str, object] | None = None,
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
            method_id: asdict(config) if hasattr(config, "__dataclass_fields__") else config
            for method_id, config in (method_configs or {}).items()
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
            for metric_name in (
                "ndcg_at_10", "precision_at_1", "precision_at_3", "precision_at_5", "precision_at_10",
                "recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "recall_at_100",
                "hit_rate_at_1", "hit_rate_at_3", "hit_rate_at_5", "hit_rate_at_10", "mrr_at_10",
                "mean_latency_ms", "std_latency_ms", "p50_latency_ms", "p95_latency_ms",
                "index_build_seconds", "estimated_cost_usd", "qwen_invocation_rate",
            ):
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
                    "direction": "lower" if metric_name in {"mean_latency_ms", "std_latency_ms", "p50_latency_ms", "p95_latency_ms", "index_build_seconds", "estimated_cost_usd"} else "higher",
                    "unit": "ms_per_query" if metric_name.endswith("latency_ms") else "seconds" if metric_name == "index_build_seconds" else "usd" if metric_name == "estimated_cost_usd" else "ratio",
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
        "| 方法 | 前十条排序 | 前一条命中 | 前三条命中 | 前十条命中 | 前十条召回 | 前百条召回 | 首条排序 | 平均用时 | 用时标准差 | P95用时 | 查询数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, (label, metrics) in metrics_by_method.items():
        lines.append(
            f"| {label} | {metrics.ndcg_at_10:.4f} | {metrics.hit_rate_at_1:.4f} | {metrics.hit_rate_at_3:.4f} | "
            f"{metrics.hit_rate_at_10:.4f} | {metrics.recall_at_10:.4f} | {metrics.recall_at_100:.4f} | "
            f"{metrics.mrr_at_10:.4f} | {metrics.mean_latency_ms:.2f} ms | {metrics.std_latency_ms:.2f} ms | "
            f"{metrics.p95_latency_ms:.2f} ms | {metrics.query_count} |"
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
    method_configs: dict[str, object] = {}
    tuned_config: RetrievalConfig | None = None
    semantic_index: SentenceTransformerBenchmarkIndex | None = None
    hybrid_index: HybridSemanticBenchmarkIndex | None = None
    hybrid_config: HybridWeightConfig | None = None
    rrf_index: ReciprocalRankFusionBenchmarkIndex | None = None
    rrf_config: RRFConfig | None = None
    selected_index: DevelopmentSelectedBenchmarkIndex | None = None
    vnext = load_vnext_config().retrieval
    cache_root = data_root / ".vnext_embedding_cache"

    def get_semantic() -> SentenceTransformerBenchmarkIndex:
        nonlocal semantic_index
        if semantic_index is None:
            cache_name = f"{dataset_id}_{hashlib.sha256(vnext.dense_backend.encode()).hexdigest()[:12]}.npy"
            semantic_index = SentenceTransformerBenchmarkIndex(
                corpus,
                model_name=vnext.dense_backend,
                cache_path=cache_root / cache_name,
                query_instruction=vnext.query_instruction,
                max_seq_length=vnext.max_seq_length,
            )
        return semantic_index

    def get_hybrid() -> HybridSemanticBenchmarkIndex:
        nonlocal hybrid_index, tuned_config, hybrid_config
        if hybrid_index is None:
            if tuned_config is None:
                tuned_config = fit_bm25_parameters(corpus, queries, dataset_dir)
            lexical = TunedBM25Index(corpus, k1=tuned_config.k1, b=tuned_config.b)
            if hybrid_config is None:
                hybrid_config = fit_hybrid_weights(
                    lexical, get_semantic(), queries, dataset_dir
                )
            hybrid_index = HybridSemanticBenchmarkIndex(
                lexical,
                get_semantic(),
                lexical_weight=hybrid_config.lexical_weight,
                dense_weight=hybrid_config.dense_weight,
            )
            method_configs[hybrid_index.method_id] = hybrid_config
        return hybrid_index

    def get_rrf() -> ReciprocalRankFusionBenchmarkIndex:
        nonlocal rrf_index, tuned_config, rrf_config
        if rrf_index is None:
            if tuned_config is None:
                tuned_config = fit_bm25_parameters(corpus, queries, dataset_dir)
            lexical = TunedBM25Index(corpus, k1=tuned_config.k1, b=tuned_config.b)
            if rrf_config is None:
                rrf_config = fit_rrf_parameters(lexical, get_semantic(), queries, dataset_dir)
            rrf_index = ReciprocalRankFusionBenchmarkIndex(
                lexical,
                get_semantic(),
                lexical_weight=rrf_config.lexical_weight,
                dense_weight=rrf_config.dense_weight,
                rrf_k=rrf_config.rrf_k,
            )
            method_configs[rrf_index.method_id] = rrf_config
        return rrf_index
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
        elif method == "vnext_semantic":
            retriever = get_semantic()
            method_id = retriever.method_id
        elif method == "vnext_hybrid":
            retriever = get_hybrid()
            method_id = retriever.method_id
        elif method == "vnext_rrf":
            retriever = get_rrf()
            method_id = retriever.method_id
        elif method == "vnext_hybrid_rerank":
            retriever = CrossEncoderBenchmarkIndex(
                get_hybrid(), model_name=vnext.reranker_backend, rerank_k=10
            )
            method_id = retriever.method_id
        elif method == "vnext_dev_selected":
            if selected_index is None:
                candidates: dict[str, object] = {"semantic": get_semantic()}
                fit_qrels = _load_qrels(
                    dataset_dir,
                    "dev" if (dataset_dir / "qrels" / "dev.tsv").exists() else "train",
                )
                if fit_qrels:
                    candidates["hybrid_rerank"] = CrossEncoderBenchmarkIndex(
                        get_hybrid(), model_name=vnext.reranker_backend, rerank_k=10
                    )
                selected_name, fit_split, fit_score, score_summary = select_development_retriever(
                    candidates, queries, dataset_dir
                )
                selected_index = DevelopmentSelectedBenchmarkIndex(
                    candidates[selected_name],
                    selected_name=selected_name,
                    fit_split=fit_split,
                    fit_ndcg_at_10=fit_score,
                )
                method_configs[selected_index.method_id] = {
                    "selected_name": selected_name,
                    "fit_split": fit_split,
                    "fit_ndcg_at_10": fit_score,
                    "candidate_scores": score_summary,
                }
            retriever = selected_index
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
