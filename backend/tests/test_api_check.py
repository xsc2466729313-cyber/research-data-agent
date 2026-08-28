from __future__ import annotations

import httpx

from backend.app.agent import ApiCheckRequest, ApiCheckService, QwenClient, QwenSettings


def test_api_check_keeps_key_out_of_result() -> None:
    secret = "rotated-test-key"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {secret}"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "CONNECTION_OK"}}]},
            request=request,
        )

    def factory(settings: QwenSettings) -> QwenClient:
        return QwenClient(
            settings=settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    result = ApiCheckService(client_factory=factory).check(
        ApiCheckRequest(
            api_key=secret,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            run_agent_probe=False,
        )
    )

    assert result.reachable is True
    assert result.authenticated is True
    assert result.agent_ready is False
    assert secret not in result.model_dump_json()


def test_api_check_reports_invalid_endpoint_without_opening_a_client() -> None:
    called = False

    def factory(settings: QwenSettings) -> QwenClient:
        nonlocal called
        called = True
        raise AssertionError("invalid endpoint must be rejected before client creation")

    result = ApiCheckService(client_factory=factory).check(
        ApiCheckRequest(api_key="rotated-test-key", base_url="http://not-https.example")
    )

    assert result.status == "连接失败"
    assert result.reachable is False
    assert called is False
