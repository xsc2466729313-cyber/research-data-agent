from __future__ import annotations

from copy import deepcopy

from backend.app.models import SafetyGate
from backend.app.repair.models import (
    PolicyAction,
    RecordDisposition,
    RepairErrorType,
    RepairExecutionStatus,
    RepairRequest,
)
from backend.app.repair.service import RepairLoopService


def canonical_record(**updates: object) -> dict[str, object]:
    record: dict[str, object] = {
        "study_id": "TCGA-BRCA",
        "patient_id": "P001",
        "sample_id": "S001",
        "disease": "Breast Cancer",
        "gene": "ERBB2",
        "drug": "Trastuzumab",
        "source_id": "fixture:source-1",
        "raw_field": "drug_name",
        "raw_value": "Trastuzumab",
        "confidence": 1.0,
    }
    record.update(updates)
    return record


def request_for(*records: dict[str, object], task_id: str = "repair-fixture") -> RepairRequest:
    return RepairRequest(
        task_id=task_id,
        records=[
            {"record_id": f"record-{index}", "record": record}
            for index, record in enumerate(records, start=1)
        ],
    )


def test_classifier_detects_exact_aliases_and_duplicate_at_record_grain() -> None:
    record = canonical_record(gene="HER2", drug="Herceptin", raw_value="Herceptin")
    result = RepairLoopService().classify(request_for(record, deepcopy(record)))

    types = [finding.error_type for finding in result.findings]
    assert types.count(RepairErrorType.EXACT_DUPLICATE) == 1
    assert types.count(RepairErrorType.GENE_ALIAS) == 2
    assert types.count(RepairErrorType.DRUG_ALIAS) == 2
    duplicate = next(
        finding
        for finding in result.findings
        if finding.error_type == RepairErrorType.EXACT_DUPLICATE
    )
    assert duplicate.candidate_repair == {
        "operation": "quarantine_duplicates",
        "survivor_record_id": "record-1",
        "duplicate_record_ids": ["record-2"],
    }


def test_safe_alias_repairs_preserve_provenance_and_are_revalidated() -> None:
    original = canonical_record(
        gene="HER2",
        drug="Herceptin",
        raw_field="drug_name",
        raw_value="Herceptin",
    )
    result = RepairLoopService().run(request_for(original))

    repaired = result.publishable_records[0].record
    assert repaired["gene"] == "ERBB2"
    assert repaired["drug"] == "Trastuzumab"
    assert repaired["source_id"] == original["source_id"]
    assert repaired["raw_field"] == "drug_name"
    assert repaired["raw_value"] == "Herceptin"
    assert result.quality_before.passed is False
    assert result.quality_after.passed is True
    assert result.safety_gate == SafetyGate.PASS
    assert all(log.revalidated for log in result.repair_log)
    assert all(log.validation_passed for log in result.repair_log)
    assert all(len(log.audit_sha256) == 64 for log in result.repair_log)
    drug_log = next(
        log for log in result.repair_log if log.error_type == RepairErrorType.DRUG_ALIAS
    )
    assert drug_log.before[0].record["drug"] == "Herceptin"
    assert drug_log.after[0].record["drug"] == "Trastuzumab"
    assert drug_log.changes[0].path == "/record/drug"


def test_casing_normalization_is_allowlisted_but_not_raw_value_rewriting() -> None:
    result = RepairLoopService().run(
        request_for(
            canonical_record(
                gene="pik3ca",
                er_status="positive",
                raw_field="ER_STATUS",
                raw_value="positive",
            )
        )
    )

    repaired = result.publishable_records[0].record
    assert repaired["gene"] == "PIK3CA"
    assert repaired["er_status"] == "Positive"
    assert repaired["raw_value"] == "positive"
    assert {
        decision.policy_rule
        for decision in result.policy_decisions
    } == {"casing_normalization"}


def test_her2_ihc_2plus_positive_stays_unchanged_in_review() -> None:
    result = RepairLoopService().run(
        request_for(
            canonical_record(
                her2_status="Positive",
                her2_assay="IHC",
                her2_raw_value="2+",
                raw_field="HER2_IHC",
                raw_value="2+",
            )
        )
    )

    finding = next(
        finding
        for finding in result.classification.findings
        if finding.error_type == RepairErrorType.HER2_ASSAY_ERROR
    )
    decision = next(
        item for item in result.policy_decisions if item.finding_id == finding.finding_id
    )
    assert finding.candidate_repair["value"] == "Equivocal"
    assert decision.action == PolicyAction.REVIEW
    assert result.record_states[0].record["her2_status"] == "Positive"
    assert result.record_states[0].disposition == RecordDisposition.REVIEW
    assert result.publishable_records == []
    assert result.safety_gate == SafetyGate.REVIEW
    assert result.repair_log[0].execution_status == RepairExecutionStatus.NOT_EXECUTED


