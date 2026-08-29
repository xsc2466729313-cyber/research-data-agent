from __future__ import annotations

from itertools import combinations

from backend.app.source_broker.models import DatasetCandidate, FieldCoverageMatrix, JoinPolicy


class WeightedSetCoverOptimizer:
    """Select a minimum-risk source set that covers required fields without illegal joins."""

    def select(
        self,
        *,
        required_fields: list[str],
        candidates: list[DatasetCandidate],
        matrix: FieldCoverageMatrix,
        max_selected: int = 3,
        lambda_risk: float = 0.35,
        lambda_latency: float = 0.15,
    ) -> tuple[list[str], list[JoinPolicy], list[str]]:
        cell_map = {(cell.dataset_id, cell.field_id): cell.coverage for cell in matrix.cells}
        if not candidates:
            return [], [], ["no source"]
        scored = [
            candidate
            for _, candidate in sorted(
                enumerate(candidates),
                key=lambda pair: (
                    self._cost(pair[1], required_fields, cell_map, lambda_risk, lambda_latency),
                    pair[0],
                ),
            )
        ]
        selected: list[DatasetCandidate] = []
        covered = {field_id: 0.0 for field_id in required_fields}
        warnings: list[str] = []
        for candidate in scored:
            if len(selected) >= max_selected:
                break
            if selected and not self._join_allowed(selected[-1], candidate):
                warnings.append(
                    f"{candidate.dataset_id} 与已选来源均为患者级且无 crosswalk，禁止加入同一 patient-level 表。"
                )
                continue
            gain = sum(
                max(0.0, cell_map.get((candidate.dataset_id, field_id), 0.0) - covered[field_id])
                for field_id in required_fields
            )
            if not selected or gain > 0:
                selected.append(candidate)
                for field_id in required_fields:
                    covered[field_id] = max(covered[field_id], cell_map.get((candidate.dataset_id, field_id), 0.0))
            if all(value >= 1.0 for value in covered.values()):
                break
        policies = [
            JoinPolicy(
                left_dataset_id=left.dataset_id,
                right_dataset_id=right.dataset_id,
                decision="FORBIDDEN_PATIENT_JOIN",
                reason="两者为独立队列且无 crosswalk，不能做患者级横向 Join。",
            )
            for left, right in combinations(selected, 2)
            if not self._join_allowed(left, right)
        ]
        if not selected:
            warnings.append("no source")
        elif any(value <= 0 for value in covered.values()):
            missing = [field_id for field_id, value in covered.items() if value <= 0]
            warnings.append("partial coverage: " + ",".join(missing))
        return [item.dataset_id for item in selected], policies, warnings

    @staticmethod
    def _cost(
        candidate: DatasetCandidate,
        required_fields: list[str],
        cell_map: dict[tuple[str, str], float],
        lambda_risk: float,
        lambda_latency: float,
    ) -> float:
        coverage = 0.0
        if required_fields:
            coverage = sum(cell_map.get((candidate.dataset_id, field_id), 0.0) for field_id in required_fields) / len(required_fields)
        risk = 1.0 - min(1.0, candidate.authority)
        return (1.0 - coverage) + candidate.cost + lambda_risk * risk + lambda_latency * (1.0 - candidate.structuredness)

    @staticmethod
    def _join_allowed(left: DatasetCandidate, right: DatasetCandidate) -> bool:
        left_patient = "patient" in left.declared_granularity
        right_patient = "patient" in right.declared_granularity
        if left.dataset_id == right.dataset_id:
            return True
        if left_patient and right_patient:
            return False
        return True
