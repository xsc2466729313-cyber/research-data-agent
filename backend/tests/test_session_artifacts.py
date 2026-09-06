from io import BytesIO
import csv
import json
from zipfile import ZipFile

from fastapi.testclient import TestClient

from backend.app.agent import AgentTaskRequest, ClosedLoopRequest, ClosedLoopService, ResearchAgentService
from backend.app.agent.loop_store import LoopStateStore
from backend.app.agent.models import DatasetColumn
from backend.app.main import app, get_closed_loop_service, get_research_agent_service
from backend.tests.test_closed_loop import _base_result


def test_persisted_conversations_restore_exact_task_and_export_separate_sources(tmp_path):
    base = _base_result()
    store = LoopStateStore(tmp_path / "loops.sqlite3")

    def runner(request, *, task_id, **kwargs):
        record = {
            "source_id": request.question, "raw_field": "response", "raw_value": "IC50",
            "response_domain": "preclinical_cell_line",
        }
        dataset = base.modeling_dataset.model_copy(update={
            "name": request.question, "study_key": request.question,
            "dataset_role": "supporting", "rows": [record], "row_count": 1,
            "columns": [DatasetColumn(name=name, label_zh=name, data_type="string", role="metadata", description="test fixture") for name in record],
        })
        return base.model_copy(update={"task_id": task_id, "source_datasets": [dataset]})

    loops = ClosedLoopService(object(), runner=runner, store=store)
    saved = [loops.run(ClosedLoopRequest(
        initial_request=AgentTaskRequest(question=f"研究对话 {label}", use_qwen=False, data_mode="plan_only"),
        max_iterations=2, require_two_rounds=False,
    )) for label in ("A", "B")]
    # Empty runtime cache simulates a server restart; only the persisted loops remain.
    restored = ClosedLoopService(object(), store=LoopStateStore(store.path))
    empty_service = ResearchAgentService()
    app.dependency_overrides[get_closed_loop_service] = lambda: restored
    app.dependency_overrides[get_research_agent_service] = lambda: empty_service
    try:
        client = TestClient(app)
        for label, loop in zip(("A", "B"), saved):
            task_id = loop.final_result.task_id
            url = f"/api/agent/tasks/{task_id}"
            fetched = client.get(url)
            assert fetched.status_code == 200
            assert fetched.json()["task_id"] == task_id
            assert fetched.json()["modeling_dataset"]["row_count"] == 0
            assert client.get(f"{url}/export/csv").status_code == 422
            exported = client.get(f"{url}/export/sources")
            assert exported.status_code == 200
            assert exported.headers["content-type"] == "application/zip"
            with ZipFile(BytesIO(exported.content)) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                assert manifest["task_id"] == task_id
                assert manifest["datasets"][0]["name"] == f"研究对话 {label}"
                rows = list(csv.DictReader(archive.read("source-1.csv").decode("utf-8-sig").splitlines()))
                assert rows[0]["source_id"] == f"研究对话 {label}"
                assert rows[0]["response_domain"] == "preclinical_cell_line"
                raw = json.loads(archive.read("source-1.json"))["rows"][0]
                assert raw["raw_field"] == "response"
                assert raw["raw_value"] == "IC50"
                assert json.loads(archive.read("quality-report.json"))["task_id"] == task_id
            assert client.get(f"/api/agent/tasks/{loop.loop_id}:r99/export/sources").status_code == 404
    finally:
        app.dependency_overrides.pop(get_closed_loop_service, None)
        app.dependency_overrides.pop(get_research_agent_service, None)
