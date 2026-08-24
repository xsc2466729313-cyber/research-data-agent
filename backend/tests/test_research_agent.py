from __future__ import annotations

import json
import gzip
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.agent import (
    AgentDatasetExportService,
    AgentExportFormat,
    AgentTaskRequest,
    QwenClient,
    QwenSettings,
    ResearchAgentService,
)
from backend.app.agent.models import DatasetColumn
from backend.app.agent.dataset_builder import ResearchDatasetBuilder
from backend.app.main import app
from backend.app.models import ResearchSpec, SourceItem
from backend.app.sources.cbioportal import CBioPortalAdapter
from backend.app.sources.geo.models import (
    GEOAdapterResult,
    GEOCacheStatus,
    GEOResourceRecord,
    GEOResourceType,
)
from backend.tests.test_cbioportal_adapter import standard_handler


QUESTION = "研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应的关系"


def qwen_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    has_tool_result = any(message.get("role") == "tool" for message in payload["messages"])
    if payload.get("response_format") and not has_tool_result:
        content = json.dumps(
            {
                "research_goal": QUESTION,
                "disease": "Breast Cancer",
                "subtype": "HER2-positive",
                "genes": ["ERBB2", "PIK3CA", "TP53"],
                "variants": [],
                "drugs": [],
                "outcomes": ["treatment_response"],
                "required_data_types": ["clinical", "mutation", "treatment_response"],
                "target_fields": ["patient_id", "sample_id", "response"],
            },
            ensure_ascii=False,
        )
        message = {"role": "assistant", "content": content}
    elif payload.get("tools"):
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-cbio",
                    "type": "function",
                    "function": {
                        "name": "search_cbioportal",
                        "arguments": json.dumps(
                            {
                                "study_id": "brca_metabric",
                                "gene_symbols": ["ERBB2", "PIK3CA", "TP53"],
                                "max_records": 100,
                            }
                        ),
                    },
                }
            ],
        }
    else:
        assert has_tool_result
        message = {
            "role": "assistant",
            "content": json.dumps({"summary": "已获取 METABRIC 患者级临床、突变和拷贝数记录；当前样例记录数较少，需扩大队列并补充治疗响应标签。"}, ensure_ascii=False),
        }
    return httpx.Response(
        200,
        json={"model": "qwen-plus", "choices": [{"message": message}]},
        request=request,
    )


def build_agent(tmp_path: Path) -> ResearchAgentService:
    qwen_http = httpx.Client(transport=httpx.MockTransport(qwen_handler))
    qwen = QwenClient(
        settings=QwenSettings(
            api_key="test-key",
            base_url="https://ws-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            workspace_id="ws-test",
        ),
        client=qwen_http,
    )
    cbio_http = httpx.Client(transport=httpx.MockTransport(standard_handler))
    cbio = CBioPortalAdapter(cache_dir=tmp_path / "cbio", client=cbio_http)
    return ResearchAgentService(qwen_client=qwen, cbioportal_adapter=cbio)


def test_qwen_agent_executes_function_call_and_builds_research_table(tmp_path: Path) -> None:
    result = build_agent(tmp_path).run(
        AgentTaskRequest(
            question=QUESTION,
            use_qwen=True,
            allow_deterministic_fallback=False,
            data_mode="live",
            max_sources=1,
            max_records=100,
        )
    )

    assert result.used_qwen is True
    assert result.agent_mode == "千问科研数据智能体"
    assert result.tool_calls[0].tool_name == "search_cbioportal"
    assert result.tool_calls[0].status == "完成"
    assert result.modeling_dataset.row_count == 1
    names = {column.name for column in result.modeling_dataset.columns}
    assert {"patient_id", "sample_id", "her2_status", "erbb2_cna"}.issubset(names)
    assert "pik3ca_mutation" not in names
    assert result.modeling_dataset.target_column is None
    assert result.readiness.target_match is False
    assert result.readiness.excluded_orphan_record_count == 4
    labels = {column.name: column.label_zh for column in result.modeling_dataset.columns}
    assert labels["her2_status"] == "HER2 状态"
    assert result.readiness.status == "研究结局不匹配"
    assert "METABRIC" in result.summary_zh
    assert result.source_items


