from __future__ import annotations

from datetime import datetime, timezone

from backend.app.evaluation.goldset import compute_gold_set_checksum
from backend.app.evaluation.models import (
    BenchmarkObservations,
    ErrorGoldCase,
    ErrorObservation,
    EvaluationMode,
    EvaluationRequest,
    FieldGoldCase,
    FieldObservation,
    GoldSetBundle,
    GoldSetManifest,
    RetrievalGoldCase,
    RetrievalObservation,
    SourceValidationSummary,
)


def validated_evaluation_request(
    evaluation_id: str = "fixture-evaluation",
) -> EvaluationRequest:
    manifest = GoldSetManifest(
        gold_set_id="fixture-only-gold",
        version="fixture-v1",
        frozen=True,
        frozen_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_labeler="fixture-labeler-a",
        independent_reviewer="fixture-labeler-b",
        deterministic_rules_verified=True,
        source_references_verified=True,
        high_risk_review_complete=True,
        gold_set_checksum="0" * 64,
    )
    bundle = GoldSetBundle(
        manifest=manifest,
        retrieval_gold=[
            RetrievalGoldCase(
                question_id="q1",
                research_question="fixture question",
                dataset_id="fixture-dataset-relevant",
                label="relevant",
                label_source="test fixture dual review",
                review_status="approved",
            ),
            RetrievalGoldCase(
                question_id="q1",
                research_question="fixture question",
                dataset_id="fixture-dataset-control",
                label="not_relevant",
                label_source="test fixture dual review",
                review_status="approved",
            ),
        ],
        field_gold=[
            FieldGoldCase(
                case_id="field-1",
                source_dataset="fixture-dataset-relevant",
                raw_field="HER2_IHC",
                raw_value="2+",
                canonical_field="her2_status",
                canonical_value="Equivocal",
                allowed_auto_transform=True,
                label_source="test fixture rules and review",
                review_status="approved",
            )
        ],
        error_gold=[
            ErrorGoldCase(
                case_id="error-1",
                error_type="gene_alias",
                original_record='{"gene":"HER2"}',
                expected_detection=True,
                expected_repair='{"gene":"ERBB2"}',
                auto_repair_allowed=True,
                risk_level="low",
                review_status="approved",
            ),
            ErrorGoldCase(
                case_id="error-control",
                error_type="clean_control",
                original_record='{"gene":"ERBB2"}',
                expected_detection=False,
                auto_repair_allowed=False,
                risk_level="low",
                review_status="approved",
            ),
        ],
    )
    checksum = compute_gold_set_checksum(bundle)
    bundle = bundle.model_copy(
        update={
            "manifest": manifest.model_copy(update={"gold_set_checksum": checksum})
        }
    )
    return EvaluationRequest(
        evaluation_id=evaluation_id,
        mode=EvaluationMode.GOLD_SET,
        gold_set=bundle,
        observations=BenchmarkObservations(
            retrieval=[
                RetrievalObservation(
                    question_id="q1",
                    dataset_id="fixture-dataset-relevant",
                    retrieved=True,
                ),
                RetrievalObservation(
                    question_id="q1",
                    dataset_id="fixture-dataset-control",
                    retrieved=False,
                ),
            ],
            fields=[
                FieldObservation(
                    case_id="field-1",
                    canonical_field="her2_status",
                    canonical_value="Equivocal",
                    evidence_complete_valid=True,
                )
            ],
            errors=[
                ErrorObservation(
                    case_id="error-1",
                    detected=True,
                    auto_repair_executed=True,
                    repaired_value='{"gene":"ERBB2"}',
                ),
                ErrorObservation(
                    case_id="error-control",
                    detected=False,
                ),
            ],
        ),
        source_validation=SourceValidationSummary(
            checked_source_count=2,
            fake_source_count=0,
        ),
    )
