from __future__ import annotations

from uuid import uuid4

from backend.app.v30.models import (
    AdapterCandidate,
    FieldMapping,
    IntegrationPlan,
    IntegrationPreviewRequest,
    PreviewSourceRef,
    SchemaPack,
)
from backend.app.v30.registry.service import SourceRegistryService
from backend.app.v30.schema_generator.service import HIGH_RISK_FIELDS, SchemaPackGenerator

NOTICE = "这是执行前规划，不是数据执行。execution_allowed=false。不调用 Adapter，不写 CanonicalRecord，不进入 Quality Gate。"
EXPECTED_OUTPUTS = [
    "per_source_adapter_tables: not generated",
    "canonical_records: not written",
    "quality_gate_report: not executed",
    "csv_export: not created",
]
HER2_CONSTRAINTS = [
    "必须保留 response_domain，细胞系 AUC/IC50 不得解释为患者 pCR。",
    "patient_id 与 sample_id 分界保留，不得把样本当成患者。",
    "禁止跨研究患者 Join（forbid_cross_entity）。",
    "HER2 IHC 2+ 不得自动判为 Positive；本计划不执行 Quality Gate，只保留约束。",
]


class IntegrationPreviewService:
    """Describe what Integrate would do. Never fetches, writes tables, or runs Quality Gate."""

    def __init__(
        self,
        *,
        registry: SourceRegistryService | None = None,
        generator: SchemaPackGenerator | None = None,
    ) -> None:
        self.registry = registry or SourceRegistryService()
        self.generator = generator or SchemaPackGenerator()

    def preview(self, request: IntegrationPreviewRequest) -> IntegrationPlan:
        pack = self.generator.get(request.schema_pack_id)
        refs = _source_refs(request.selected_sources)
        adapter_candidates = [self._adapter_candidate(item) for item in refs]
        field_requirements = _field_requirements(pack, request.field_mappings)
        oncology = _is_oncology(request, pack)
        if oncology and "response_domain" not in field_requirements:
            field_requirements.append("response_domain")
        if oncology:
            for name in ("patient_id", "sample_id"):
                if name not in field_requirements:
                    field_requirements.append(name)
        join_policy = "forbid_cross_entity" if oncology or pack.entity_type == "patient" else "file_only"
        return IntegrationPlan(
            plan_id=f"intplan-{uuid4().hex[:12]}",
            contract_id=request.contract_id,
            schema_pack_id=pack.schema_pack_id,
            sources=[item.source_key for item in refs],
            adapter_candidates=adapter_candidates,
            field_requirements=field_requirements,
            expected_outputs=list(EXPECTED_OUTPUTS),
            join_policy=join_policy,
            execution_allowed=False,
            fetched=False,
            integrated=False,
            generates_data=False,
            row_count=0,
            medical_constraints=list(HER2_CONSTRAINTS) if oncology else [],
            notice=NOTICE,
        )

    def _adapter_candidate(self, ref: PreviewSourceRef) -> AdapterCandidate:
        registered = self.registry.get(ref.source_key)
        binding = registered.fetch_binding if registered else None
        eligible = bool(registered and registered.integrate_eligible and binding)
        if binding:
            note = f"若执行将调用现有工具 {binding}，当前 would_invoke=false。"
        else:
            note = "无 fetch_binding，即使允许执行也不能取数。"
        return AdapterCandidate(
            source_key=ref.source_key,
            fetch_binding=binding,
            integrate_eligible=eligible,
            would_invoke=False,
            note=note,
        )


def _source_refs(selected: list[PreviewSourceRef] | list[str]) -> list[PreviewSourceRef]:
    refs: list[PreviewSourceRef] = []
    for item in selected:
        if isinstance(item, str):
            key = item.strip()
            if key:
                refs.append(PreviewSourceRef(source_key=key))
            continue
        refs.append(item)
    return refs


def _field_requirements(pack: SchemaPack, mappings: list[FieldMapping]) -> list[str]:
    names: list[str] = []
    for field in pack.fields:
        if field.required or field.name in HIGH_RISK_FIELDS or field.name in {"source_id", "raw_field", "raw_value"}:
            if field.name not in names:
                names.append(field.name)
    for mapping in mappings:
        target = (mapping.target_field or "").strip()
        if target and target not in names:
            names.append(target)
    return names


def _is_oncology(request: IntegrationPreviewRequest, pack: SchemaPack) -> bool:
    text = f"{request.domain} {request.research_goal} {pack.domain} {pack.schema_pack_id}".casefold()
    return pack.domain == "oncology" or any(token in text for token in ("her2", "乳腺", "breast", "oncology", "癌"))
