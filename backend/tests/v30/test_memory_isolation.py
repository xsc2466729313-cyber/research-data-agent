from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.v30.memory.service import MemoryService
from backend.app.v30.models import MemoryPatch, MemorySnapshot, ResearchGoal


def test_new_session_memory_is_empty() -> None:
    memory = MemoryService().create_session()
    assert memory.goal is None
    assert memory.clarifications == []
    assert memory.constraints == []


def test_parallel_sessions_do_not_share_constraints() -> None:
    service = MemoryService()
    session_a = service.create_session()
    session_b = service.create_session()
    service.apply_patch(
        session_a.session_id,
        MemoryPatch(
            goal=ResearchGoal(object="HER2阳性乳腺癌", target="耐药机制分析", domain="oncology"),
            constraints=["排除 METABRIC"],
        ),
    )
    service.apply_patch(
        session_b.session_id,
        MemoryPatch(
            goal=ResearchGoal(object="红移样本", target="观测对比", domain="astronomy"),
            constraints=["只要公开光谱"],
        ),
    )
    later_a = service.get(session_a.session_id)
    later_b = service.get(session_b.session_id)
    assert later_a.constraints == ["排除 METABRIC"]
    assert later_b.constraints == ["只要公开光谱"]
    assert "排除 METABRIC" not in later_b.constraints
    assert later_a.goal is not None and later_a.goal.object != later_b.goal.object


def test_memory_snapshot_rejects_patient_rows() -> None:
    with pytest.raises(ValidationError):
        MemorySnapshot.model_validate(
            {
                "session_id": "s1",
                "goal": None,
                "clarifications": [],
                "constraints": [],
                "patient_rows": [{"patient_id": "P1"}],
            }
        )


def test_memory_patch_rejects_secrets_and_facts() -> None:
    with pytest.raises(ValidationError):
        MemoryPatch.model_validate({"api_key": "sk-test"})
    with pytest.raises(ValidationError):
        MemoryPatch.model_validate({"historical_facts": ["HER2 IHC 2+ is Positive"]})
    allowed = set(MemorySnapshot.model_fields)
    assert allowed == {"session_id", "goal", "clarifications", "constraints"}
