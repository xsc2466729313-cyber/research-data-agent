from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.goldset import GoldSetCurationError, GoldSetCurationService
from backend.app.goldset.models import (
    ErrorConstructionRequest,
    ErrorCaseType,
    ErrorSecondReviewRequest,
    ErrorSeed,
    FieldSecondReviewRequest,
    GoldSetRuleValidationRequest,
    RetrievalSecondReviewRequest,
)
from backend.tests.goldset_curation_fixtures import (
    StubSourceVerifier,
    gdc_source,
    retrieval_request,
    safe_field_request,
    unsafe_her2_field_request,
)


def service() -> GoldSetCurationService:
    return GoldSetCurationService(verifier=StubSourceVerifier())


def review_retrieval(curator: GoldSetCurationService):
    draft = curator.initial_label_retrieval(retrieval_request()).drafts[0]
    return curator.review_retrieval(
        RetrievalSecondReviewRequest(
            draft=draft,
            reviewer_model_id="model-b",
            reviewed_label="relevant",
            confidence=0.97,
            rationale="Independent fixture review agrees.",
        )
    )


def review_safe_field(curator: GoldSetCurationService):
    draft = curator.initial_label_fields(safe_field_request()).drafts[0]
    return curator.review_field(
        FieldSecondReviewRequest(
            draft=draft,
            reviewer_model_id="model-b",
            reviewed_canonical_field="gene",
            reviewed_canonical_value="ERBB2",
            preserves_medical_meaning=True,
            confidence=0.98,
            rationale="Independent fixture review confirms exact alias.",
        )
    )


def error_seed() -> ErrorSeed:
    return ErrorSeed(
        record_id="seed-1",
        source=gdc_source(),
        record={
            "study_id": "TCGA-BRCA",
            "patient_id": "P001",
            "sample_id": "S001",
            "disease": "Breast Cancer",
            "gene": "ERBB2",
            "drug": "Trastuzumab",
            "her2_status": "Equivocal",
            "her2_assay": "IHC",
            "her2_raw_value": "2+",
            "source_id": "gdc:TCGA-BRCA",
            "raw_field": "HER2_IHC",
            "raw_value": "2+",
        },
    )


def test_retrieval_dual_review_and_rules_create_approved_gold_proposal() -> None:
    curator = service()
    initial = curator.initial_label_retrieval(retrieval_request())

    assert initial.drafts[0].status.value == "initial_labeled"
    assert initial.drafts[0].source_verification.status.value == "verified"
    assert initial.review_queue == []

    reviewed = review_retrieval(curator)
    result = curator.validate_rules(
        GoldSetRuleValidationRequest(retrieval=[reviewed])
    )

    assert reviewed.agreement is True
    assert result.retrieval_gold[0].review_status.value == "approved"
    assert "primary_model:model-a" in result.retrieval_gold[0].label_source
    assert result.review_queue == []
    assert result.freeze_eligible is False


def test_same_model_cannot_review_its_own_retrieval_label() -> None:
    curator = service()
    draft = curator.initial_label_retrieval(retrieval_request()).drafts[0]

    with pytest.raises(GoldSetCurationError) as exc_info:
        curator.review_retrieval(
            RetrievalSecondReviewRequest(
                draft=draft,
                reviewer_model_id="MODEL-A",
                reviewed_label="relevant",
                confidence=1.0,
                rationale="Not independent.",
            )
        )

    assert exc_info.value.code.value == "invalid_reviewer"


def test_model_disagreement_enters_review_queue_and_stays_pending() -> None:
    curator = service()
    draft = curator.initial_label_retrieval(retrieval_request()).drafts[0]
    reviewed = curator.review_retrieval(
        RetrievalSecondReviewRequest(
            draft=draft,
            reviewer_model_id="model-b",
            reviewed_label="not_relevant",
            confidence=0.99,
            rationale="Independent model disagrees.",
        )
    )

    result = curator.validate_rules(
        GoldSetRuleValidationRequest(retrieval=[reviewed])
    )

    assert reviewed.status.value == "human_review_required"
    assert result.retrieval_gold[0].review_status.value == "pending"
    assert result.review_queue[0].reasons == ["model_disagreement"]


def test_unverified_source_enters_high_priority_review_queue() -> None:
    curator = service()
    request = retrieval_request(source=gdc_source(source_id="unverified:gdc"))

    result = curator.initial_label_retrieval(request)

    assert result.drafts[0].source_verification.status.value == "failed"
    assert result.drafts[0].status.value == "human_review_required"
    assert result.review_queue[0].priority.value == "high"
    assert result.review_queue[0].reasons == ["source_unverified"]


def test_safe_gene_alias_field_passes_dual_review_and_deterministic_rule() -> None:
    curator = service()
    reviewed = review_safe_field(curator)

    result = curator.validate_rules(GoldSetRuleValidationRequest(fields=[reviewed]))

    assert result.field_gold[0].canonical_field == "gene"
    assert result.field_gold[0].canonical_value == "ERBB2"
    assert result.field_gold[0].review_status.value == "approved"
    assert result.review_queue == []


def test_her2_ihc_2plus_positive_is_blocked_and_sent_to_human_review() -> None:
    curator = service()
    draft = curator.initial_label_fields(unsafe_her2_field_request()).drafts[0]
    reviewed = curator.review_field(
        FieldSecondReviewRequest(
            draft=draft,
            reviewer_model_id="model-b",
            reviewed_canonical_field="her2_status",
            reviewed_canonical_value="Positive",
            preserves_medical_meaning=True,
            confidence=0.99,
            rationale="Deliberately unsafe agreement fixture.",
        )
    )

    result = curator.validate_rules(GoldSetRuleValidationRequest(fields=[reviewed]))

    her2_finding = next(
        item for item in result.findings if item.rule_id == "HER2_IHC_2PLUS"
    )
    assert her2_finding.passed is False
    assert result.field_gold[0].review_status.value == "pending"
    assert any(
        "medical_rule:HER2_IHC_2PLUS" in item.reasons
        for item in result.review_queue
    )


