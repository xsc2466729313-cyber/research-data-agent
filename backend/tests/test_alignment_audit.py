from backend.app.agent.alignment_audit import DataAlignmentAuditor
from backend.app.agent.models import DatasetColumn, ModelingDataset
from backend.app.models import SourceItem


def build_dataset(rows: list[dict]) -> ModelingDataset:
    return ModelingDataset(
        name="测试数据集",
        unit_of_analysis="样本",
        columns=[
            DatasetColumn(
                name=name,
                label_zh=name,
                data_type="string",
                role="标识符",
                description="测试字段",
            )
            for name in {"study_id", "patient_id", "sample_id", "source_id"}
        ],
        rows=rows,
        row_count=len(rows),
        patient_count=len({row.get("patient_id") for row in rows if row.get("patient_id")}),
        sample_count=len({row.get("sample_id") for row in rows if row.get("sample_id")}),
    )


def build_source(source_id: str, name: str = "cBioPortal") -> SourceItem:
    return SourceItem(
        source_id=source_id,
        task_id="task-alignment",
        source_name=name,
        source_type="database",
        accession="brca-test",
        url="https://example.org/source",
        status="retrieved",
    )


def test_same_study_and_source_is_reported_as_safe_internal_alignment() -> None:
    report = DataAlignmentAuditor().build(
        build_dataset(
            [
                {"study_id": "study-a", "patient_id": "P1", "sample_id": "S1", "source_id": "source-a"},
                {"study_id": "study-a", "patient_id": "P2", "sample_id": "S2", "source_id": "source-a"},
            ]
        ),
        [build_source("source-a")],
    )

    assert report.status == "同一研究内可对齐"
    assert report.same_study is True
    assert report.same_source is True
    assert report.patient_id_coverage_rate == 1
    assert report.sample_id_coverage_rate == 1
    assert report.cross_source_join_performed is False
    assert report.entity_match_status == "MATCH"
    assert report.sources[0].role == "主数据集来源"


def test_mixed_source_ids_are_not_declared_as_same_patient_cohort() -> None:
    report = DataAlignmentAuditor().build(
        build_dataset(
            [
                {"study_id": "study-a", "patient_id": "P1", "sample_id": "S1", "source_id": "source-a"},
                {"study_id": "study-b", "patient_id": "P1", "sample_id": "S1", "source_id": "source-b"},
            ]
        ),
        [build_source("source-a"), build_source("source-b", "NCBI GEO")],
    )

    assert report.status == "混合边界，不能直接合并"
    assert report.same_study is False
    assert report.same_source is False
    assert report.cross_source_join_status == "未执行跨来源患者合并"
    assert report.entity_match_status == "UNMATCH"
    assert len(report.sources) == 2
    assert all(item.role == "主数据集来源" for item in report.sources)
