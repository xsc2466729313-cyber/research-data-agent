from __future__ import annotations

import os

from pydantic import SecretStr

from backend.app.literature.models import LiteratureSearchRequest, LiteratureSearchResult
from backend.app.literature.providers.base import LiteratureProviderConfigurationError


class GiiispProvider:
    """Safe integration seam for Giiisp; no undocumented endpoint is guessed.

    The provider becomes callable only after an official response mapper is
    supplied in a later integration phase. Credentials remain process-local and
    are never exposed through API models, logs, or repr output.
    """

    name = "giiisp"

    def __init__(
        self,
        *,
        api_key: SecretStr | None = None,
        base_url: str | None = None,
    ) -> None:
        env_key = os.getenv("GIIISP_API_KEY", "").strip()
        self._api_key = api_key or (SecretStr(env_key) if env_key else None)
        self._base_url = (base_url or os.getenv("GIIISP_BASE_URL", "")).strip().rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._base_url)

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult:
        del request
        if not self.configured:
            raise LiteratureProviderConfigurationError(
                "Giiisp 尚未配置；请通过进程环境提供 GIIISP_API_KEY 和 GIIISP_BASE_URL。"
            )
        raise LiteratureProviderConfigurationError(
            "Giiisp 官方搜索端点与响应 Schema 尚未配置，已停止调用并保留 Europe PMC fallback。"
        )

    def __repr__(self) -> str:
        return f"GiiispProvider(configured={self.configured}, base_url_configured={bool(self._base_url)})"
