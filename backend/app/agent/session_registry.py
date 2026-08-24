from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app.agent.models import QwenSessionRequest, QwenSessionStatus
from backend.app.agent.qwen_client import QwenClient, QwenSettings


@dataclass
class _QwenSession:
    client: QwenClient
    expires_at: datetime


class QwenSessionRegistry:
    """Process-memory Qwen credentials with bounded lifetime and no disk writes."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 7_200,
        max_sessions: int = 50,
        client_factory: Callable[[QwenSettings], QwenClient] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.client_factory = client_factory or (lambda settings: QwenClient(settings=settings))
        self._sessions: dict[str, _QwenSession] = {}
        self._lock = threading.Lock()

    def create(self, request: QwenSessionRequest) -> QwenSessionStatus:
        settings = QwenSettings(
            api_key=request.api_key.get_secret_value(),
            base_url=request.base_url.rstrip("/"),
            model=request.model,
            workspace_id=request.workspace_id or None,
            timeout_seconds=request.timeout_seconds,
            provider=request.provider,
        )
        settings.validate_base_url()
        client = self.client_factory(settings)
        try:
            client.test_connection()
        except Exception:
            client.close()
            raise

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        session_id = f"qws_{uuid4().hex}{uuid4().hex[:8]}"
        with self._lock:
            self._remove_expired(now)
            while len(self._sessions) >= self.max_sessions:
                oldest_id = min(self._sessions, key=lambda key: self._sessions[key].expires_at)
                self._sessions.pop(oldest_id).client.close()
            self._sessions[session_id] = _QwenSession(client=client, expires_at=expires_at)
        return self._status(session_id, settings, expires_at)

    def get(self, session_id: str) -> QwenClient | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(session_id)
            return session.client if session else None

    def delete(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.client.close()
        return True

    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.client.close()

    def _remove_expired(self, now: datetime) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id).client.close()

    @staticmethod
    def _status(
        session_id: str,
        settings: QwenSettings,
        expires_at: datetime,
    ) -> QwenSessionStatus:
        return QwenSessionStatus(
            session_id=session_id,
            model=settings.model,
            base_url=settings.base_url,
            provider=settings.provider_label,
            workspace_configured=bool(
                settings.workspace_id or ".maas.aliyuncs.com" in settings.base_url
            ),
            expires_at=expires_at,
            message=f"{settings.provider_label} API 已验证并启用；凭据只保存在当前后端进程内存中。",
        )
