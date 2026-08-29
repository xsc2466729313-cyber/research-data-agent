from types import SimpleNamespace

from backend.app.evaluation.observe import observe_error, observe_field, project_error_seed


def field(*, raw_field: str, raw_value: str, canonical_field: str):
    return SimpleNamespace(
        case_id="case",
        source_dataset="TCGA-BRCA",
        raw_field=raw_field,
        raw_value=raw_value,
        canonical_field=canonical_field,
    )


def error(*, error_type: str, original_record: str, auto_repair_allowed: bool = False):
    return SimpleNamespace(
        case_id="case",
        error_type=error_type,
        original_record=original_record,
        auto_repair_allowed=auto_repair_allowed,
    )


def test_field_observer_keeps_requested_dimension_and_cna_is_not_ihc():
    gene, _ = observe_field(
        field(raw_field="ERBB2_CNA", raw_value="amplification", canonical_field="gene")
    )
    her2, _ = observe_field(
        field(raw_field="ERBB2_CNA", raw_value="amplification", canonical_field="her2_status")
    )

    assert (gene.canonical_field, gene.canonical_value) == ("gene", "ERBB2")
    assert (her2.canonical_field, her2.canonical_value) == ("her2_status", "Unknown")


def test_field_observer_does_not_match_pr_inside_primary_diagnosis():
    observed, _ = observe_field(
        field(
            raw_field="primary_diagnosis",
            raw_value="Breast Invasive Carcinoma",
            canonical_field="disease",
        )
    )
    assert observed.canonical_value == "breast cancer"


def test_field_observer_supports_reviewed_chinese_biomarker_labels():
    observed, _ = observe_field(
        field(raw_field="ER", raw_value="阳性", canonical_field="er_status")
    )
    assert observed.canonical_value == "Positive"


def test_field_observer_normalizes_response_semantics_not_numeric_values():
    residual, _ = observe_field(
        field(raw_field="response at surgery", raw_value="RD", canonical_field="response")
    )
    auc, _ = observe_field(field(raw_field="AUC", raw_value="0.42", canonical_field="response"))
    assert residual.canonical_value == "residual_disease"
    assert auc.canonical_value == "AUC"


def test_error_projection_preserves_explicitly_empty_provenance():
    projected = project_error_seed({"source_id": "", "raw_field": "", "raw_value": ""})
    assert projected["source_id"] == ""
    assert projected["raw_field"] == ""
    assert projected["raw_value"] == ""


def test_error_observer_blocks_explicitly_empty_raw_value():
    observed, _ = observe_error(
        error(
            error_type="provenance_missing",
            original_record='{"source_id":"source:1","raw_value":""}',
        )
    )
    assert observed.detected is True


def test_error_observer_detects_generic_crosswalk_and_low_confidence_rules():
    crosswalk, _ = observe_error(
        error(
            error_type="patient_sample_conflict",
            original_record='{"left":"study:A","right":"study:B","join":"patient_id"}',
        )
    )
    low_confidence, _ = observe_error(
        error(
            error_type="patient_sample_conflict",
            original_record='{"patient_id":"A","sample_id":"B","match_score":0.4,"decision":"AUTO_MERGE"}',
        )
    )
    assert crosswalk.detected is True
    assert low_confidence.detected is True


def test_error_observer_detects_declared_missing_unit_typo_and_unknown_mapping():
    cases = [
        ("missing", '{"required":"response","response":""}'),
        ("unit", '{"age":"0.52","unit_guess":"years"}'),
        ("typo", '{"stage":"Stge IIA"}'),
        ("schema_mapping_error", '{"er_status":"Negative","raw_value":"NA"}'),
    ]
    assert all(observe_error(error(error_type=kind, original_record=record))[0].detected for kind, record in cases)


def test_error_observer_detects_single_payload_duplicate_marker():
    observed, _ = observe_error(
        error(
            error_type="duplicate",
            original_record='{"patient_id":"P1","sample_id":"S1","rows":2}',
            auto_repair_allowed=True,
        )
    )
    assert observed.detected is True
    assert observed.auto_repair_executed is True