def test_error_constructor_builds_clean_controls_and_applicable_mutations() -> None:
    curator = service()
    seed = error_seed()
    original = json.loads(json.dumps(seed.record))

    result = curator.construct_error_cases(ErrorConstructionRequest(seeds=[seed]))

    by_type = {draft.error_type: draft for draft in result.drafts}
    assert "clean_control" in by_type
    assert by_type["clean_control"].expected_detection is False
    assert by_type["duplicate"].auto_repair_allowed is True
    assert by_type["gene_alias"].auto_repair_allowed is True
    assert by_type["her2_assay_error"].risk_level.value == "high"
    assert by_type["her2_assay_error"].auto_repair_allowed is False
    assert by_type["provenance_missing"].risk_level.value == "high"
    assert by_type["patient_sample_conflict"].risk_level.value == "high"
    assert seed.record == original
    assert any("schema_mapping_error" in item for item in result.skipped_mutations)
    assert any(item.priority.value == "high" for item in result.review_queue)


def test_full_low_risk_batch_becomes_freeze_eligible_but_is_not_frozen() -> None:
    curator = service()
    retrieval = review_retrieval(curator)
    field = review_safe_field(curator)
    constructed = curator.construct_error_cases(
        ErrorConstructionRequest(
            seeds=[
                error_seed().model_copy(
                    update={"requested_error_types": [ErrorCaseType.DUPLICATE]}
                )
            ]
        )
    )
    duplicate = next(item for item in constructed.drafts if item.error_type == "duplicate")
    reviewed_error = curator.review_error(
        ErrorSecondReviewRequest(
            draft=duplicate,
            reviewer_model_id="model-b",
            reviewed_error_type=duplicate.error_type,
            reviewed_expected_detection=duplicate.expected_detection,
            reviewed_expected_repair=duplicate.expected_repair,
            reviewed_auto_repair_allowed=duplicate.auto_repair_allowed,
            confidence=0.99,
            rationale="Independent review confirms deterministic duplicate case.",
        )
    )

    result = curator.validate_rules(
        GoldSetRuleValidationRequest(
            retrieval=[retrieval],
            fields=[field],
            errors=[reviewed_error],
        )
    )

    assert result.summary["approved_count"] == 3
    assert result.review_queue == []
    assert result.freeze_eligible is True
    assert "Manifest" in result.notice


def test_error_seed_must_preserve_real_source_id() -> None:
    with pytest.raises(ValidationError):
        ErrorSeed(
            record_id="bad-seed",
            source=gdc_source(),
            record={"source_id": "different-source", "study_id": "TCGA-BRCA"},
            requested_error_types=["duplicate"],
        )


def test_rule_validation_rechecks_source_instead_of_trusting_nested_status() -> None:
    curator = service()
    reviewed = review_retrieval(curator)
    forged_source = gdc_source(source_id="unverified:forged-client-status")
    forged_verification = reviewed.draft.source_verification.model_copy(
        update={"source": forged_source, "status": "verified"}
    )
    forged_draft = reviewed.draft.model_copy(
        update={"source_verification": forged_verification}
    )
    forged_review = reviewed.model_copy(
        update={"draft": forged_draft, "agreement": True}
    )

    result = curator.validate_rules(
        GoldSetRuleValidationRequest(retrieval=[forged_review])
    )

    assert result.retrieval_gold[0].review_status.value == "pending"
    assert result.summary["source_failures"] == 1
    assert result.review_queue[0].reasons == ["source_unverified"]


def test_rule_validation_recomputes_model_agreement() -> None:
    curator = service()
    reviewed = review_retrieval(curator).model_copy(
        update={"reviewed_label": "not_relevant", "agreement": True}
    )

    result = curator.validate_rules(
        GoldSetRuleValidationRequest(retrieval=[reviewed])
    )

    assert result.retrieval_gold[0].review_status.value == "pending"
    assert result.review_queue[0].reasons == ["model_disagreement"]


def test_rule_validation_rejects_tampered_error_construction() -> None:
    curator = service()
    constructed = curator.construct_error_cases(
        ErrorConstructionRequest(
            seeds=[
                error_seed().model_copy(
                    update={"requested_error_types": [ErrorCaseType.DUPLICATE]}
                )
            ]
        )
    )
    duplicate = next(item for item in constructed.drafts if item.error_type == "duplicate")
    tampered = duplicate.model_copy(update={"original_record": '{"records":[]}'})
    reviewed = curator.review_error(
        ErrorSecondReviewRequest(
            draft=tampered,
            reviewer_model_id="model-b",
            reviewed_error_type=tampered.error_type,
            reviewed_expected_detection=tampered.expected_detection,
            reviewed_expected_repair=tampered.expected_repair,
            reviewed_auto_repair_allowed=tampered.auto_repair_allowed,
            confidence=0.99,
            rationale="Fixture review of a tampered construction.",
        )
    )

    result = curator.validate_rules(GoldSetRuleValidationRequest(errors=[reviewed]))

    integrity = next(
        item
        for item in result.findings
        if item.rule_id == "ERROR_CONSTRUCTION_INTEGRITY"
    )
    assert integrity.passed is False
    assert result.error_gold[0].review_status.value == "pending"
    assert "invalid_error_construction" in result.review_queue[0].reasons
