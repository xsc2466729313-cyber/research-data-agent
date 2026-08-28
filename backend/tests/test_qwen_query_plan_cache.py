from __future__ import annotations

import json
from pathlib import Path

from backend.app.retrieval.query_understanding import RetrievalQueryPlan, validate_query_plan
from scripts.build_qwen_query_plan_cache import (
    _selected_query_ids,
    conservatively_repair_plan,
    load_queries_without_qrels,
)


def test_load_queries_does_not_require_qrels(tmp_path: Path) -> None:
    (tmp_path / "queries.jsonl").write_text(json.dumps({"_id": "q1", "text": "HER2 response"}) + "\n", encoding="utf-8")
    assert load_queries_without_qrels(tmp_path) == {"q1": "HER2 response"}


def test_selection_manifest_returns_dataset_specific_query_ids() -> None:
    selection = {
        "datasets": {
            "beir_scifact": {
                "selected": [
                    {"query_id": "q2", "stratum": "short"},
                    {"query_id": "q7", "stratum": "long"},
                ]
            }
        }
    }
    assert _selected_query_ids(selection, "beir_scifact") == ["q2", "q7"]
    assert _selected_query_ids({}, "beir_scifact") is None


def test_protected_term_repair_adds_missing_terms_without_qrels() -> None:
    query = "co-IR blockade does not cause adverse autoimmune events"
    plan = RetrievalQueryPlan(keyword_query="co-IR blockade autoimmune safety")
    repaired, applied = conservatively_repair_plan(plan, query)
    assert applied is True
    assert validate_query_plan(repaired, query).valid is True
    assert "not" in repaired.keyword_query
