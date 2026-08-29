from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LoopStateStore:
    """Stdlib SQLite store for resumable closed-loop runs and episodic feedback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS agent_loops (loop_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS agent_memory (memory_id INTEGER PRIMARY KEY AUTOINCREMENT, loop_id TEXT NOT NULL, iteration INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def save_loop(self, loop_id: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO agent_loops(loop_id,payload,created_at) VALUES(?,?,?)",
                (loop_id, json.dumps(payload, ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()),
            )

    def load_loop(self, loop_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT payload FROM agent_loops WHERE loop_id = ?", (loop_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def remember(self, loop_id: str, iteration: int, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO agent_memory(loop_id,iteration,payload,created_at) VALUES(?,?,?,?)",
                (loop_id, iteration, json.dumps(payload, ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()),
            )

    def recall(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT loop_id,iteration,payload,created_at FROM agent_memory ORDER BY memory_id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [{"loop_id": row[0], "iteration": row[1], "payload": json.loads(row[2]), "created_at": row[3]} for row in rows]
