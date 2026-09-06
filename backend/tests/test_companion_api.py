from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.main import app, get_qwen_session_registry, get_research_agent_service


class FakeCompanionClient:
    def __init__(self):
        self.messages = None

    def chat(self, *, messages):
        self.messages = messages
        return {"content": "这是模型根据上下文生成的动态回答。"}


def test_companion_endpoint_uses_configured_model_and_context() -> None:
    client_model = FakeCompanionClient()
    service = SimpleNamespace(
        qwen=client_model,
        configuration=lambda: SimpleNamespace(configured=True),
    )
    app.dependency_overrides[get_research_agent_service] = lambda: service
    app.dependency_overrides[get_qwen_session_registry] = lambda: SimpleNamespace(get=lambda _session_id: None)
    try:
        response = TestClient(app).post(
            "/api/agent/companion/chat",
            json={
                "message": "解释这个数据集",
                "history": [{"role": "user", "content": "我想研究 Ia 型超新星"}],
                "context": {
                    "question": "我想研究 Ia 型超新星光变曲线",
                    "dataset_size": "128 行 × 9 列",
                    "result": {"source_items": [{"source_id": "zenodo:1"}]},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["reply"] == "这是模型根据上下文生成的动态回答。"
    assert "Ia 型超新星光变曲线" in client_model.messages[0]["content"]
    assert client_model.messages[-1]["content"] == "解释这个数据集"


def test_companion_endpoint_is_explicit_when_no_model_is_configured() -> None:
    service = SimpleNamespace(
        qwen=SimpleNamespace(),
        configuration=lambda: SimpleNamespace(configured=False),
    )
    app.dependency_overrides[get_research_agent_service] = lambda: service
    app.dependency_overrides[get_qwen_session_registry] = lambda: SimpleNamespace(get=lambda _session_id: None)
    try:
        response = TestClient(app).post("/api/agent/companion/chat", json={"message": "你好"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "未连接科研模型" in response.json()["detail"]


def test_companion_research_question_endpoint_formats_context_with_model() -> None:
    client_model = FakeCompanionClient()
    service = SimpleNamespace(
        qwen=client_model,
        configuration=lambda: SimpleNamespace(configured=True),
    )
    app.dependency_overrides[get_research_agent_service] = lambda: service
    app.dependency_overrides[get_qwen_session_registry] = lambda: SimpleNamespace(get=lambda _session_id: None)
    try:
        response = TestClient(app).post(
            "/api/agent/companion/research-question",
            json={
                "message": "把这段聊天整理成研究问题",
                "history": [{"role": "user", "content": "我想找一份可以下载的鸟类迁徙数据"}],
                "context": {
                    "question": "鸟类迁徙数据的季节性变化",
                    "result": {"source_items": [{"source_id": "zenodo:1"}]},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["research_question"] == "这是模型根据上下文生成的动态回答。"
    assert response.json()["question"] == response.json()["research_question"]
    assert "鸟类迁徙数据的季节性变化" in client_model.messages[0]["content"]
    assert "zenodo:1" in client_model.messages[0]["content"]


def test_companion_research_question_endpoint_has_transparent_no_model_fallback() -> None:
    service = SimpleNamespace(
        qwen=SimpleNamespace(),
        configuration=lambda: SimpleNamespace(configured=False),
    )
    app.dependency_overrides[get_research_agent_service] = lambda: service
    app.dependency_overrides[get_qwen_session_registry] = lambda: SimpleNamespace(get=lambda _session_id: None)
    try:
        response = TestClient(app).post(
            "/api/agent/companion/research-question",
            json={
                "message": "请整理这段聊天",
                "history": [{"role": "user", "content": "我想研究鸟类迁徙"}],
                "context": {"status": "尚未运行"},
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["used_model"] is False
    assert payload["model_mode"] == "deterministic"
    assert "鸟类迁徙" in payload["research_question"]
    assert "分析边界" in payload["research_question"]
