from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.evaluation.overview import build_evaluation_overview, retrieval_probe_from_matches
from backend.app.main import app


client = TestClient(app)


def test_overview_endpoint_keeps_official_metrics_unevaluated() -> None:
    response = client.get("/api/evaluation/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation_status"] == "NOT_EVALUATED"
    assert payload["official_metrics_allowed"] is False
    assert all(item["value"] is None for item in payload["official_metrics"])
    assert payload["official_metrics"][-1]["key"] == "sdti"
    assert payload["official_metrics"][-1]["status"] == "NOT_EVALUATED"
    assert "AI_PROVISIONAL" not in {item["status"] for item in payload["official_metrics"]}
    assert len(payload["protocol"]) == 5
    assert payload["protocol"][0]["step_id"] == "01-subject-run"
    assert payload["goldset_row_counts"]["retrieval_gold.csv"] == 0
    assert payload["team_reference"]["available"] is False
    assert payload["toolkit_run"]["status"] in {"待运行", "已计算"}
    assert payload["official_metrics"][-1]["value"] is None
    assert all(item["status"] != "TEAM_REFERENCE" for item in payload["official_metrics"])
    assert all(item["status"] != "AI_PROVISIONAL" for item in payload.get("toolkit_run", {}).get("metrics", []))


def test_retrieval_probe_uses_selected_candidates_as_relevance() -> None:
    matches = [
        SimpleNamespace(match_score=0.9, selected=True),
        SimpleNamespace(match_score=0.8, selected=False),
        SimpleNamespace(match_score=0.4, selected=True),
        SimpleNamespace(match_score=0.2, selected=False),
    ]

    probe = retrieval_probe_from_matches(matches)

    by_key = {item.key: item.value for item in probe.metrics}
    assert probe.cases == 4
    assert probe.status == "已计算"
    assert by_key["recall@1"] == 0.5
    assert by_key["recall@3"] == 1.0
    assert by_key["ndcg@3"] is not None
    assert 0.0 < by_key["ndcg@3"] <= 1.0


def test_overview_builder_does_not_copy_external_proxy_scores() -> None:
    overview = build_evaluation_overview(goldset_row_counts={"retrieval_gold.csv": 0, "field_gold.csv": 0, "error_gold.csv": 0})

    assert overview.retrieval_probe.status == "待运行"
    assert overview.notice.startswith("评测方法对齐统一评测方案工具包")
    assert all(item.status == "NOT_EVALUATED" for item in overview.official_metrics)
    assert overview.team_reference.available is False
    assert overview.toolkit_run.status == "待运行"
    assert overview.evaluation_status == "NOT_EVALUATED"
