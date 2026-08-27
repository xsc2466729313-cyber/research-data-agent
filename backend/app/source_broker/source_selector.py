from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from uuid import uuid4

from backend.app.research_planning.models import ResearchContract
from backend.app.source_broker.models import (
    DatasetCandidate,
    FieldCoverageMatrix,
    JoinPolicy,
    SourcePlan,
    SourcePlanRequest,
)


class SourceSelector:
    def select(
        self,
        contract: ResearchContract,
        candidates: list[DatasetCandidate],
        matrix: FieldCoverageMatrix,
        request: SourcePlanRequest,
    ) -> SourcePlan:
        required = [field.field_id for field in contract.required_fields]
        recommended = [field.field_id for field in contract.recommended_fields]
        cell_map = {
            (cell.dataset_id, cell.field_id): cell.coverage
            for cell in matrix.cells
        }
        preferred = {value.casefold() for value in request.preferred_dataset_ids}
        ranked = sorted(
            candidates,
            key=lambda item: (
                -self._dataset_score(item, required, recommended, cell_map, preferred),
                item.dataset_id,
            ),
        )
        selected: list[DatasetCandidate] = []
        best_coverage = {field_id: 0.0 for field_id in required}
        for candidate in ranked:
            if len(selected) >= request.max_selected_datasets:
                break
            gain = sum(
                max(
                    0.0,
                    cell_map.get((candidate.dataset_id, field_id), 0.0)
                    - best_coverage[field_id],
                )
                for field_id in required
            )
            if not selected or gain > 0:
                selected.append(candidate)
                for field_id in required:
                    best_coverage[field_id] = max(
                        best_coverage[field_id],
                        cell_map.get((candidate.dataset_id, field_id), 0.0),
                    )
            if all(value >= 1.0 for value in best_coverage.values()):
                break

        primary = selected[0] if selected else None
        primary_required_coverage = self._coverage(
            required,
            [primary.dataset_id] if primary else [],
            cell_map,
        )
        portfolio_required_coverage = self._coverage(
            required,
            [item.dataset_id for item in selected],
            cell_map,
        )
        recommended_coverage = self._coverage(
            recommended,
            [item.dataset_id for item in selected],
            cell_map,
        )
        uncovered_required = [
            field_id
            for field_id in required
            if max(
                (cell_map.get((item.dataset_id, field_id), 0.0) for item in selected),
                default=0.0,
            )
            <= 0
        ]
        uncovered_recommended = [
            field_id
            for field_id in recommended
            if max(
                (cell_map.get((item.dataset_id, field_id), 0.0) for item in selected),
                default=0.0,
            )
            <= 0
        ]
        join_policies = [
            JoinPolicy(
                left_dataset_id=left.dataset_id,
                right_dataset_id=right.dataset_id,
                decision="FORBIDDEN_PATIENT_JOIN",
                reason=(
                    "两者为独立 cohort，当前无可核验 patient/sample crosswalk；"
                    "只能分别分析、外部验证或纵向追加。"
                ),
            )
            for left, right in combinations(selected, 2)
        ]
        warnings = [
            "当前能力矩阵是采集前 seed profile，每个字段在采集前仍需官方接口/资源校验。"
        ]
        if portfolio_required_coverage > primary_required_coverage:
            warnings.append(
                "Portfolio 联合覆盖率高于单 cohort 覆盖率，不得因此横向拼接患者。"
            )
        if uncovered_required:
            warnings.append("Required 字段仍未覆盖：" + "、".join(uncovered_required))
        status = (
            "PARTIAL"
            if not selected or primary_required_coverage < 1.0
            else "NEEDS_REVIEW"
            if any(item.capability_status != "live_verified" for item in selected)
            else "READY"
        )
        selected_ids = [item.dataset_id for item in selected]
        fallback_ids = [item.dataset_id for item in ranked if item.dataset_id not in selected_ids][:3]
        scores = [
            self._dataset_score(item, required, recommended, cell_map, preferred)
            for item in selected
        ]
        return SourcePlan(
            source_plan_id=f"source-plan-{uuid4().hex[:12]}",
            contract_id=contract.contract_id,
            status=status,
            selected_dataset_ids=selected_ids,
            selected_resource_ids=[
                resource.resource_id
                for item in selected
                for resource in item.resources
            ],
            dataset_roles={
                item.dataset_id: (
                    "primary_analysis_candidate" if index == 0 else "secondary_independent_cohort"
                )
                for index, item in enumerate(selected)
            },
            required_field_coverage=primary_required_coverage,
            portfolio_required_field_coverage=portfolio_required_coverage,
            recommended_field_coverage=recommended_coverage,
            uncovered_required_fields=uncovered_required,
            uncovered_recommended_fields=uncovered_recommended,
            join_policies=join_policies,
            access_requirements=sorted({item.access_mode for item in selected}),
            fallback_dataset_ids=fallback_ids,
            objective_score=round(sum(scores) / len(scores), 6) if scores else 0.0,
            explanation=[
                "先按单 cohort Required Field Coverage 排名，再用 greedy set cover 补充未覆盖字段。",
                "第一条数据集是主分析候选；后续数据集默认是独立 cohort，不共享患者身份。",
                "论文和目录只贡献 accession/discovery evidence，不贡献 patient rows。",
            ],
            warnings=warnings,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _coverage(
        field_ids: list[str],
        dataset_ids: list[str],
        cell_map: dict[tuple[str, str], float],
    ) -> float:
        if not field_ids:
            return 1.0
        total = sum(
            max((cell_map.get((dataset_id, field_id), 0.0) for dataset_id in dataset_ids), default=0.0)
            for field_id in field_ids
        )
        return round(total / len(field_ids), 6)

    @staticmethod
    def _dataset_score(
        candidate: DatasetCandidate,
        required: list[str],
        recommended: list[str],
        cell_map: dict[tuple[str, str], float],
        preferred: set[str],
    ) -> float:
        required_coverage = SourceSelector._coverage(required, [candidate.dataset_id], cell_map)
        recommended_coverage = SourceSelector._coverage(recommended, [candidate.dataset_id], cell_map)
        granularity = 1.0 if {"patient", "sample"} & set(candidate.declared_granularity) else 0.4
        accessibility = 1.0 if candidate.access_mode == "OPEN_API" else 0.5
        preferred_bonus = 0.05 if candidate.dataset_id.casefold() in preferred else 0.0
        score = (
            0.52 * required_coverage
            + 0.10 * recommended_coverage
            + 0.10 * candidate.authority
            + 0.08 * candidate.traceability
            + 0.07 * granularity
            + 0.05 * candidate.structuredness
            + 0.05 * accessibility
            - 0.03 * candidate.cost
            + preferred_bonus
        )
        return max(0.0, min(1.0, round(score, 6)))
