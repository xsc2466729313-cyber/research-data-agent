from backend.app.agent.quality_agent import QualityAgent, QualityStatus
from backend.app.repair.models import RepairRecordInput


def _record(**updates):
    value = {
        "study_id": "study-1",
        "disease": "breast cancer",
        "source_id": "source-1",
        "raw_field": "disease",
        "raw_value": "breast cancer",
        "confidence": 0.98,
    }
    value.update(updates)
    return value


def test_quality_agent_ready_when_required_evidence_is_complete():
    report = QualityAgent().review(
        "task-ready",
        [RepairRecordInput(record_id="r1", record=_record())],
    )

    assert report.status is QualityStatus.READY
    assert report.publish_allowed is True
    assert report.provenance_completeness == 1.0
    assert report.summary["blocking_finding_count"] == 0


def test_low_risk_normalization_is_reported_without_blocking():
    report = QualityAgent().review(
        "task-low-risk",
        [RepairRecordInput(record_id="r1", record=_record(gene="pik3ca"))],
    )

    assert report.status is QualityStatus.READY
    assert report.low_risk_findings
    assert report.review_findings == []


def test_high_risk_her2_semantics_require_review():
    report = QualityAgent().review(
        "task-her2",
        [
            RepairRecordInput(
                record_id="r1",
                record=_record(
                    her2_assay="IHC",
                    her2_raw_value="2+",
                    her2_status="Positive",
                ),
            )
        ],
    )

    assert report.status is QualityStatus.REVIEW
    assert report.publish_allowed is False
    assert report.review_findings
    assert any(f.rule_id == "HER2_IHC_2PLUS" for f in report.findings)


def test_missing_provenance_fails_closed():
    report = QualityAgent().review(
        "task-missing-source",
        [RepairRecordInput(record_id="r1", record=_record(source_id=""))],
    )

    assert report.status is QualityStatus.FAIL
    assert report.publish_allowed is False
    assert report.provenance_completeness == 0.0
    assert any(f.rule_id == "MISSING_EVIDENCE" for f in report.findings)


def test_empty_records_are_not_publishable():
    report = QualityAgent().review("task-empty", [])

    assert report.status is QualityStatus.REVIEW
    assert report.publish_allowed is False
    assert report.checked_record_count == 0
