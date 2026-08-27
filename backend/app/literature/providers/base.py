from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.literature.models import LiteratureSearchRequest, LiteratureSearchResult


class LiteratureProviderError(RuntimeError):
    """Base error for replaceable literature providers."""


class LiteratureProviderConfigurationError(LiteratureProviderError):
    """Raised when a provider cannot run without external configuration."""


@runtime_checkable
class LiteratureProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    def search(self, request: LiteratureSearchRequest) -> LiteratureSearchResult: ...
