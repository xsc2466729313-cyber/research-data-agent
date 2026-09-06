from __future__ import annotations

import threading

from backend.app.v30.models import EvidenceGraph


class GraphNotFoundError(KeyError):
    pass


class InMemoryGraphStore:
    """Process-local graph store. Never persists patient rows or EvidenceCell values."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._graphs: dict[str, EvidenceGraph] = {}

    def put(self, graph: EvidenceGraph) -> EvidenceGraph:
        stored = graph.model_copy(deep=True)
        with self._lock:
            self._graphs[stored.graph_id] = stored
        return stored.model_copy(deep=True)

    def get(self, graph_id: str) -> EvidenceGraph:
        with self._lock:
            graph = self._graphs.get(graph_id)
            if graph is None:
                raise GraphNotFoundError(graph_id)
            return graph.model_copy(deep=True)
