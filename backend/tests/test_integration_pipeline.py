from __future__ import annotations

from copy import deepcopy

import pytest

from backend.app.integration import (
    IntegrationError,
    IntegrationErrorCode,
    NormalizationIntegrationPipeline,
)
from backend.app.integration.models import (
    LinkScope,
    LinkStatus,
    NormalizationIntegrationRequest,
    PatientSampleLinkCandidate,
)
from backend.app.models import SourceItem
from backend.app.normalization.models import FieldMapping, RawSourceRecord


def source_item(source_id: str, *, task_id: str = "task_norm_001") -> SourceItem:
    return SourceItem(
        source_id=source_id,
        task_id=task_id,
        source_name="Automated test fixture",
        source_type="test_fixture",
        accession=source_id,
        url="https://example.test/normalization-fixture",
        file_type="json",
        checksum="sha256:test-fixture",
        status="test_fixture",
    )


def standard_mappings() -> list[FieldMapping]:
    specs = [
        ("study", "study", "study_id", "passthrough"),
        ("patient", "patient", "patient_id", "passthrough"),
        ("sample", "sample", "sample_id", "passthrough"),
        ("disease", "disease", "disease", "passthrough"),
        ("ihc", "HER2_IHC", "her2_status", "biomarker"),
        ("fish", "HER2_FISH", "her2_status", "biomarker"),
        ("cna", "ERBB2_CNA", "variant", "biomarker"),
        ("gene", "gene", "gene", "gene"),
        ("drug", "drug", "drug", "drug"),
        ("mutation", "mutation", "mutation_status", "mutation_status"),
        ("domain", "response_domain", "response_domain", "response_domain"),
        ("response_type", "response_type", "response_type", "passthrough"),
        ("response", "response_value", "response", "passthrough"),
    ]
    return [
        FieldMapping(
            mapping_id=mapping_id,
            raw_field=raw_field,
            canonical_field=canonical_field,
            normalizer=normalizer,
        )
        for mapping_id, raw_field, canonical_field, normalizer in specs
    ]


def standard_request() -> NormalizationIntegrationRequest:
    records = [
        RawSourceRecord(
            record_id="raw-a",
            source_id="fixture:source-a",
            source_authority="high",
            fields={
                "study": "STUDY-1",
                "patient": "P001",
                "sample": "S001",
                "disease": "Breast Cancer",
                "HER2_IHC": "2+",
                "ERBB2_CNA": "amplification",
                "gene": "HER-2",
                "drug": "Herceptin",
                "mutation": "mutated",
                "response_domain": "cell line",
                "response_type": "AUC",
                "response_value": 0.42,
            },
        ),
        RawSourceRecord(
            record_id="raw-b",
            source_id="fixture:source-b",
            source_authority="high",
            fields={
                "study": "STUDY-1",
                "patient": "P001",
                "sample": "S001",
                "disease": "Breast Cancer",
                "HER2_FISH": "amplified",
                "gene": "ERBB2",
                "drug": "Trastuzumab",
                "response_domain": "clinical",
                "response_type": "pCR",
                "response_value": "Yes",
            },
        ),
        RawSourceRecord(
            record_id="raw-c",
            source_id="fixture:source-c",
            source_authority="high",
            fields={
                "study": "STUDY-1",
                "patient": "P001",
                "sample": "S001",
                "disease": "Breast Cancer",
                "HER2_IHC": "3+",
            },
        ),
    ]
    return NormalizationIntegrationRequest(
        task_id="task_norm_001",
        source_items=[
            source_item("fixture:source-a"),
            source_item("fixture:source-b"),
            source_item("fixture:source-c"),
        ],
        records=records,
        mappings=standard_mappings(),
    )


def test_pipeline_builds_atomic_canonical_records_and_field_evidence() -> None:
    result = NormalizationIntegrationPipeline().run(standard_request())

    assert result.canonical_records
    assert len(result.evidence) == sum(
        len(record.mapped_fields) for record in result.mapped_records
    )
    evidence_ids = {cell.evidence_id for cell in result.evidence}
    assert len(evidence_ids) == len(result.evidence)
    assert all(cell.raw_field and cell.raw_value is not None for cell in result.evidence)
    auc_evidence = next(
        cell
        for cell in result.evidence
        if cell.raw_field == "response_value" and cell.field == "response"
    )
    assert auc_evidence.raw_value == 0.42
    assert isinstance(auc_evidence.raw_value, float)
    assert all(
        record.canonical_record.raw_field and record.canonical_record.raw_value is not None
        for record in result.mapped_records
    )

    ihc_2plus = next(
        record.canonical_record
        for record in result.mapped_records
        if record.canonical_record.raw_field == "HER2_IHC"
        and record.canonical_record.raw_value == "2+"
    )
    assert ihc_2plus.her2_status.value == "Equivocal"
    assert ihc_2plus.her2_assay.value == "IHC"
    cna = next(
        record.canonical_record
        for record in result.mapped_records
        if record.canonical_record.raw_field == "ERBB2_CNA"
    )
    assert cna.gene == "ERBB2"
    assert cna.variant == "Amplification"
    assert cna.her2_status is None


