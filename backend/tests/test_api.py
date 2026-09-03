from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.main import app, get_gdc_adapter
from backend.app.sources.gdc import GDCAdapter
from backend.tests.test_gdc_adapter import (
    adapter_request,
    files_response,
    project_response,
    response_json,
)


client = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


def test_health_reports_qwen_agent_capabilities() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "qwen-agent+function-calling+live-adapters+research-dataset+traceability+quality-gate+v3-mainline",
        "version": "2.0.0-qwen-agent",
    }


def test_agent_architecture_endpoint_exposes_boundaries_and_parallel_policy() -> None:
    response = client.get("/api/agent/architecture")

    assert response.status_code == 200
    payload = response.json()
    assert payload["architecture_type"] == "bounded_hybrid_multi_agent_orchestration"
    assert {role["id"] for role in payload["roles"]} >= {
        "task_agent",
        "planning_agents",
        "collection_agent",
        "critic_agent",
        "quality_gate",
        "closed_loop",
    }
    assert payload["parallel_policy"]["current_runtime"] == "controlled_serial_tool_execution_with_explicit_parallel_tool_intent"
    assert payload["independent_validation"]
    assert payload["when_not_to_use_multi_agent"]


def test_mock_task_api_returns_business_values_not_only_http_200() -> None:
    response = client.post(
        "/api/tasks/mock",
        json={
            "question": "研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应的关系"
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["research_spec"]["genes"] == ["ERBB2", "PIK3CA"]
    assert payload["canonical_dataset"][1]["her2_status"] == "Equivocal"
    assert payload["canonical_dataset"][1]["her2_raw_value"] == "2+"
    assert payload["evidence"][1]["raw_field"] == "HER2_IHC"
    assert payload["quality_report"]["metrics"]["evaluation_status"] == "NOT_EVALUATED"
    assert payload["quality_report"]["metrics"]["values"]["sdti"] is None


def test_mock_task_rejects_questions_outside_the_reviewable_asset_pack() -> None:
    response = client.post(
        "/api/tasks/mock",
        json={"question": "研究肺癌中 EGFR 突变与总生存期的关系"},
    )

    assert response.status_code == 422
    assert "仅提供预置" in response.json()["detail"]


def test_frontend_smoke_contains_qwen_agent_chinese_research_dataset_views() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "千问驱动" in response.text
    assert "输入你真正想研究的问题" in response.text
    assert "规划与真实检索入口" in response.text
    assert "科研数据集" in response.text
    assert "可科研性检查" in response.text
    assert "研究结局分布" in response.text
    assert "科研建模数据集" not in response.text
    assert "中文字段字典" in response.text
    assert "数据溯源" in response.text
    assert "科研问题 → 多源检索 → 主科研数据集" in response.text
    assert "仅主路径" in response.text
    assert "暂停动画" in response.text
    assert "本题关键字段" in response.text
    assert "全部字段" in response.text
    assert "scientific-usability" in response.text
    assert "变量分级" in response.text or "research-brief" in response.text
    assert "价值判断" in response.text or "value-assessment" in response.text
    assert "标准化中文值" in response.text
    assert "连接千问 API" in response.text
    assert "从百炼凭据 CSV 导入" in response.text
    assert "测试连接并启用" in response.text
    assert "最长 2 小时" in response.text
    assert "技术审计与后续建议" in response.text
    assert "本次实际清洗动作" not in response.text
    assert "模型评测报告集合" not in response.text
    assert 'href="#system-evaluation"' not in response.text
    assert "公开数据实测" not in response.text
    assert "DeepSeek 替换组" not in response.text
    assert "正式 SDTI：NOT_EVALUATED" not in response.text
    assert "evaluation-dashboard" not in response.text
    assert "评测结果与可信度趋势" not in response.text
    assert "团队压缩包对照探针" not in response.text
    assert "团队对照探针" not in response.text
    assert "AI proxy" not in response.text
    assert "DeepSeek Judge" not in response.text
    assert "下载 CSV" in response.text
    assert "下载质量报告" in response.text
    assert "下载 Excel" in response.text
    assert "下载 JSON" not in response.text
    assert "下载 Metadata" not in response.text
    assert "下载 Parquet" not in response.text
    assert "四层质量门" in response.text
    assert "有边界的混合式多智能体协作" in response.text
    assert "上下文隔离" in response.text
    assert "独立校验" in response.text
    assert 'src="/agent-workflow-cn.svg"' in response.text
    assert "什么是智能体" in response.text
    assert "任务总负责人智能体" in response.text
    assert "研究规划智能体" in response.text
    assert "资料查找智能体" in response.text
    assert "独立质疑智能体" in response.text
    assert "固定规则模块" in response.text
    assert "先明确研究需要什么数据" in response.text
    assert "每一步筛选都能解释清楚" in response.text
    assert "模型评价中心" not in response.text
    assert "数据统一与身份对齐" in response.text
    assert "患者编号能不能安全对上" in response.text
    assert "统一评价与科研适用性" not in response.text
    assert "模型、横向结果与分层结果" not in response.text
    assert "study-design" in response.text
    assert "cohort-construction" in response.text
    assert "模型评价中心" not in response.text.split('<main id="main-content">', 1)[1]
    assert "比赛对齐" not in response.text
    assert "API · 开发者入口" not in response.text
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'fetchApi("/api/research/task"' in script
    assert 'fetchApi("/api/agent/tasks"' in script
    assert "isUnimplementedApi" in script
    assert "pinnedApiOrigin" in script
    assert "pinPreferredApiOrigin" in script
    assert "originHasResearchTask" in script
    assert "clearStaleQwenSession" in script
    assert "runResearchTaskOnce" in script
    assert "runResearchTask" in script
    assert "/api/task/status/" in script
    assert "/api/agent/tasks/" in script
    assert 'fetchApi("/api/agent/configuration"' in script
    assert "/export/${format}" in script
    assert "renderDataset" in script
    assert "renderReadiness" in script
    assert "renderDictionary" in script
    assert "结局完整率" not in script
    assert "来源审计完整度" in script
    assert "全表字段完整率" not in script
    assert "主字段覆盖" in script
    assert "renderResearchBrief" in script
    assert "brief-keywords" in script
    assert "检索关键词" in script
    assert "renderLineage" in script
    assert "loadPublicBenchmarkSummary" not in script
    assert "public-benchmark-summary.json" not in script
    assert "updateLineageInteraction" in script
    assert "renderRawCharacteristics" in script
    assert "openRawCharacteristicsDialog" in script
    assert "connectQwenSession" in script
    assert "importQwenCredentialCsv" in script
    assert "qwen_session_id" in script
    assert "data-source-db" in script
    assert "TYPE_TRANSLATIONS" in script
    assert "competition_report" in script
    assert "renderScientificUsability" in script
    assert "renderStudyDesign" in script
    assert "renderCohortConstruction" in script
    assert "renderParsedQuestion" in script
    assert "renderQualityGates" in script
    assert "study-design-summary" in script
    assert "cohort-funnel" in script
    assert "cohort-stage-funnel" in script
    assert "association-meter" in script
    assert "scientific-usability-findings" in script
    assert "/api/evaluation/model-tests/generate" not in script
    assert "研究相关性" in script
    assert "患者-样本关联置信度" in script
    assert "modelSessions" not in script
    assert "renderDataAlignment" in script
    assert "data_alignment" in script
    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 760px)" in styles
    assert "prefers-reduced-motion" in styles
    assert "@keyframes lineage-flow" in styles
    assert ".raw-characteristics" in styles
    assert ".competition-panel" in styles
    assert ".rag-flow-visual" in styles
    assert ".rag-matching" in styles
    assert ".kg-visual" in styles
    assert ".scientific-usability" in styles
    assert ".evaluation-flow-visual" in styles
    assert ".model-comparison-visual" in styles
    assert ".stratified-visual" in styles
    assert ".model-bar-chart" in styles
    assert ".evaluation-workbench" not in styles
    assert ".pico-grid" in styles
    assert ".quality-gate-panel" in styles
    assert ".cohort-stage-funnel" in styles

    nginx_config = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "location = /health" in nginx_config
    assert "proxy_pass http://backend:8000/health;" in nginx_config
    assert "proxy_read_timeout 300s;" in nginx_config
    assert 'Cache-Control "no-store, no-cache, must-revalidate"' in nginx_config

    qwen_bootstrap = (ROOT / "scripts" / "docker_up_qwen.ps1").read_text(encoding="utf-8")
    assert "$valueColumns" in qwen_bootstrap
    assert "默认业务空间-apiKey-" not in qwen_bootstrap
    assert "DASHSCOPE_API_KEY" in qwen_bootstrap


def test_frontend_guided_planner_is_primary_and_wires_real_planning_apis() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="planning-workspace"' in response.text
    assert 'id="planner-form"' in response.text
    assert "告诉我你想研究的方向" in response.text
    assert "哪些因素会影响乳腺癌新辅助治疗的疗效？" in response.text
    assert "哪些生物标志物可以预测乳腺癌患者的治疗效果？" in response.text
    assert "公开数据中有哪些乳腺癌队列适合开展疗效预测研究？" not in response.text
    assert "研究依据" in response.text
    assert "研究方案" in response.text
    assert "数据准备" in response.text
    assert "开始完整规划" in response.text

    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'fetchApi("/api/research/topics"' in script
    assert "/literature-scan" in script
    assert "/question-candidates" in script
    assert "/api/research/questions/" in script
    assert "/source-plan" in script
    assert "renderPlannerEvidence" in script
    assert "renderPlannerContract" in script
    assert "renderPlannerSources" in script
    assert "renderPlannerFlowSummary" in script
    assert "runPlannerDatasetBuild" in script
    assert "系统会自动采用证据最充分的一项" in script
    assert "系统未生成替代性虚假结果" in script


def test_gdc_adapter_api_returns_registered_official_sources(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/projects":
            return response_json(request, project_response())
        if request.url.path == "/files":
            return response_json(request, files_response())
        raise AssertionError(f"Unexpected request: {request.url}")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GDCAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_gdc_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/gdc",
            json=adapter_request().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_gdc_adapter, None)
        transport_client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "gdc"
    assert payload["project"]["project_id"] == "TCGA-BRCA"
    assert payload["source_items"][0]["accession"] == "TCGA-BRCA"
    assert payload["source_items"][0]["status"] == "discovered"
    assert payload["source_items"][0]["url"].startswith(
        "https://api.gdc.cancer.gov/data/"
    )


def test_gdc_adapter_api_exposes_structured_failure_code(tmp_path: Path) -> None:
    request_payload = adapter_request()
    request_payload.search_plan.plans[0].source = "GEO"

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid plan must not call GDC")

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GDCAdapter(cache_dir=tmp_path, client=transport_client)
    app.dependency_overrides[get_gdc_adapter] = lambda: adapter
    try:
        response = client.post(
            "/api/adapters/gdc",
            json=request_payload.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.pop(get_gdc_adapter, None)
        transport_client.close()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_plan"
    assert detail["retryable"] is False


def test_agent_task_api_exposes_competition_alignment_report(tmp_path: Path) -> None:
    from backend.app.agent.models import AgentTaskRequest
    from backend.tests.test_research_agent import build_agent

    result = build_agent(tmp_path).run(
        AgentTaskRequest(
            question="研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系",
            use_qwen=True,
            allow_deterministic_fallback=False,
            data_mode="live",
            max_sources=1,
            max_records=100,
        )
    )

    assert result.competition_report is not None
    assert result.competition_report.direction == "方向1A · 科学数据查找解析与整合"
    assert result.competition_report.unified_evaluation is not None
    unified = result.competition_report.unified_evaluation
    assert unified.version == "v2"
    assert unified.model_comparison == []
    assert unified.status == "未运行横向评价；当前仅有任务级诊断"
    assert any(table.table_id == "task_fitness_by_variant" for table in unified.horizontal_comparisons)
    assert any(row.stratum_name == "response_domain" for row in unified.stratified_comparisons)
    source_audit = next(metric for metric in result.competition_report.metrics if metric.name == "来源审计完整度")
    assert source_audit.value is not None
    assert source_audit.value < 1
    assert any(metric.name == "请求要素覆盖率" for metric in result.competition_report.metrics)
    assert any(metric.name == "科研探索可用性" for metric in result.competition_report.metrics)
    assert any(row.variant == "去掉千问结构化解析" for row in result.competition_report.ablation_rows)
    assert any(row.variant == "去掉质量门与修正闭环" for row in result.competition_report.ablation_rows)
    assert all(row.diagnostic_score is not None for row in result.competition_report.ablation_rows)
    ours = next(row for row in result.competition_report.variant_scores if row.variant_id == "full")
    assert ours.diagnostic_score is not None
    assert ours.is_primary is True
    assert {row.variant_id for row in result.competition_report.variant_scores} >= {"full", "no_qwen", "single_source", "no_repair"}
    assert all(row.diagnostic_score is not None for row in result.competition_report.variant_scores)
    no_qwen = next(row for row in result.competition_report.variant_scores if row.variant_id == "no_qwen")
    single_source = next(row for row in result.competition_report.variant_scores if row.variant_id == "single_source")
    no_repair = next(row for row in result.competition_report.variant_scores if row.variant_id == "no_repair")
    assert no_qwen.status == "已计算"
    assert single_source.status == "已计算"
    assert no_repair.status == "已计算"
    assert result.competition_report.knowledge_graph.enabled is True
    assert result.competition_report.rag_flow_nodes
    assert result.competition_report.rag_flow_edges
    assert result.competition_report.rag_matches
    assert any(item.signals for item in result.competition_report.rag_matches)
    assert result.competition_report.graph_nodes
    assert result.competition_report.graph_edges
    assert result.competition_report.scientific_usability is not None
    assert result.competition_report.scientific_usability.title == "科研适用性初步分析"
    assert "消融" in result.competition_report.summary or result.competition_report.summary


def test_removed_model_evaluation_api_is_not_exposed() -> None:
    response = client.post("/api/evaluation/model-tests/generate", json={})
    page = client.get("/model-evaluation.html")
    openapi = client.get("/openapi.json").json()

    assert response.status_code == 405  # Static mount receives the unknown POST route.
    assert page.status_code == 404
    assert not any(path.startswith("/api/evaluation/model-tests") for path in openapi["paths"])


def test_latest_agent_task_endpoint_does_not_invent_scores() -> None:
    response = client.get("/api/agent/tasks/latest")

    if response.status_code == 404:
        assert "还没有已完成的科研任务" in response.json()["detail"]
        return
    assert response.status_code == 200
    payload = response.json()
    report = payload.get("competition_report") or {}
    scores = report.get("variant_scores") or []
    assert {row["variant_id"] for row in scores} >= {"full", "no_qwen", "single_source", "no_repair"}
    assert all(row.get("diagnostic_score") is not None for row in scores)


def test_api_check_endpoint_does_not_accept_insecure_endpoint() -> None:
    response = client.post(
        "/api/agent/api-check",
        json={
            "api_key": "rotated-test-key",
            "base_url": "http://not-https.example",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "连接失败"
    assert payload["reachable"] is False
    assert "rotated-test-key" not in response.text
