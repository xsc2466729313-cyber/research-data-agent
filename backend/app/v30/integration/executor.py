from __future__ import annotations

from typing import Any

from backend.app.agent.models import AgentTaskRequest
from backend.app.v30.models import ExecutionRequestPreview, ExecutionResult
from backend.app.v30.registry.service import SourceRegistryService
from backend.app.v30.schema_generator.service import SchemaPackGenerator, SchemaPackNotFoundError

DEFAULT_ONCOLOGY_QUESTION = "研究 HER2 阳性乳腺癌耐药机制与疗效预测，整理患者级公开科研数据。"
SOURCE_TO_PREFERRED = {
    "geo": "GEO",
    "gdc": "GDC",
    "cbioportal": "cBioPortal",
    "aact": "ClinicalTrials",
    "civic": "CIViC",
    "europe_pmc": "Europe PMC",
}


class OncologyIntegrateNotAllowedError(ValueError):
    error = "only_oncology_integrate_supported"


class ExecutionNotReadyError(ValueError):
    error = "execution_not_ready"


class RunnerNotInjectedError(RuntimeError):
    error = "old_runner_not_injected"


class OncologyIntegrator:
    """Hand an oncology ExecutionRequestPreview to the existing runner. Never calls adapters itself."""

    def __init__(
        self,
        *,
        runner: object | None = None,
        registry: SourceRegistryService | None = None,
        generator: SchemaPackGenerator | None = None,
    ) -> None:
        self.runner = runner
        self.registry = registry or SourceRegistryService()
        self.generator = generator or SchemaPackGenerator()

    def execute(self, preview: ExecutionRequestPreview) -> ExecutionResult:
        if not _is_oncology(preview, self.generator):
            raise OncologyIntegrateNotAllowedError(OncologyIntegrateNotAllowedError.error)
        if not preview.execution_ready:
            raise ExecutionNotReadyError(ExecutionNotReadyError.error)
        if self.runner is None:
            raise RunnerNotInjectedError(RunnerNotInjectedError.error)
        request = _to_agent_request(preview)
        raw = _invoke_runner(self.runner, request)
        return _to_execution_result(preview, raw)


def _is_oncology(preview: ExecutionRequestPreview, generator: SchemaPackGenerator) -> bool:
    domain = (preview.domain or "").strip().casefold()
    if domain == "oncology":
        return True
    if domain in {"astronomy", "materials"}:
        return False
    pack_domain = ""
    if preview.schema_pack_id:
        try:
            pack_domain = generator.get(preview.schema_pack_id).domain
        except SchemaPackNotFoundError:
            pack_domain = ""
    text = f"{pack_domain} {preview.schema_pack_id} {preview.join_policy} {' '.join(preview.required_fields)}"
    folded = text.casefold()
    if pack_domain == "astronomy" or "astronomy" in folded or "supernova" in folded:
        return False
    return pack_domain == "oncology" or "oncology" in folded or preview.join_policy == "forbid_cross_entity"


def _to_agent_request(preview: ExecutionRequestPreview) -> AgentTaskRequest:
    question = (preview.question or "").strip() or DEFAULT_ONCOLOGY_QUESTION
    tools = [item for item in preview.tool_candidates if item]
    preferred = [SOURCE_TO_PREFERRED.get(key, key) for key in preview.selected_sources if key]
    focus_accessions: list[str] = []
    selected = {item.casefold() for item in preview.selected_sources}
    if "search_cbioportal" in tools or "cbioportal" in selected:
        focus_accessions.append("brca_metabric")
    return AgentTaskRequest(
        question=question,
        use_qwen=False,
        allow_deterministic_fallback=True,
        data_mode="live",
        preferred_sources=preferred[:20],
        focus_accessions=focus_accessions[:20],
        focus_tools=tools[:20],
        max_sources=max(1, min(8, len(tools) or 2)),
        max_records=200,
        iterative_collection=False,
    )


def _invoke_runner(runner: object, request: AgentTaskRequest):
    run = getattr(runner, "run", None)
    if callable(run):
        return run(request)
    if callable(runner):
        return runner(request)
    raise RunnerNotInjectedError(RunnerNotInjectedError.error)


def _to_execution_result(preview: ExecutionRequestPreview, raw: Any) -> ExecutionResult:
    rows = list(getattr(getattr(raw, "modeling_dataset", None), "rows", []) or [])
    columns = [item.name for item in getattr(getattr(raw, "modeling_dataset", None), "columns", []) or []]
    keys = set(columns)
    if rows:
        keys.update(rows[0].keys())
    report = getattr(raw, "quality_gate_report", None)
    quality_status = getattr(report, "overall", None) or "UNKNOWN"
    has_rows = bool(rows)
    formats = ["metadata", "quality_report"]
    if has_rows:
        formats.extend(["csv", "xlsx", "json"])
    return ExecutionResult(
        task_id=str(getattr(raw, "task_id", "") or preview.plan_id),
        status=str(getattr(raw, "status", "completed") or "completed"),
        export_available=True,
        quality_status=quality_status,
        evidence_summary={
            "has_source_id": "source_id" in keys or bool(getattr(raw, "source_items", None)),
            "has_raw_field": "raw_field" in keys,
            "has_raw_value": "raw_value" in keys,
            "has_evidence": bool(report) or bool(getattr(raw, "source_items", None)),
            "row_count": len(rows),
            "has_response_domain": "response_domain" in keys or "response_domain" in preview.required_fields,
            "has_patient_id": "patient_id" in keys or "patient_id" in preview.required_fields,
            "has_sample_id": "sample_id" in keys or "sample_id" in preview.required_fields,
            "join_policy": preview.join_policy,
        },
        domain="oncology",
        executed=True,
        schema_pack_id=preview.schema_pack_id,
        selected_sources=list(preview.selected_sources),
        tool_candidates=list(preview.tool_candidates),
        required_fields=list(preview.required_fields),
        join_policy=preview.join_policy or "forbid_cross_entity",
        medical_constraints=list(preview.medical_constraints),
        export_formats=formats,
        notice="已转调现有执行链完成医学 Integrate。v30 未直接调用 Adapter。",
    )