def test_pipeline_separates_assay_and_response_domains_but_flags_true_conflict() -> None:
    result = NormalizationIntegrationPipeline().run(standard_request())

    assert len(result.merged_records) == 1
    merged = result.merged_records[0]
    ihc_conflict = next(
        conflict
        for conflict in result.conflicts
        if conflict.semantic_key == "her2_status|assay=IHC"
    )
    assert set(ihc_conflict.values) == {"Equivocal", "Positive"}
    assert ihc_conflict.high_authority_conflict is True
    assert ihc_conflict.status.value == "unresolved"
    assert merged.status == "unresolved"

    fish_field = next(
        field
        for field in merged.fields
        if field.semantic_key == "her2_status|assay=FISH"
    )
    assert fish_field.selected_value == "Positive"
    assert fish_field.status == "resolved"
    response_fields = [field for field in merged.fields if field.field == "response"]
    assert {field.dimension for field in response_fields} == {
        "domain=preclinical_cell_line;type=AUC",
        "domain=clinical;type=pCR",
    }
    assert all(field.status == "resolved" for field in response_fields)


def test_low_confidence_candidate_stays_unresolved_and_unmerged() -> None:
    request = minimal_unidentified_request(confidence=0.75)
    result = NormalizationIntegrationPipeline().run(request)

    assert len(result.link_decisions) == 1
    decision = result.link_decisions[0]
    assert decision.status == LinkStatus.UNRESOLVED
    assert decision.auto_merge_allowed is False
    assert len(result.merged_records) == 2


def test_high_confidence_sample_candidate_can_merge_without_contradiction() -> None:
    request = minimal_unidentified_request(confidence=0.95)
    result = NormalizationIntegrationPipeline().run(request)

    assert result.link_decisions[0].status == LinkStatus.LINKED
    assert result.link_decisions[0].auto_merge_allowed is True
    assert len(result.merged_records) == 1


def test_same_patient_different_samples_are_linked_but_not_merged() -> None:
    request = minimal_unidentified_request(confidence=None)
    request.records[0].fields.update({"patient": "P001", "sample": "S001"})
    request.records[1].fields.update({"patient": "P001", "sample": "S002"})
    request.mappings.extend(
        [
            FieldMapping(
                mapping_id="patient",
                raw_field="patient",
                canonical_field="patient_id",
            ),
            FieldMapping(
                mapping_id="sample",
                raw_field="sample",
                canonical_field="sample_id",
            ),
        ]
    )
    result = NormalizationIntegrationPipeline().run(request)

    assert result.link_decisions[0].status == LinkStatus.LINKED_PATIENT_ONLY
    assert result.link_decisions[0].auto_merge_allowed is False
    assert len(result.merged_records) == 2


def test_auc_cannot_be_mapped_to_clinical_response_domain() -> None:
    request = NormalizationIntegrationRequest(
        task_id="task_norm_001",
        source_items=[source_item("fixture:source-a")],
        records=[
            RawSourceRecord(
                record_id="raw-a",
                source_id="fixture:source-a",
                fields={
                    "study": "STUDY-1",
                    "disease": "Breast Cancer",
                    "domain": "clinical",
                    "type": "AUC",
                    "value": "0.4",
                },
            )
        ],
        mappings=[
            FieldMapping(
                mapping_id="study",
                raw_field="study",
                canonical_field="study_id",
            ),
            FieldMapping(
                mapping_id="disease",
                raw_field="disease",
                canonical_field="disease",
            ),
            FieldMapping(
                mapping_id="domain",
                raw_field="domain",
                canonical_field="response_domain",
                normalizer="response_domain",
            ),
            FieldMapping(
                mapping_id="type",
                raw_field="type",
                canonical_field="response_type",
            ),
            FieldMapping(
                mapping_id="response",
                raw_field="value",
                canonical_field="response",
                response_type="AUC",
            ),
        ],
    )
    result = NormalizationIntegrationPipeline().run(request)

    assert any(issue.code == "unsafe_response_domain" for issue in result.mapping_issues)
    assert not any(
        mapped.canonical_record.raw_field == "value"
        for mapped in result.mapped_records
    )


