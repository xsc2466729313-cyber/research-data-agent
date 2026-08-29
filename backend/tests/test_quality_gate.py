from __future__ import annotations

from datetime import datetime, timezone

from backend.app.agent.alignment_audit import DataAlignmentAuditor
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import (
    AgentTaskResult,
    DatasetColumn,
    ModelingDataset,
)
from backend.app.agent.quality_gate import QualityGateBuilder
from backend.app.agent.study_design import StudyDesignBuilder
from backend.app.models import ResearchSpec, SourceItem


def _spec() -> ResearchSpec:
    return ResearchSpec(
        task_id="qg-test",
        research_goal="研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应",
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "mutation", "treatment_response"],
    )


def _source(*, source_id: str = "source-a", url: str = "https://www.cbioportal.org/study") -> SourceItem:
    return SourceItem(
        source_id=source_id,
        task_id="qg-test",
        source_name="cBioPortal",
        source_type="database",
        accession="brca_tcga",
        url=url,
        checksum="sha256:test",
        status="retrieved",
    )


def _result(
    *,
    rows: list[dict] | None = None,
    sources: list[SourceItem] | None = None,
    analysis_ready: bool = False,
    completeness: float | None = None,
    target_match: bool = False,
    coverage: float | None = None,
) -> AgentTaskResult:
    spec = _spec()
    columns = [
        DatasetColumn(name=name, label_zh=name, data_type="string", role="标识符", description="测试")
        for name in ("study_id", "patient_id", "sample_id", "source_id", "disease", "subtype", "pik3ca_mutation", "treatment_response")
    ]
    dataset = ModelingDataset(
        name="测试数据集",
        unit_of_analysis="患者",
        columns=columns,
        rows=rows or [],
        row_count=len(rows or []),
        patient_count=len({row.get("patient_id") for row in (rows or []) if row.get("patient_id")}),
        sample_count=len({row.get("sample_id") for row in (rows or []) if row.get("sample_id")}),
        target_column="treatment_response",
    )
    _empty_dataset, readiness = ResearchDatasetBuilder().empty()
    del _empty_dataset
    readiness = readiness.model_copy(
        update={
            "status": "可支持科研分析" if analysis_ready else "数据不足",
            "analysis_ready": analysis_ready,
            "row_count": dataset.row_count,
            "feature_count": len(dataset.columns),
            "target_column": "treatment_response",
            "target_match": target_match,
            "field_completeness_rate": completeness,
        }
    )
    source_items = sources if sources is not None else []
    design, cohort = StudyDesignBuilder().build(spec, dataset, readiness, [], source_items)
    if coverage is not None:
        design = design.model_copy(update={"variable_coverage_rate": coverage})
        cohort = cohort.model_copy(update={"variable_coverage_rate": coverage})
    alignment = DataAlignmentAuditor().build(dataset, source_items)
    return AgentTaskResult(
        task_id="qg-test",
        status="完成",
        agent_mode="确定性科研规划",
        model_provider="test",
        model_name="test",
        used_qwen=False,
        notice="quality-gate-test",
        research_spec=spec,
        plan=[],
        tool_calls=[],
        candidate_sources=[],
        source_items=source_items,
        modeling_dataset=dataset,
        readiness=readiness,
        study_design=design,
        cohort_construction=cohort,
        data_alignment=alignment,
        summary_zh="quality-gate-test",
        created_at=datetime.now(timezone.utc),
    )


def test_empty_task_is_review_and_does_not_invent_cohort_f1() -> None:
    report = QualityGateBuilder().build(_result())

    assert report.overall == "REVIEW"
    assert report.publish_allowed is False
    assert [layer.gate_id for layer in report.layers] == [
        "source_trust",
        "field_quality",
        "entity_consistency",
        "research_fitness",
    ]
    assert report.cohort_f1 is None
    assert all(layer.decision in {"PASS", "REVIEW", "REJECT"} for layer in report.layers)
    assert "不生成虚假分数" in report.note
    assert "未评测" not in report.note


def test_field_and_fitness_review_copy_does_not_lead_with_zero_match() -> None:
    rows = [
        {
            "study_id": "study-a",
            "patient_id": "P1",
            "sample_id": "S1",
            "source_id": "source-a",
            "disease": "Breast Cancer",
        }
    ]
    result = _result(rows=rows, sources=[_source()], completeness=0.694, target_match=False, coverage=0.777)
    result = result.model_copy(update={
        "readiness": result.readiness.model_copy(update={"target_column": None, "target_match": False, "target_match_rate": 0.0}),
    })
    report = QualityGateBuilder().build(result)
    field_gate = next(layer for layer in report.layers if layer.gate_id == "field_quality")
    fitness = next(layer for layer in report.layers if layer.gate_id == "research_fitness")

    assert field_gate.decision == "REVIEW"
    assert "0.0%" not in field_gate.evidence
    assert "结局匹配=" not in field_gate.evidence
    assert "还没对上" in field_gate.evidence
    assert fitness.decision == "REVIEW"
    assert "未识别" not in fitness.evidence
    assert "还要补结局字段" in fitness.evidence


