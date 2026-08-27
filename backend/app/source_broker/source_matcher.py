from __future__ import annotations

from backend.app.research_planning.models import FieldRequirement, ResearchContract
from backend.app.source_broker.models import (
    DatasetCandidate,
    FieldCoverageCell,
    FieldCoverageMatrix,
)


class SourceMatcher:
    def build_matrix(
        self,
        contract: ResearchContract,
        candidates: list[DatasetCandidate],
    ) -> FieldCoverageMatrix:
        requirements = [
            *contract.required_fields,
            *contract.recommended_fields,
            *contract.optional_fields,
        ]
        cells = [
            self._cell(requirement, candidate)
            for requirement in requirements
            for candidate in candidates
        ]
        return FieldCoverageMatrix(
            contract_id=contract.contract_id,
            field_ids=[item.field_id for item in requirements],
            dataset_ids=[item.dataset_id for item in candidates],
            cells=cells,
            notice=(
                "Coverage 来自版本化 seed profile 或论文 accession hint，是采集前规划证据；"
                "runtime_verified=false 时不得解释为数据已获取。"
            ),
        )

    @staticmethod
    def _cell(
        requirement: FieldRequirement,
        candidate: DatasetCandidate,
    ) -> FieldCoverageCell:
        hints = {value.casefold() for value in candidate.field_hints}
        field_id = requirement.field_id.casefold()
        coverage = 0.0
        basis = "not_declared"
        if field_id in hints or requirement.canonical_name.casefold() in hints:
            coverage = 1.0
            basis = "dataset_specific_seed_field"
        elif field_id.endswith("_mutation") and "mutation" in hints:
            coverage = 0.75
            basis = "generic_mutation_capability_requires_gene_verification"
        elif field_id.endswith("_variants") and "mutation" in hints:
            coverage = 0.75
            basis = "generic_mutation_capability_requires_variant_verification"
        elif field_id in {"os_months", "dfs_months", "rfs_status"} and "survival" in hints:
            coverage = 0.75
            basis = "generic_survival_capability_requires_endpoint_verification"
        elif field_id == "response_domain" and ({"pcr", "treatment_response"} & hints):
            coverage = 1.0
            basis = "deterministic_pipeline_domain_annotation"
        return FieldCoverageCell(
            field_id=requirement.field_id,
            priority=requirement.priority.value,
            dataset_id=candidate.dataset_id,
            coverage=coverage,
            match_basis=basis,
            runtime_verified=candidate.capability_status == "live_verified",
        )