def test_hr_positive_her2_negative_pi3k_question_skips_her2_geo_response_cohort() -> None:
    question = "PIK3CA 突变的 HR+/HER2- 乳腺癌患者，使用 PI3K 抑制剂后的响应是否优于野生型？"
    request = AgentTaskRequest(
        question=question,
        use_qwen=False,
        data_mode="live",
        max_sources=5,
        max_records=500,
    )
    service = ResearchAgentService()
    spec = service._enrich_research_spec(
        service._deterministic_spec(question, "task-hr-her2-pi3k"),
        question,
    )
    calls = service._deterministic_tool_calls(spec, request)
    guarded = service._guard_tool_arguments(
        [{"id": "qwen-wrong-geo", "name": "search_geo", "arguments": {"accession": "GSE76360"}}, *calls],
        spec,
        request,
    )

    assert spec.subtype == "HR-positive/HER2-negative"
    assert spec.genes == ["PIK3CA"]
    assert spec.drugs == ["Alpelisib"]
    assert "search_geo" not in {call["name"] for call in guarded}
    cbio_call = next(call for call in guarded if call["name"] == "search_cbioportal")
    assert cbio_call["arguments"]["gene_symbols"] == ["PIK3CA"]
    civic_call = next(call for call in guarded if call["name"] == "search_civic")
    assert civic_call["arguments"]["therapy_name"] == "Alpelisib"


def test_agent_excel_export_contains_chinese_dictionary_and_readiness(tmp_path: Path) -> None:
    result = build_agent(tmp_path).run(
        AgentTaskRequest(
            question=QUESTION,
            use_qwen=True,
            allow_deterministic_fallback=False,
            data_mode="live",
            max_sources=1,
            max_records=100,
        )
    )
    exported = AgentDatasetExportService().export(result, AgentExportFormat.XLSX)
    workbook = load_workbook(BytesIO(exported.content), read_only=True)

    assert workbook.sheetnames == ["科研数据集", "字段字典", "可科研性报告", "数据来源", "研究设计", "队列构建", "比赛报告"]
    assert workbook["科研数据集"]["A1"].value == "study_id"
    assert workbook["字段字典"]["B1"].value == "中文标注"
    assert workbook["字段字典"]["D1"].value == "科研用途"
    assert workbook["可科研性报告"]["A2"].value == "任务编号"
    assert workbook["研究设计"]["A1"].value == "项目"
    assert workbook["队列构建"]["A1"].value == "步骤"
    competition_values = [cell.value for row in workbook["比赛报告"].iter_rows(values_only=False) for cell in row if cell.value]
    assert "科研适用性" in competition_values
    assert "统一评价体系" in competition_values
    assert "模型对比" in competition_values
    assert "横向对比" in competition_values
    assert "分层对比" in competition_values
    assert "RAG流程节点" in competition_values
    assert "RAG库匹配" in competition_values
    assert "知识图谱节点" in competition_values


def test_agent_parquet_export_normalizes_mixed_upstream_types(tmp_path: Path) -> None:
    result = build_agent(tmp_path).run(
        AgentTaskRequest(
            question=QUESTION,
            use_qwen=True,
            allow_deterministic_fallback=False,
            data_mode="live",
            max_sources=1,
            max_records=100,
        )
    )
    if not any(column.name == "stage" for column in result.modeling_dataset.columns):
        result.modeling_dataset.columns.append(
            DatasetColumn(
                name="stage",
                label_zh="肿瘤分期",
                data_type="string",
                role="研究变量",
                source_field="STAGE",
                description="混合上游类型测试",
            )
        )
    result.modeling_dataset.rows.append(dict(result.modeling_dataset.rows[0]))
    result.modeling_dataset.rows[0]["stage"] = 2
    result.modeling_dataset.rows[1]["stage"] = "Stage III"
    result.modeling_dataset.row_count = len(result.modeling_dataset.rows)
    exported = AgentDatasetExportService().export(result, AgentExportFormat.PARQUET)
    table = pq.read_table(pa.BufferReader(exported.content))

    assert table.num_rows == result.modeling_dataset.row_count
    assert table["stage"].type == pa.string()
    assert table["stage"][0].as_py() == "2"


