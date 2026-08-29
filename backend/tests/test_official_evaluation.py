from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.evaluation.official_run import run_official_evaluation
from backend.app.main import app


client = TestClient(app)


def _partial_retriever(question_id: str, _question: str) -> list[str]:
    if question_id.startswith("oc01"):
        return ["GSE25066", "CIViC"]
    if question_id.startswith("oc06"):
        return ["CIViC"]
    if question_id.startswith("oc08"):
        return ["DepMap"]
    if question_id.startswith("oc07"):
        return ["NCT01104584", "AACT"]
    return ["brca_metabric"]


def test_official_evaluation_scores_from_system_observations_not_hardcoded(tmp_path: Path) -> None:
    result = run_official_evaluation(
        evaluation_id="official-candidate-fixture-wiring",
        retrieval_fn=_partial_retriever,
        output_dir=tmp_path,
        persist_dashboard=False,
    )

    assert result.gold_set is not None
    assert result.gold_set.gold_set_id == "breast-cancer-official-candidate-20260829"
    assert result.evaluation_status.value in {"EVALUATED", "PARTIALLY_EVALUATED"}
    assert result.metrics.sdti.value is not None
    assert 0 < float(result.metrics.sdti.value) < 100
    assert float(result.metrics.sdti.value) != 66.94
    assert result.metrics.retrieval_f1.value is not None
    assert float(result.metrics.retrieval_f1.value) < 1.0
    assert "official_candidate" in result.notice or "frozen_test" in result.notice
    assert result.safety.publish_allowed is False
    metrics_path = tmp_path / result.evaluation_id / "metrics.json"
    assert metrics_path.is_file()
    dumped = metrics_path.read_text(encoding="utf-8")
    assert "66.94" not in dumped
    assert "development-xsc-qwen-live" not in dumped


def test_official_run_endpoint_uses_injected_path_via_real_templates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.evaluation.official_run.DEFAULT_OUTPUT",
        tmp_path,
    )
    monkeypatch.setattr(
        "backend.app.main.run_official_evaluation",
        lambda **kwargs: run_official_evaluation(
            evaluation_id="official-candidate-api-wiring",
            retrieval_fn=_partial_retriever,
            output_dir=tmp_path,
            persist_dashboard=False,
        ),
    )
    response = client.post("/api/evaluation/official-run", json={"retrieval": "planner"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["gold_set"]["gold_set_id"] == "breast-cancer-official-candidate-20260829"
    assert payload["metrics"]["sdti"]["value"] is not None
    assert payload["metrics"]["sdti"]["value"] != 66.94
    assert payload["safety"]["publish_allowed"] is False
