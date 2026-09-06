from __future__ import annotations

import threading
from uuid import uuid4

from backend.app.v30.models import MemorySnapshot


class SessionNotFoundError(KeyError):
    pass


class InMemorySessionStore:
    """Process-local session store. Never persists patient rows or secrets."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, MemorySnapshot] = {}

    def create(self, session_id: str | None = None) -> MemorySnapshot:
        sid = session_id or f"v30-{uuid4().hex[:12]}"
        snapshot = MemorySnapshot(session_id=sid)
        with self._lock:
            if sid in self._sessions:
                raise ValueError(f"session already exists: {sid}")
            self._sessions[sid] = snapshot
        return snapshot.model_copy(deep=True)

    def get(self, session_id: str) -> MemorySnapshot:
        with self._lock:
            snapshot = self._sessions.get(session_id)
            if snapshot is None:
                raise SessionNotFoundError(session_id)
            return snapshot.model_copy(deep=True)

    def put(self, snapshot: MemorySnapshot) -> MemorySnapshot:
        stored = snapshot.model_copy(deep=True)
        with self._lock:
            self._sessions[stored.session_id] = stored
        return stored.model_copy(deep=True)
