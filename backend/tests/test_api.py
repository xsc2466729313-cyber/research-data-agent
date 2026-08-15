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
        "mode": "qwen-agent+function-calling+live-adapters+research-dataset+traceability+quality-gate",
        "version": "2.0.0-qwen-agent",
    }


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
    assert "规划与真实工具调用" in response.text
    assert "科研数据集" in response.text
    assert "可科研性检查" in response.text
    assert "研究结局分布" in response.text
    assert "科研建模数据集" not in response.text
    assert "中文字段字典" in response.text
    assert "数据溯源" in response.text
    assert "科研问题 → 多源检索 → 主科研数据集" in response.text
    assert "仅主路径" in response.text
    assert "暂停动画" in response.text
    assert "含原始信息" in response.text
    assert "标准化中文值" in response.text
    assert "API · 开发者入口" in response.text
    assert "发送 API 请求" in response.text
    assert "复制 cURL" in response.text
    assert "本次实际清洗动作" in response.text
    assert "系统评测指标" in response.text
    assert "下载 CSV" in response.text
    assert "下载 Parquet" in response.text
    assert "下载 Excel" in response.text

    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'fetch("/api/agent/tasks"' in script
    assert 'fetch("/api/agent/configuration"' in script
    assert "/export/${format}" in script
    assert "renderDataset" in script
    assert "renderReadiness" in script
    assert "renderDictionary" in script
    assert "结局完整率" in script
    assert "来源可追溯率" in script
    assert "全表字段完整率" in script
    assert "请求变量覆盖率" in script
    assert "renderLineage" in script
    assert "updateLineageInteraction" in script
    assert "renderRawCharacteristics" in script
    assert "openRawCharacteristicsDialog" in script
    assert "sendApiConsoleRequest" in script
    assert "buildCurlCommand" in script
    assert "validateApiPath" in script
    assert "data-source-db" in script
    assert "TYPE_TRANSLATIONS" in script

    styles = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 760px)" in styles
    assert "prefers-reduced-motion" in styles
    assert "@keyframes lineage-flow" in styles
    assert ".raw-characteristics" in styles

    nginx_config = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "location = /health" in nginx_config
    assert "proxy_pass http://backend:8000/health;" in nginx_config
    assert "proxy_read_timeout 300s;" in nginx_config
    assert 'Cache-Control "no-store, no-cache, must-revalidate"' in nginx_config

    qwen_bootstrap = (ROOT / "scripts" / "docker_up_qwen.ps1").read_text(encoding="utf-8")
    assert "$valueColumns" in qwen_bootstrap
    assert "6298992" not in qwen_bootstrap
    assert "DASHSCOPE_API_KEY" in qwen_bootstrap


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
