from pathlib import Path

from backend.app.agent.loop_store import LoopStateStore


def test_loop_state_store_persists_runs_and_episodic_memory(tmp_path: Path):
    store = LoopStateStore(tmp_path / "state" / "agent.sqlite3")
    store.save_loop("loop-1", {"status": "completed", "value": 1})
    store.remember("loop-1", 1, {"progress_score": 0.4, "next": "geo"})

    reopened = LoopStateStore(tmp_path / "state" / "agent.sqlite3")
    assert reopened.load_loop("loop-1")["value"] == 1
    memory = reopened.recall(limit=1)
    assert memory[0]["loop_id"] == "loop-1"
    assert memory[0]["payload"]["next"] == "geo"