def test_safe_alias_is_suppressed_when_same_record_has_high_risk_semantics() -> None:
    result = RepairLoopService().run(
        request_for(
            canonical_record(
                drug="Herceptin",
                her2_status="Positive",
                her2_assay="IHC",
                her2_raw_value="2+",
                raw_field="HER2_IHC",
                raw_value="2+",
            )
        )
    )

    drug_decision = next(
        item
        for item in result.policy_decisions
        if item.error_type == RepairErrorType.DRUG_ALIAS
    )
    assert drug_decision.action == PolicyAction.REVIEW
    assert result.record_states[0].record["drug"] == "Herceptin"
    assert result.summary["automatic_repair_count"] == 0


def test_erbb2_cna_is_never_repaired_into_or_as_ihc_status() -> None:
    result = RepairLoopService().run(
        request_for(
            canonical_record(
                her2_status="Positive",
                raw_field="ERBB2_CNA",
                raw_value="amplification",
            )
        )
    )

    assert RepairErrorType.ERBB2_CNA_NOT_IHC in {
        item.error_type for item in result.classification.findings
    }
    assert result.record_states[0].disposition == RecordDisposition.REVIEW
    assert result.summary["automatic_repair_count"] == 0


def test_missing_provenance_is_blocked_without_synthesizing_source() -> None:
    record = canonical_record()
    del record["source_id"]
    result = RepairLoopService().run(request_for(record))

    finding = next(
        item
        for item in result.classification.findings
        if item.error_type == RepairErrorType.PROVENANCE_MISSING
    )
    decision = next(
        item for item in result.policy_decisions if item.finding_id == finding.finding_id
    )
    assert decision.action == PolicyAction.BLOCK
    assert "source_id" not in result.blocked_records[0].record
    assert result.safety_gate == SafetyGate.FAIL
    assert result.summary["automatic_repair_count"] == 0


def test_patient_sample_conflict_remains_unresolved_for_review() -> None:
    first = canonical_record(source_id="fixture:source-1", patient_id="P001")
    second = canonical_record(source_id="fixture:source-2", patient_id="P002")
    result = RepairLoopService().run(request_for(first, second))

    finding = next(
        item
        for item in result.classification.findings
        if item.error_type == RepairErrorType.PATIENT_SAMPLE_CONFLICT
    )
    assert finding.observed_value["patient_ids"] == ["P001", "P002"]
    assert all(
        state.disposition == RecordDisposition.REVIEW
        for state in result.record_states
    )
    assert result.summary["automatic_repair_count"] == 0


def test_high_authority_conflict_does_not_select_a_winner() -> None:
    request = request_for(
        canonical_record(source_id="fixture:source-1", her2_status="Positive", her2_assay="FISH"),
        canonical_record(source_id="fixture:source-2", her2_status="Negative", her2_assay="FISH"),
    )
    request.records[0].source_authority = "high"
    request.records[1].source_authority = "high"
    result = RepairLoopService().run(request)

    assert RepairErrorType.HIGH_AUTHORITY_CONFLICT in {
        item.error_type for item in result.classification.findings
    }
    assert [state.record["her2_status"] for state in result.record_states] == [
        "Positive",
        "Negative",
    ]
    assert result.publishable_records == []


def test_preclinical_measure_in_clinical_domain_is_review_only() -> None:
    result = RepairLoopService().run(
        request_for(
            canonical_record(
                response_domain="clinical",
                response_type="IC50",
                response="0.4 uM",
                raw_field="IC50",
                raw_value="0.4 uM",
            )
        )
    )

    assert RepairErrorType.CROSS_DOMAIN_RESPONSE in {
        item.error_type for item in result.classification.findings
    }
    assert result.record_states[0].record["response_domain"] == "clinical"
    assert result.record_states[0].disposition == RecordDisposition.REVIEW


def test_exact_duplicate_is_quarantined_non_destructively_and_is_idempotent() -> None:
    record = canonical_record()
    service = RepairLoopService()
    first = service.run(request_for(record, deepcopy(record), task_id="dedup-first"))

    assert len(first.publishable_records) == 1
    assert len(first.quarantined_records) == 1
    assert first.quarantined_records[0].record == record
    duplicate_log = next(
        log
        for log in first.repair_log
        if log.error_type == RepairErrorType.EXACT_DUPLICATE
    )
    assert duplicate_log.changes[0].operation == "quarantine"
    assert duplicate_log.before[1].record == duplicate_log.after[1].record

    second = service.run(
        RepairRequest(task_id="dedup-second", records=first.publishable_records)
    )
    assert second.classification.findings == []
    assert second.repair_log == []
    assert second.summary["automatic_repair_count"] == 0
    assert second.safety_gate == SafetyGate.PASS


def test_gene_drug_schema_swap_is_not_auto_repaired() -> None:
    result = RepairLoopService().run(
        request_for(canonical_record(gene="Trastuzumab"))
    )

    decision = next(
        item
        for item in result.policy_decisions
        if item.error_type == RepairErrorType.SCHEMA_MAPPING_ERROR
    )
    assert decision.action == PolicyAction.REVIEW
    assert result.record_states[0].record["gene"] == "Trastuzumab"


def test_pipeline_does_not_claim_repair_accuracy_without_frozen_gold_truth() -> None:
    result = RepairLoopService().run(request_for(canonical_record(drug="Herceptin")))

    assert result.summary["repair_accuracy_evaluation_status"] == "NOT_EVALUATED"
    assert result.summary["repair_accuracy"] is None