def test_agent_api_plan_only_is_not_mock() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/agent/tasks",
        json={
            "question": QUESTION,
            "use_qwen": False,
            "data_mode": "plan_only",
            "max_sources": 2,
            "max_records": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_mode"] == "确定性科研规划"
    assert payload["used_qwen"] is False
    assert payload["plan"][1]["label"] == "选择真实数据工具"
    assert "Mock" not in payload["notice"]


def test_geo_series_matrix_builds_baseline_response_cohort(tmp_path: Path) -> None:
    matrix = tmp_path / "GSE76360_series_matrix.txt.gz"
    lines = [
        '!Sample_title\t"119_B"\t"119_P"\t"120_B"\t"120_P"',
        '!Sample_geo_accession\t"GSM1"\t"GSM2"\t"GSM3"\t"GSM4"',
        '!Sample_characteristics_ch1\t"subject id: 119"\t"subject id: 119"\t"subject id: 120"\t"subject id: 120"',
        '!Sample_characteristics_ch1\t"patient status: HER2+ Breast Cancer"\t"patient status: HER2+ Breast Cancer"\t"patient status: HER2+ Breast Cancer"\t"patient status: HER2+ Breast Cancer"',
        '!Sample_characteristics_ch1\t"timepoint: baseline"\t"timepoint: post"\t"timepoint: baseline"\t"timepoint: post"',
        '!Sample_characteristics_ch1\t"response at surgery: pCR"\t"response at surgery: pCR"\t"response at surgery: NOR"\t"response at surgery: NOR"',
        '!Sample_characteristics_ch1\t"er status: Pos"\t"er status: Pos"\t"er status: Neg"\t"er status: Neg"',
        '!Sample_characteristics_ch1\t"pr status: Neg"\t"pr status: Neg"\t"pr status: Neg"\t"pr status: Neg"',
        '!series_matrix_table_begin',
    ]
    with gzip.open(matrix, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    source = SourceItem(
        source_id="geo:GSE76360:test",
        task_id="task-geo",
        source_name="NCBI GEO",
        source_type="database",
        accession="GSE76360",
        url="https://ftp.ncbi.nlm.nih.gov/test",
        file_type="series_matrix",
        local_path=str(matrix),
        checksum="sha256:test",
        status="downloaded",
    )
    geo = GEOAdapterResult(
        task_id="task-geo",
        accession="GSE76360",
        portal_url="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360",
        availability=[],
        resources=[
            GEOResourceRecord(
                accession="GSE76360",
                resource_type=GEOResourceType.SERIES_MATRIX,
                file_name=matrix.name,
                download_url=source.url,
                status="downloaded",
                file_size=matrix.stat().st_size,
                source_item=source,
            )
        ],
        source_items=[source],
        cache_hit=GEOCacheStatus(accession_directory=False, resource_directories={}),
        queried_at=datetime.now(timezone.utc),
        notice="test",
    )
    spec = ResearchSpec(
        task_id="task-geo",
        research_goal=QUESTION,
        disease="Breast Cancer",
        subtype="HER2-positive",
        genes=["PIK3CA"],
        outcomes=["treatment_response"],
        required_data_types=["clinical", "treatment_response"],
    )

    built = ResearchDatasetBuilder().build_from_geo(geo, spec)

    assert built is not None
    dataset, readiness = built
    assert dataset.name == "HER2 阳性乳腺癌术前曲妥珠单抗响应队列科研数据集"
    assert dataset.row_count == 2
    assert dataset.patient_count == 2
    assert dataset.target_column == "treatment_response"
    assert dataset.class_distribution == {"病理完全缓解（pCR）": 1, "未达客观缓解": 1}
    assert {row["timepoint"] for row in dataset.rows} == {"基线"}
    assert all(row["raw_characteristics"] for row in dataset.rows)
    assert readiness.target_match is True
    assert readiness.target_missing_rate == 0
    assert readiness.requested_variable_coverage_rate == 0
    assert any("治疗后配对样本" in action for action in readiness.cleaning_actions)
