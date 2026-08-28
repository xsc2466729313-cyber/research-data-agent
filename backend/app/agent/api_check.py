from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal

from pydantic import SecretStr

from backend.app.agent.qwen_client import QwenClient, QwenClientError, QwenSettings
from backend.app.models import ApiModel
from pydantic import Field


class ApiCheckRequest(ApiModel):
    provider: Literal["qwen"] = "qwen"
    api_key: SecretStr
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    workspace_id: str | None = None
    timeout_seconds: float = Field(default=30, ge=5, le=120)
    run_agent_probe: bool = False


class ApiCheckResult(ApiModel):
    provider: str
    model: str
    base_url: str
    reachable: bool
    authenticated: bool
    model_available: bool
    function_calling_available: bool
    agent_ready: bool
    status: str
    message: str
    checked_at: datetime


class ApiCheckService:
    """Run a bounded, in-memory provider check without persisting credentials."""

    def __init__(
        self,
        client_factory: Callable[[QwenSettings], QwenClient] | None = None,
    ) -> None:
        self.client_factory = client_factory or (lambda settings: QwenClient(settings=settings))

    def check(self, request: ApiCheckRequest) -> ApiCheckResult:
        settings = QwenSettings(
            api_key=request.api_key.get_secret_value(),
            base_url=request.base_url.rstrip("/"),
            model=request.model,
            workspace_id=request.workspace_id or None,
            timeout_seconds=request.timeout_seconds,
            provider=request.provider,
        )
        checked_at = datetime.now(timezone.utc)
        try:
            settings.validate_base_url()
            client = self.client_factory(settings)
        except QwenClientError as exc:
            return self._failure(request, checked_at, str(exc))

        try:
            client.test_connection()
            agent_ready = False
            message = "网络可达、鉴权成功、模型可用；尚未执行 Agent 探测。"
            if request.run_agent_probe:
                client.extract_research_spec(
                    "请将乳腺癌治疗响应研究问题解析为结构化科研任务。",
                    "api-probe",
                )
                agent_ready = True
                message = "网络可达、鉴权成功、模型可用，结构化 Agent 探测通过。"
            return ApiCheckResult(
                provider=settings.provider_label,
                model=settings.model,
                base_url=settings.base_url,
                reachable=True,
                authenticated=True,
                model_available=True,
                function_calling_available=bool(QwenClient.TOOL_DEFINITIONS),
                agent_ready=agent_ready,
                status="已通过" if agent_ready or not request.run_agent_probe else "已连接",
                message=message,
                checked_at=checked_at,
            )
        except QwenClientError as exc:
            return self._failure(request, checked_at, str(exc), settings=settings)
        finally:
            client.close()

    @staticmethod
    def _failure(
        request: ApiCheckRequest,
        checked_at: datetime,
        message: str,
        *,
        settings: QwenSettings | None = None,
    ) -> ApiCheckResult:
        return ApiCheckResult(
            provider=settings.provider_label if settings else request.provider,
            model=settings.model if settings else request.model,
            base_url=settings.base_url if settings else request.base_url.rstrip("/"),
            reachable=False,
            authenticated=False,
            model_available=False,
            function_calling_available=False,
            agent_ready=False,
            status="连接失败",
            message=message,
            checked_at=checked_at,
        )
