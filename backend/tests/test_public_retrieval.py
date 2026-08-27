from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.app.evaluation.public_retrieval import (
    BM25Index,
    ProjectHybridHashIndex,
    evaluate_retriever,
    load_beir,
)


def test_bm25_and_project_hybrid_retrieve_relevant_document() -> None:
    corpus = {
        "d1": "HER2 positive breast cancer pathological complete response",
        "d2": "weather forecast and airport delays",
        "d3": "PIK3CA mutation in breast cancer",
    }
    queries = {"q1": "HER2 breast cancer response"}
    qrels = {"q1": {"d1": 1}}
    for retriever in (BM25Index(corpus), ProjectHybridHashIndex(corpus)):
        metrics = evaluate_retriever(retriever, queries, qrels)
        assert metrics.query_count == 1
        assert metrics.ndcg_at_10 == pytest.approx(1.0)
        assert metrics.recall_at_100 == pytest.approx(1.0)
        assert metrics.mrr_at_10 == pytest.approx(1.0)


def test_load_beir_preserves_official_ids_and_graded_qrels(tmp_path: Path) -> None:
    (tmp_path / "qrels").mkdir()
    (tmp_path / "corpus.jsonl").write_text(
        json.dumps({"_id": "d1", "title": "Title", "text": "Body"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "queries.jsonl").write_text(
        json.dumps({"_id": "q1", "text": "Question"}) + "\n",
        encoding="utf-8",
    )
    with (tmp_path / "qrels" / "test.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query-id", "corpus-id", "score"], delimiter="\t")
        writer.writeheader()
        writer.writerow({"query-id": "q1", "corpus-id": "d1", "score": 2})
    corpus, queries, qrels = load_beir(tmp_path)
    assert corpus == {"d1": "Title Body"}
    assert queries == {"q1": "Question"}
    assert qrels == {"q1": {"d1": 2}}


def test_evaluation_uses_graded_ndcg() -> None:
    class FixedRanker:
        def rank(self, query: str, top_k: int) -> list[str]:
            return ["weak", "strong"]

    metrics = evaluate_retriever(
        FixedRanker(),  # type: ignore[arg-type]
        {"q1": "question"},
        {"q1": {"strong": 2, "weak": 1}},
    )
    assert 0 < metrics.ndcg_at_10 < 1
    assert metrics.recall_at_100 == 1
    assert metrics.mrr_at_10 == 1
