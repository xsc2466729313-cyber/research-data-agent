from __future__ import annotations

import json
from pathlib import Path

from scripts.build_qwen_query_plan_cache import load_queries_without_qrels


def test_load_queries_does_not_require_qrels(tmp_path: Path) -> None:
    (tmp_path / "queries.jsonl").write_text(json.dumps({"_id": "q1", "text": "HER2 response"}) + "\n", encoding="utf-8")
    assert load_queries_without_qrels(tmp_path) == {"q1": "HER2 response"}