def test_missing_required_context_blocks_record_instead_of_inventing_values() -> None:
    request = NormalizationIntegrationRequest(
        task_id="task_norm_001",
        source_items=[source_item("fixture:source-a")],
        records=[
            RawSourceRecord(
                record_id="raw-a",
                source_id="fixture:source-a",
                fields={"disease": "Breast Cancer", "gene": "ERBB2"},
            )
        ],
        mappings=[
            FieldMapping(
                mapping_id="study",
                raw_field="study",
                canonical_field="study_id",
            ),
            FieldMapping(
                mapping_id="disease",
                raw_field="disease",
                canonical_field="disease",
            ),
            FieldMapping(
                mapping_id="gene",
                raw_field="gene",
                canonical_field="gene",
                normalizer="gene",
            ),
        ],
    )
    result = NormalizationIntegrationPipeline().run(request)

    assert result.blocked_record_ids == ["raw-a"]
    assert result.canonical_records == []
    assert result.evidence == []
    assert any(issue.code == "missing_required_context" for issue in result.mapping_issues)


def test_unregistered_sources_and_duplicate_ids_are_rejected() -> None:
    request = standard_request()
    request.records[0].source_id = "fixture:not-registered"
    with pytest.raises(IntegrationError) as exc_info:
        NormalizationIntegrationPipeline().run(request)
    assert exc_info.value.code == IntegrationErrorCode.UNREGISTERED_SOURCE

    duplicate = standard_request()
    duplicate.records[1].record_id = duplicate.records[0].record_id
    with pytest.raises(IntegrationError) as exc_info:
        NormalizationIntegrationPipeline().run(duplicate)
    assert exc_info.value.code == IntegrationErrorCode.DUPLICATE_ID


def test_source_specific_mappings_only_apply_to_the_declared_source() -> None:
    request = NormalizationIntegrationRequest(
        task_id="task_norm_001",
        source_items=[source_item("fixture:source-a"), source_item("fixture:source-b")],
        records=[
            RawSourceRecord(
                record_id="raw-a",
                source_id="fixture:source-a",
                fields={"study": "S", "disease": "Breast Cancer", "symbol_a": "HER2"},
            ),
            RawSourceRecord(
                record_id="raw-b",
                source_id="fixture:source-b",
                fields={"study": "S", "disease": "Breast Cancer", "symbol_b": "PIK3CA"},
            ),
        ],
        mappings=[
            FieldMapping(mapping_id="study", raw_field="study", canonical_field="study_id"),
            FieldMapping(
                mapping_id="disease",
                raw_field="disease",
                canonical_field="disease",
            ),
            FieldMapping(
                mapping_id="gene-a",
                source_id="fixture:source-a",
                raw_field="symbol_a",
                canonical_field="gene",
                normalizer="gene",
            ),
            FieldMapping(
                mapping_id="gene-b",
                source_id="fixture:source-b",
                raw_field="symbol_b",
                canonical_field="gene",
                normalizer="gene",
            ),
        ],
    )
    result = NormalizationIntegrationPipeline().run(request)

    genes = {
        (mapped.raw_record_id, mapped.canonical_record.gene)
        for mapped in result.mapped_records
        if mapped.canonical_record.gene
    }
    assert genes == {("raw-a", "ERBB2"), ("raw-b", "PIK3CA")}
    assert not any(issue.raw_field in {"symbol_a", "symbol_b"} for issue in result.mapping_issues)


def test_conflicting_values_from_one_high_authority_source_are_not_mislabeled() -> None:
    request = standard_request()
    request.records[2].source_id = "fixture:source-a"
    result = NormalizationIntegrationPipeline().run(request)

    ihc_conflict = next(
        conflict
        for conflict in result.conflicts
        if conflict.semantic_key == "her2_status|assay=IHC"
    )
    assert ihc_conflict.high_authority_conflict is False


def minimal_unidentified_request(
    *, confidence: float | None
) -> NormalizationIntegrationRequest:
    request = NormalizationIntegrationRequest(
        task_id="task_norm_001",
        source_items=[source_item("fixture:source-a"), source_item("fixture:source-b")],
        records=[
            RawSourceRecord(
                record_id="raw-a",
                source_id="fixture:source-a",
                fields={"study": "STUDY-1", "disease": "Breast Cancer", "stage": "II"},
            ),
            RawSourceRecord(
                record_id="raw-b",
                source_id="fixture:source-b",
                fields={"study": "STUDY-1", "disease": "Breast Cancer", "stage": "II"},
            ),
        ],
        mappings=[
            FieldMapping(
                mapping_id="study",
                raw_field="study",
                canonical_field="study_id",
            ),
            FieldMapping(
                mapping_id="disease",
                raw_field="disease",
                canonical_field="disease",
            ),
            FieldMapping(
                mapping_id="stage",
                raw_field="stage",
                canonical_field="stage",
            ),
        ],
    )
    if confidence is not None:
        request.link_candidates.append(
            PatientSampleLinkCandidate(
                left_record_id="raw-a",
                right_record_id="raw-b",
                scope=LinkScope.SAMPLE,
                confidence=confidence,
                basis="test-only deterministic candidate",
            )
        )
    return request
