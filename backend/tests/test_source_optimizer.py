from __future__ import annotations

from backend.app.source_broker.models import DatasetCandidate, FieldCoverageCell, FieldCoverageMatrix
from backend.app.source_registry_v2 import WeightedSetCoverOptimizer


def _candidate(dataset_id: str, fields: dict[str, float], *, granularity: list[str], cost: float = 0.1, authority: float = 0.9) -> tuple[DatasetCandidate, list[FieldCoverageCell]]:
    candidate = DatasetCandidate(
        dataset_id=dataset_id,
        source_id=dataset_id.split(":")[0],
        title=dataset_id,
        source_url=f"https://example.org/{dataset_id}",
        declared_granularity=granularity,
        field_hints=list(fields),
        access_mode="OPEN_API",
        capability_status="seed_requires_runtime_verification",
        authority=authority,
        traceability=0.9,
        structuredness=0.8,
        cost=cost,
    )
    cells = [
        FieldCoverageCell(field_id=field_id, priority="required", dataset_id=dataset_id, coverage=coverage, match_basis="test")
        for field_id, coverage in fields.items()
    ]
    return candidate, cells


def test_required_fields_complete_prefers_single_source() -> None:
    a, a_cells = _candidate("geo:A", {"pik3ca": 1, "pcr": 1, "her2_status": 1}, granularity=["patient"])
    b, b_cells = _candidate("cbio:B", {"pik3ca": 1, "pcr": 0, "her2_status": 1}, granularity=["patient"], cost=0.4)
    selected, _policies, warnings = WeightedSetCoverOptimizer().select(
        required_fields=["pik3ca", "pcr", "her2_status"],
        candidates=[a, b],
        matrix=FieldCoverageMatrix(contract_id="c", field_ids=["pik3ca", "pcr", "her2_status"], dataset_ids=["geo:A", "cbio:B"], cells=a_cells + b_cells, notice="t"),
    )
    assert selected == ["geo:A"]
    assert not any(item.startswith("partial") for item in warnings)


def test_two_source_optimum_and_forbidden_patient_join() -> None:
    a, a_cells = _candidate("geo:A", {"pik3ca": 1, "pcr": 0, "her2_status": 1}, granularity=["patient"])
    b, b_cells = _candidate("cbio:B", {"pik3ca": 0, "pcr": 1, "her2_status": 1}, granularity=["patient"])
    selected, policies, warnings = WeightedSetCoverOptimizer().select(
        required_fields=["pik3ca", "pcr", "her2_status"],
        candidates=[a, b],
        matrix=FieldCoverageMatrix(contract_id="c", field_ids=["pik3ca", "pcr", "her2_status"], dataset_ids=["geo:A", "cbio:B"], cells=a_cells + b_cells, notice="t"),
    )
    assert selected == ["geo:A"]
    assert policies == []
    assert any("partial coverage" in item for item in warnings)


def test_no_source() -> None:
    selected, _policies, warnings = WeightedSetCoverOptimizer().select(
        required_fields=["pcr"],
        candidates=[],
        matrix=FieldCoverageMatrix(contract_id="c", field_ids=["pcr"], dataset_ids=[], cells=[], notice="t"),
    )
    assert selected == []
    assert "no source" in warnings
