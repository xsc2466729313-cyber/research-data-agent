from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from backend.app.agent import QwenClient, QwenSessionRegistry, QwenSettings
from backend.app.agent.models import QwenSessionRequest
from backend.app.main import app, get_qwen_session_registry


def qwen_session_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer session-test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "qwen-plus"
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "CONNECTION_OK"}}]},
        request=request,
    )


def build_registry() -> QwenSessionRegistry:
    def factory(settings: QwenSettings) -> QwenClient:
        return QwenClient(
            settings=settings,
            client=httpx.Client(transport=httpx.MockTransport(qwen_session_handler)),
        )

    return QwenSessionRegistry(client_factory=factory)


def session_request() -> QwenSessionRequest:
    return QwenSessionRequest(
        api_key="session-test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        workspace_id="workspace-test",
    )


def test_qwen_session_registry_keeps_secret_out_of_status_and_can_delete() -> None:
    registry = build_registry()
    status = registry.create(session_request())

    assert status.connected is True
    assert status.session_id.startswith("qws_")
    assert status.model == "qwen-plus"
    assert status.secret_persisted_by_application is False
    assert "session-test-key" not in status.model_dump_json()
    assert registry.get(status.session_id) is not None
    assert registry.delete(status.session_id) is True
    assert registry.get(status.session_id) is None


def test_qwen_session_api_returns_only_sanitized_ephemeral_session() -> None:
    registry = build_registry()
    app.dependency_overrides[get_qwen_session_registry] = lambda: registry
    try:
        response = TestClient(app).post(
            "/api/agent/qwen-sessions",
            json={
                "api_key": "session-test-key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
                "workspace_id": "workspace-test",
                "timeout_seconds": 30,
            },
        )
        assert response.status_code == 200
        assert "session-test-key" not in response.text
        payload = response.json()
        assert payload["session_id"].startswith("qws_")
        assert payload["secret_persisted_by_application"] is False

        deleted = TestClient(app).delete(
            f"/api/agent/qwen-sessions/{payload['session_id']}"
        )
        assert deleted.status_code == 204
    finally:
        app.dependency_overrides.pop(get_qwen_session_registry, None)
        registry.close()


def test_public_session_endpoint_rejects_deepseek_provider() -> None:
    response = TestClient(app).post(
        "/api/agent/qwen-sessions",
        json={
            "provider": "deepseek",
            "api_key": "deepseek-test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
    )

    assert response.status_code == 422


def test_agent_task_rejects_unknown_qwen_session() -> None:
    response = TestClient(app).post(
        "/api/agent/tasks",
        json={
            "question": "整理 HER2 阳性乳腺癌科研数据来源",
            "use_qwen": True,
            "allow_deterministic_fallback": False,
            "data_mode": "plan_only",
            "preferred_sources": [],
            "max_sources": 1,
            "max_records": 100,
            "qwen_session_id": "qws_0000000000000000000000000000000000000000",
        },
    )

    assert response.status_code == 401
    assert "不存在或已过期" in response.json()["detail"]


def test_stale_qwen_session_is_ignored_when_fallback_is_allowed() -> None:
    response = TestClient(app).post(
        "/api/agent/tasks",
        json={
            "question": "整理 HER2 阳性乳腺癌科研数据来源",
            "use_qwen": True,
            "allow_deterministic_fallback": True,
            "data_mode": "plan_only",
            "preferred_sources": [],
            "max_sources": 1,
            "max_records": 100,
            "qwen_session_id": "qws_0000000000000000000000000000000000000000",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_qwen"] is False
    assert payload["plan"]