def test_missing_source_identity_rejects_source_gate() -> None:
    broken = SourceItem.model_construct(
        source_id="",
        task_id="qg-test",
        source_name="unknown",
        source_type="database",
        accession=None,
        url="",
        status="retrieved",
    )
    report = QualityGateBuilder().build(_result(sources=[broken]))
    source_gate = next(layer for layer in report.layers if layer.gate_id == "source_trust")

    assert source_gate.decision == "REJECT"
    assert report.overall == "REJECT"
    assert report.publish_allowed is False


def test_same_study_alignment_can_pass_all_four_gates() -> None:
    rows = [
        {
            "study_id": "study-a",
            "patient_id": "P1",
            "sample_id": "S1",
            "source_id": "source-a",
            "disease": "Breast Cancer",
            "subtype": "HER2-positive",
            "pik3ca_mutation": "1",
            "treatment_response": "pCR",
        }
    ]
    report = QualityGateBuilder().build(
        _result(
            rows=rows,
            sources=[_source()],
            analysis_ready=True,
            completeness=0.92,
            target_match=True,
            coverage=0.9,
        )
    )

    assert {layer.gate_id: layer.decision for layer in report.layers} == {
        "source_trust": "PASS",
        "field_quality": "PASS",
        "entity_consistency": "PASS",
        "research_fitness": "PASS",
    }
    assert report.overall == "PASS"
    assert report.publish_allowed is True
    assert report.variable_coverage == 0.9
    assert report.traceability == 1
    assert report.cohort_f1 is None


def test_cross_source_identity_stays_review_and_is_not_auto_merged() -> None:
    rows = [
        {"study_id": "study-a", "patient_id": "P1", "sample_id": "S1", "source_id": "source-a"},
        {"study_id": "study-b", "patient_id": "P1", "sample_id": "S1", "source_id": "source-b"},
    ]
    sources = [
        _source(source_id="source-a"),
        SourceItem(
            source_id="source-b",
            task_id="qg-test",
            source_name="NCBI GEO",
            source_type="database",
            accession="GSE1",
            url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1",
            checksum="sha256:geo",
            status="retrieved",
        ),
    ]
    report = QualityGateBuilder().build(_result(rows=rows, sources=sources))
    entity_gate = next(layer for layer in report.layers if layer.gate_id == "entity_consistency")

    assert entity_gate.decision == "REVIEW"
    assert report.overall != "PASS"
    assert "UNMATCH" in entity_gate.evidence


def test_fitness_score_above_one_is_scaled_to_unit_interval() -> None:
    class Fitness:
        fitness_score = 85

    class Unified:
        task_adaptive_fitness = Fitness()

    class Report:
        unified_evaluation = Unified()

    class Result:
        competition_report = Report()

    assert QualityGateBuilder._fitness_score(Result()) == 0.85
    Fitness.fitness_score = 0.42
    assert QualityGateBuilder._fitness_score(Result()) == 0.42


def test_pcr_and_her2_fill_can_pass_field_and_fitness_without_inventing_gold_f1() -> None:
    rows = [
        {
            "study_id": "GSE25066",
            "patient_id": f"P{index}",
            "sample_id": f"S{index}",
            "source_id": "geo:GSE25066",
            "disease": "Breast Cancer",
            "subtype": "HER2-positive",
            "her2_status": "2+" if index == 0 else "阳性",
            "pcr": "pCR",
            "treatment_response": "pCR",
            "pik3ca_mutation": "1",
        }
        for index in range(40)
    ]
    source = SourceItem(
        source_id="geo:GSE25066",
        task_id="qg-test",
        source_name="NCBI GEO",
        source_type="database",
        accession="GSE25066",
        url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066",
        checksum="sha256:gse25066",
        status="retrieved",
    )
    result = _result(
        rows=rows,
        sources=[source],
        analysis_ready=True,
        completeness=0.42,
        target_match=True,
        coverage=0.55,
    )
    result = result.model_copy(
        update={
            "modeling_dataset": result.modeling_dataset.model_copy(update={"name": "GSE25066 科研数据集", "target_column": "pcr"}),
            "readiness": result.readiness.model_copy(
                update={"target_column": "pcr", "target_match": True, "target_match_rate": 1.0, "analysis_ready": True}
            ),
        }
    )
    report = QualityGateBuilder().build(result)
    decisions = {layer.gate_id: layer.decision for layer in report.layers}

    assert decisions["field_quality"] == "PASS"
    assert decisions["research_fitness"] == "PASS"
    assert report.cohort_f1 is None
    assert report.cohort_plan_f1 is not None
    assert 0 < report.cohort_plan_f1 <= 1
    assert ResearchDatasetBuilder._receptor_polarity(rows[0]["her2_status"]) == "equivocal"
