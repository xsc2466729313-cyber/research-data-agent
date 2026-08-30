from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.evaluation import EvaluationError, EvaluationService
from backend.app.evaluation.models import EvaluationRequest
from backend.tests.evaluation_fixtures import validated_evaluation_request


def test_without_real_goldset_all_metrics_are_not_evaluated(tmp_path: Path) -> None:
    service = EvaluationService(output_dir=tmp_path)

    result = service.run(EvaluationRequest(evaluation_id="no-real-gold"))

    assert result.evaluation_status.value == "NOT_EVALUATED"
    assert result.safety.publish_allowed is False
    assert result.safety.gate.value == "REVIEW"
    assert all(metric.value is None for _, metric in result.metrics)
    assert all(metric.status.value == "NOT_EVALUATED" for _, metric in result.metrics)
    assert {artifact.name for artifact in result.artifacts} == {
        "metrics.json",
        "report.md",
    }
    metrics_payload = json.loads(
        (tmp_path / "no-real-gold" / "metrics.json").read_text(encoding="utf-8")
    )
    assert metrics_payload["metrics"]["sdti"]["value"] is None
    assert "本报告不包含系统成绩" in (
        tmp_path / "no-real-gold" / "report.md"
    ).read_text(encoding="utf-8")


def test_validated_fixture_is_derived_from_rows_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    service = EvaluationService(output_dir=tmp_path)

    result = service.run(validated_evaluation_request("validated-fixture"))

    assert result.evaluation_status.value == "EVALUATED"
    assert result.counts is not None
    assert result.counts.retrieval.model_dump() == {"tp": 1, "fp": 0, "fn": 0}
    assert result.metrics.retrieval_precision.value == 1.0
    assert result.metrics.faithfulness.value == 1.0
    assert result.metrics.traceability.value == 1.0
    assert result.metrics.error_f1.value == 1.0
    assert result.metrics.repair_accuracy.value == 1.0
    assert result.metrics.sdti.value == 100.0
    assert result.safety.gate.value == "PASS"
    assert result.safety.publish_allowed is True
    assert all(Path(artifact.path).is_file() for artifact in result.artifacts)


def test_goldset_checksum_tampering_is_rejected(tmp_path: Path) -> None:
    request = validated_evaluation_request("tampered")
    assert request.gold_set is not None
    request.gold_set.field_gold[0].canonical_value = "Positive"

    with pytest.raises(EvaluationError) as exc_info:
        EvaluationService(output_dir=tmp_path).run(request)

    assert exc_info.value.code.value == "invalid_gold_set"
    assert "checksum" in exc_info.value.message
    assert not (tmp_path / "tampered").exists()


def test_missing_observation_is_rejected_without_partial_scoring(tmp_path: Path) -> None:
    request = validated_evaluation_request("missing-observation")
    assert request.observations is not None
    request.observations.retrieval.pop()

    with pytest.raises(EvaluationError) as exc_info:
        EvaluationService(output_dir=tmp_path).run(request)

    assert exc_info.value.code.value == "observation_mismatch"
    assert not (tmp_path / "missing-observation").exists()


def test_zero_formula_denominators_produce_partial_not_zero_scores(
    tmp_path: Path,
) -> None:
    request = validated_evaluation_request("zero-denominator")
    assert request.observations is not None
    request.observations.retrieval[0].retrieved = False
    request.observations.errors[0].auto_repair_executed = False
    request.observations.errors[0].repaired_value = None

    result = EvaluationService(output_dir=tmp_path).run(request)

    assert result.evaluation_status.value == "PARTIALLY_EVALUATED"
    assert result.metrics.retrieval_precision.value is None
    assert result.metrics.retrieval_f1.value is None
    assert result.metrics.repair_accuracy.value is None
    assert result.metrics.sdti.value is None
    assert result.safety.publish_allowed is False


def test_evaluation_id_cannot_overwrite_existing_artifacts(tmp_path: Path) -> None:
    service = EvaluationService(output_dir=tmp_path)
    service.run(EvaluationRequest(evaluation_id="same-id"))

    with pytest.raises(EvaluationError) as exc_info:
        service.run(EvaluationRequest(evaluation_id="same-id"))

    assert exc_info.value.code.value == "duplicate_evaluation"


def test_faithfulness_and_fake_source_redlines_fail_the_safety_gate(
    tmp_path: Path,
) -> None:
    request = validated_evaluation_request("redline-fixture")
    assert request.observations is not None
    assert request.source_validation is not None
    request.observations.fields[0].canonical_value = "Positive"
    request.source_validation.checked_source_count = 50
    request.source_validation.fake_source_count = 1

    result = EvaluationService(output_dir=tmp_path).run(request)

    assert result.metrics.faithfulness.value == 0.0
    assert result.safety.gate.value == "FAIL"
    assert result.safety.publish_allowed is False
    assert "Faithfulness < 90%" in result.safety.redlines
    assert "虚假来源率 > 1%" in result.safety.redlines


def test_missing_evidence_blocks_publication_even_above_other_metrics(
    tmp_path: Path,
) -> None:
    request = validated_evaluation_request("missing-evidence-fixture")
    assert request.observations is not None
    request.observations.fields[0].evidence_complete_valid = False

    result = EvaluationService(output_dir=tmp_path).run(request)

    assert result.metrics.faithfulness.value == 1.0
    assert result.metrics.traceability.value == 0.0
    assert result.safety.gate.value == "REVIEW"
    assert result.safety.publish_allowed is False
    assert any("Evidence" in item for item in result.safety.publication_blockers)


def test_runtime_quality_reviews_block_publication(tmp_path: Path) -> None:
    request = validated_evaluation_request("runtime-review-fixture")
    request.runtime_quality_review_count = 2

    result = EvaluationService(output_dir=tmp_path).run(request)

    assert result.safety.gate.value == "REVIEW"
    assert result.safety.publish_allowed is False
    assert any("2 个实时任务" in item for item in result.safety.publication_blockers)
