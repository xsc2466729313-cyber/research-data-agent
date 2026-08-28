from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.evaluation.public_retrieval import BM25Index, evaluate_retriever
from backend.app.evaluation.semantic_retrieval import (
    CrossEncoderBenchmarkIndex,
    HybridSemanticBenchmarkIndex,
    SentenceTransformerBenchmarkIndex,
)


class FakeEmbeddingModel:
    def encode(self, texts, **kwargs):
        return np.asarray(
            [[1.0, 0.0] if any(token in text.casefold() for token in ("her2", "erbb2", "response")) else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )


class FakeCrossEncoder:
    def predict(self, pairs, **kwargs):
        return np.asarray([3.0 if "HER2" in document else -3.0 for _, document in pairs])


def test_semantic_hybrid_and_reranker_share_frozen_corpus_without_test_tuning(tmp_path: Path) -> None:
    corpus = {
        "d1": "HER2 breast cancer pathological response",
        "d2": "weather airport",
        "d3": "ERBB2 neoadjuvant treatment",
    }
    queries = {"q1": "HER2 response"}
    qrels = {"q1": {"d1": 1}}
    semantic = SentenceTransformerBenchmarkIndex(
        corpus,
        model_name="fake-model",
        cache_path=tmp_path / "vectors.npy",
        model=FakeEmbeddingModel(),
        query_instruction="",
    )
    hybrid = HybridSemanticBenchmarkIndex(BM25Index(corpus), semantic)
    reranked = CrossEncoderBenchmarkIndex(hybrid, model_name="fake-cross", model=FakeCrossEncoder())
    for index in (semantic, hybrid, reranked):
        metrics = evaluate_retriever(index, queries, qrels)  # type: ignore[arg-type]
        assert metrics.ndcg_at_10 == 1.0
        assert metrics.estimated_cost_usd == 0.0
        assert metrics.qwen_invocation_rate == 0.0
    assert (tmp_path / "vectors.npy").exists()
