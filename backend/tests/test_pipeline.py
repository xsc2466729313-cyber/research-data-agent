from __future__ import annotations

from backend.app.services.mock_pipeline import MockPipeline


DEMO_QUESTION = "研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应的关系"


def test_mock_pipeline_runs_complete_data_driven_chain() -> None:
    result = MockPipeline().run(DEMO_QUESTION)

    assert result.mode == "mock"
    assert result.research_spec.research_goal == DEMO_QUESTION
    assert result.research_spec.genes == ["ERBB2", "PIK3CA"]
    assert len(result.search_plan.plans) == 3
    assert {item.source_database for item in result.candidate_sources} == {
        "GDC",
        "GEO",
        "cBioPortal",
    }
    assert len(result.canonical_dataset) == 2
    assert len(result.evidence) == 2

    ihc_record = next(
        record for record in result.canonical_dataset if record.her2_assay.value == "IHC"
    )
    assert ihc_record.her2_status.value == "Equivocal"
    assert ihc_record.her2_raw_value == "2+"
    assert ihc_record.response_domain.value == "clinical"


def test_mock_quality_report_never_invents_gold_set_metrics() -> None:
    report = MockPipeline().run(DEMO_QUESTION).quality_report

    assert report.safety_gate.value == "REVIEW"
    assert report.metrics["evaluation_status"] == "NOT_EVALUATED"
    assert all(value is None for value in report.metrics["values"].values())
    assert report.metrics["mock_validation"]["checks"]["source_linkage"] == "PASS"
    assert report.errors == []


def test_every_record_and_evidence_cell_links_to_a_registered_source() -> None:
    result = MockPipeline().run(DEMO_QUESTION)
    source_ids = {source.source_id for source in result.source_items}

    assert source_ids
    assert all(record.source_id in source_ids for record in result.canonical_dataset)
    assert all(cell.source_id in source_ids for cell in result.evidence)
    assert all(cell.raw_field and cell.raw_value is not None for cell in result.evidence)

