from __future__ import annotations

from backend.app.v30.models import ExecutionRequestPreview, IntegrationPlan
from backend.app.v30.registry.service import SourceRegistryService
from backend.app.v30.schema_generator.service import SchemaPackGenerator, SchemaPackNotFoundError

NOTICE = "已编译为旧执行系统可理解的请求预览。executed=false，不调用旧执行引擎，不调用 Adapter，不写 CanonicalRecord。"
HER2_CONSTRAINTS = [
    "必须保留 response_domain，细胞系 AUC/IC50 不得解释为患者 pCR。",
    "patient_id 与 sample_id 分界保留，不得把样本当成患者。",
    "禁止跨研究患者 Join（forbid_cross_entity）。",
    "HER2 IHC 2+ 不得自动判为 Positive。",
]


class ExecutionBridge:
    """Compile an IntegrationPlan into a request the old runner could accept later.

    This stage never invokes the old runner or any adapter.
    """

    def __init__(
        self,
        *,
        registry: SourceRegistryService | None = None,
        generator: SchemaPackGenerator | None = None,
    ) -> None:
        self.registry = registry or SourceRegistryService()
        self.generator = generator or SchemaPackGenerator()

    def prepare(self, plan: IntegrationPlan) -> ExecutionRequestPreview:
        pack = None
        if plan.schema_pack_id:
            try:
                pack = self.generator.get(plan.schema_pack_id)
            except SchemaPackNotFoundError:
                pack = None
        sources = [item for item in (plan.selected_sources or plan.sources) if item]
        tools = _tool_candidates(plan, sources, self.registry)
        fields = list(plan.field_requirements)
        for mapping in plan.field_mappings:
            target = (mapping.target_field or "").strip()
            if target and target not in fields:
                fields.append(target)
        oncology = _is_oncology(plan, pack.domain if pack else "")
        if oncology:
            for name in ("response_domain", "patient_id", "sample_id"):
                if name not in fields:
                    fields.append(name)
        join_policy = plan.join_policy or ("forbid_cross_entity" if oncology else "file_only")
        if oncology:
            join_policy = "forbid_cross_entity"
        constraints = list(plan.medical_constraints)
        if oncology and not constraints:
            constraints = list(HER2_CONSTRAINTS)
        ready = bool(plan.plan_id and plan.schema_pack_id and sources and fields)
        domain = (pack.domain if pack else "") or ("oncology" if oncology else "")
        return ExecutionRequestPreview(
            plan_id=plan.plan_id,
            contract_id=plan.contract_id,
            schema_pack_id=plan.schema_pack_id,
            selected_sources=sources,
            tool_candidates=tools,
            required_fields=fields,
            execution_ready=ready,
            executed=False,
            join_policy=join_policy,
            medical_constraints=constraints,
            field_mappings=list(plan.field_mappings),
            generates_data=False,
            row_count=0,
            fetched=False,
            integrated=False,
            domain=domain,
            notice=NOTICE,
        )

    def execute(self, preview: ExecutionRequestPreview, *, runner: object | None = None):
        from backend.app.v30.integration.executor import OncologyIntegrator

        return OncologyIntegrator(
            runner=runner,
            registry=self.registry,
            generator=self.generator,
        ).execute(preview)


def _tool_candidates(
    plan: IntegrationPlan,
    sources: list[str],
    registry: SourceRegistryService,
) -> list[str]:
    tools: list[str] = []
    for candidate in plan.adapter_candidates:
        binding = (candidate.fetch_binding or "").strip()
        if binding and binding not in tools:
            tools.append(binding)
    if tools:
        return tools
    for key in sources:
        registered = registry.get(key)
        binding = (registered.fetch_binding or "").strip() if registered else ""
        if binding and binding not in tools:
            tools.append(binding)
    return tools


def _is_oncology(plan: IntegrationPlan, pack_domain: str) -> bool:
    text = f"{pack_domain} {plan.schema_pack_id} {plan.contract_id or ''} {' '.join(plan.medical_constraints)}"
    return pack_domain == "oncology" or any(token in text.casefold() for token in ("her2", "oncology", "乳腺", "breast"))
