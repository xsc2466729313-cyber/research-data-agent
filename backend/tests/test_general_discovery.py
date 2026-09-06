from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.agent.models import AgentTaskRequest
from backend.app.agent.search_planner import FieldDrivenSearchPlanner
from backend.app.agent.service import ResearchAgentService
from backend.app.models import ResearchSpec, SourceItem
from backend.app.sources.discovery.models import ZenodoDatasetRecord


def test_unknown_topic_uses_general_science_discovery_plan() -> None:
    question = "analyze dinosaur fossil datasets and find downloadable data"
    spec = ResearchAgentService._deterministic_spec(question, "task-general")
    calls = FieldDrivenSearchPlanner().plan(
        spec,
        AgentTaskRequest(question=question, use_qwen=False, data_mode="plan_only"),
    )

    assert spec.domain == "general_science"
    assert spec.disease == "General Science"
    assert [call["name"] for call in calls[:2]] == ["search_zenodo", "search_europe_pmc"]


def test_zenodo_records_become_traceable_non_patient_dataset() -> None:
    spec = ResearchSpec(
        task_id="task-general",
        research_goal="analyze dinosaur fossil datasets",
        disease="General Science",
        domain="general_science",
        required_data_types=["publication", "evidence"],
        target_fields=["dataset_id", "title", "source_id"],
    )
    source = SourceItem(
        source_id="zenodo:123",
        task_id=spec.task_id,
        source_name="Zenodo",
        source_type="discovery",
        accession="10.5281/zenodo.123",
        url="https://zenodo.org/records/123",
        file_type="json",
        checksum="abc",
        status="retrieved",
    )
    record = ZenodoDatasetRecord(
        record_id="123",
        title="Dinosaur observations",
        description="Public observation table",
        doi="10.5281/zenodo.123",
        keywords=["dinosaur"],
        file_count=1,
        file_formats=["csv"],
        files=[{"key": "observations.csv", "download_url": "https://zenodo.org/api/files/observations.csv"}],
        url=source.url,
        raw_record={"id": 123},
        source_item=source,
    )

    dataset, readiness = ResearchDatasetBuilder().build_from_zenodo([record], spec)

    assert dataset.unit_of_analysis == "公开数据集记录"
    assert dataset.row_count == 1
    assert dataset.patient_count == 0
    assert dataset.rows[0]["source_id"] == "zenodo:123"
    assert dataset.rows[0]["file_names"] == "observations.csv"
    assert dataset.rows[0]["first_file_url"].endswith("observations.csv")
    assert readiness.analysis_ready is False
    assert readiness.status == "可继续解析"
