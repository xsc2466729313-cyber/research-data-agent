from __future__ import annotations

from datetime import datetime, timezone

from backend.app.evidence import EvidenceBuilder
from backend.app.integration.conflict_detector import ConflictDetector
from backend.app.integration.errors import IntegrationError, IntegrationErrorCode
from backend.app.integration.merge_engine import MergeEngine
from backend.app.integration.models import (
    NormalizationIntegrationRequest,
    NormalizationIntegrationResult,
)
from backend.app.integration.patient_sample_linker import PatientSampleLinker
from backend.app.normalization import SchemaMapper


class NormalizationIntegrationPipeline:
    def __init__(
        self,
        *,
        schema_mapper: SchemaMapper | None = None,
        evidence_builder: EvidenceBuilder | None = None,
        linker: PatientSampleLinker | None = None,
        conflict_detector: ConflictDetector | None = None,
        merge_engine: MergeEngine | None = None,
    ) -> None:
        self.schema_mapper = schema_mapper or SchemaMapper()
        self.evidence_builder = evidence_builder or EvidenceBuilder()
        self.linker = linker or PatientSampleLinker()
        self.conflict_detector = conflict_detector or ConflictDetector()
        self.merge_engine = merge_engine or MergeEngine()

    def run(
        self, request: NormalizationIntegrationRequest
    ) -> NormalizationIntegrationResult:
        self._validate_request(request)
        mapping = self.schema_mapper.map(
            records=request.records,
            mappings=request.mappings,
        )
        evidence = self.evidence_builder.build(mapping.records)
        link_decisions = self.linker.link(
            identities=mapping.identities,
            candidates=request.link_candidates,
        )
        groups = self.merge_engine.build_groups(
            identities=mapping.identities,
            decisions=link_decisions,
        )
        observations = self.conflict_detector.collect_observations(
            groups=groups,
            mapped_records=mapping.records,
        )
        conflicts = self.conflict_detector.detect(observations)
        merged_records = self.merge_engine.merge(
            groups=groups,
            identities=mapping.identities,
            observations=observations,
            conflicts=conflicts,
        )
        evidence_ids = {cell.evidence_id for cell in evidence}
        referenced_evidence_ids = {
            evidence_id
            for merged in merged_records
            for field in merged.fields
            for evidence_id in field.evidence_ids
        }
        if not referenced_evidence_ids.issubset(evidence_ids):
            raise IntegrationError(
                IntegrationErrorCode.INTERNAL_ERROR,
                "Merged output references evidence that was not built.",
            )
        return NormalizationIntegrationResult(
            task_id=request.task_id,
            canonical_records=[record.canonical_record for record in mapping.records],
            mapped_records=mapping.records,
            evidence=evidence,
            link_decisions=link_decisions,
            conflicts=conflicts,
            merged_records=merged_records,
            mapping_issues=mapping.issues,
            blocked_record_ids=mapping.blocked_record_ids,
            source_items=request.source_items,
            summary={
                "raw_record_count": len(request.records),
                "canonical_record_count": len(mapping.records),
                "evidence_cell_count": len(evidence),
                "linked_pair_count": sum(
                    decision.auto_merge_allowed for decision in link_decisions
                ),
                "unresolved_link_count": sum(
                    decision.status.value == "unresolved"
                    for decision in link_decisions
                ),
                "conflict_count": len(conflicts),
                "merged_entity_count": len(merged_records),
                "blocked_record_count": len(mapping.blocked_record_ids),
            },
            processed_at=datetime.now(timezone.utc),
            notice=(
                "CanonicalRecord 为逐原始字段的原子记录；每个映射字段都有 EvidenceCell。"
                "融合视图不覆盖原子记录：HER2 按 assay、response 按 response_domain/type、"
                "变异按 gene/variant 维度隔离。低于 0.90 的患者/样本候选关联保持 unresolved，"
                "冲突值不自动选边。"
            ),
        )

    @staticmethod
    def _validate_request(request: NormalizationIntegrationRequest) -> None:
        source_ids = [source.source_id for source in request.source_items]
        record_ids = [record.record_id for record in request.records]
        mapping_ids = [mapping.mapping_id for mapping in request.mappings]
        duplicate_groups = {
            "source_id": NormalizationIntegrationPipeline._duplicates(source_ids),
            "record_id": NormalizationIntegrationPipeline._duplicates(record_ids),
            "mapping_id": NormalizationIntegrationPipeline._duplicates(mapping_ids),
        }
        nonempty_duplicates = {
            key: values for key, values in duplicate_groups.items() if values
        }
        if nonempty_duplicates:
            raise IntegrationError(
                IntegrationErrorCode.DUPLICATE_ID,
                "Normalization request contains duplicate identifiers.",
                details=nonempty_duplicates,
            )
        wrong_task_sources = [
            source.source_id
            for source in request.source_items
            if source.task_id != request.task_id
        ]
        if wrong_task_sources:
            raise IntegrationError(
                IntegrationErrorCode.INVALID_REQUEST,
                "SourceItem task_id does not match the integration task.",
                details={"source_ids": wrong_task_sources},
            )
        registered = set(source_ids)
        unknown_mapping_sources = sorted(
            {
                mapping.source_id
                for mapping in request.mappings
                if mapping.source_id is not None and mapping.source_id not in registered
            }
        )
        if unknown_mapping_sources:
            raise IntegrationError(
                IntegrationErrorCode.UNREGISTERED_SOURCE,
                "Source-specific mappings must reference a registered SourceItem.",
                details={"source_ids": unknown_mapping_sources},
            )
        unregistered = sorted(
            {
                record.source_id
                for record in request.records
                if record.source_id not in registered
            }
        )
        if unregistered:
            raise IntegrationError(
                IntegrationErrorCode.UNREGISTERED_SOURCE,
                "Every raw record must reference a registered SourceItem.",
                details={"source_ids": unregistered},
            )

    @staticmethod
    def _duplicates(values: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        return duplicates
