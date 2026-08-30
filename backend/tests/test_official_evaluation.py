from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.evaluation.official_run import (
    OfficialEvaluationLaunch,
    RetrievalRun,
    collect_observations,
    load_official_bundle,
    run_official_evaluation,
    validate_retrieved_sources,
)
from backend.app.models import SourceItem
from backend.app.main import app


client = TestClient(app)


def test_official_launch_defaults_to_strict_qwen_agent() -> None:
    launch = OfficialEvaluationLaunch()

    assert launch.retrieval == "agent"
    assert launch.use_qwen is True
    assert launch.allow_deterministic_fallback is False


def test_contained_high_risk_cases_are_not_counted_as_unresolved() -> None:
    _envelope, _manifest, bundle = load_official_bundle()

    _observations, _audit, unresolved, _source_validation = collect_observations(
        bundle,
        retrieval_fn=lambda _qid, _question: [],
        retrieval_label="fixture",
    )

    assert unresolved == 0


def test_qwen_audit_and_source_validation_use_current_run_sources() -> None:
    _envelope, _manifest, bundle = load_official_bundle()
    source = SourceItem(
        source_id="geo:GSE25066",
        task_id="official-fixture",
        source_name="GEO GSE25066",
        source_type="geo",
        accession="GSE25066",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066",
        status="downloaded",
    )
    retrieval_run = RetrievalRun(
        ids=["GSE25066"],
        model_provider="qwen",
        model_name="qwen3.8-max",
        used_model=True,
        used_qwen=True,
        deterministic_fallback_used=False,
        source_items=[source],
        quality_gate="REVIEW",
        publish_allowed=False,
    )

    _observations, audit, _unresolved, source_validation = collect_observations(
        bundle,
        retrieval_fn=lambda _qid, _question: retrieval_run,
        retrieval_label="agent_qwen_live",
    )

    assert audit["retrieval_method"] == "agent_qwen_live"
    assert audit["execution"]["model_provider"] == "qwen"
    assert audit["execution"]["model_name"] == "qwen3.8-max"
    assert audit["execution"]["used_qwen_for_all_questions"] is True
    assert audit["execution"]["deterministic_fallback_count"] == 0
    assert audit["execution"]["quality_gate_review_count"] == 11
    assert source_validation is not None
    assert source_validation.checked_source_count == 1
    assert source_validation.fake_source_count == 0


def test_source_validation_rejects_non_official_run_url() -> None:
    source = SourceItem(
        source_id="geo:GSE25066",
        task_id="official-fixture",
        source_name="Forged GEO mirror",
        source_type="geo",
        accession="GSE25066",
        url="https://example.com/GSE25066",
        status="downloaded",
    )

    summary, details = validate_retrieved_sources([source])

    assert summary is not None
    assert summary.checked_source_count == 1
    assert summary.fake_source_count == 1
    assert details[0]["valid"] is False


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
    assert result.execution is not None
    assert result.execution.retrieval_method == "injected"
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
    response = client.post("/api/evaluation/official-run", json={"retrieval": "agent"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["gold_set"]["gold_set_id"] == "breast-cancer-official-candidate-20260829"
    assert payload["metrics"]["sdti"]["value"] is not None
    assert payload["metrics"]["sdti"]["value"] != 66.94
    assert payload["safety"]["publish_allowed"] is False
