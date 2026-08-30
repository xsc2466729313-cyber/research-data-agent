from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from backend.app.agent.models import AgentDataMode, AgentTaskRequest
from backend.app.agent.search_planner import FieldDrivenSearchPlanner
from backend.app.agent.service import ResearchAgentService
from backend.app.evaluation.goldset import GoldSetCsvLoader, compute_gold_set_checksum
from backend.app.evaluation.models import (
    BenchmarkObservations,
    EvaluationExecution,
    EvaluationMode,
    EvaluationRequest,
    EvaluationResult,
    GoldSetBundle,
    GoldSetManifest,
    SourceValidationSummary,
)
from backend.app.evaluation.observe import (
    observe_error,
    observe_field,
    retrieval_observations_from_ids,
)
from backend.app.evaluation.service import EvaluationService
from backend.app.models import ApiModel, SourceItem


ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "goldset" / "templates"
OFFICIAL_RUNS = ROOT / "goldset" / "breast_cancer" / "official_candidate" / "evaluation_runs"
DEFAULT_OUTPUT = ROOT / "data" / "output" / "evaluation"

OFFICIAL_SOURCE_HOSTS = (
    "cbioportal.org",
    "civicdb.org",
    "clinicaltrials.gov",
    "depmap.org",
    "europepmc.org",
    "gdc.cancer.gov",
    "maayanlab.cloud",
    "ncbi.nlm.nih.gov",
)


@dataclass(frozen=True)
class RetrievalRun:
    ids: list[str]
    model_provider: str = ""
    model_name: str = ""
    used_model: bool = False
    used_qwen: bool = False
    deterministic_fallback_used: bool = False
    source_items: list[SourceItem] = field(default_factory=list)
    quality_gate: str | None = None
    publish_allowed: bool | None = None


RetrievalFn = Callable[[str, str], list[str] | RetrievalRun]


class OfficialEvaluationLaunch(ApiModel):
    evaluation_id: str | None = None
    retrieval: str = "agent"
    use_qwen: bool = True
    allow_deterministic_fallback: bool = False


def load_official_bundle() -> tuple[dict[str, Any], GoldSetManifest, GoldSetBundle]:
    envelope = json.loads((TEMPLATES / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest = GoldSetManifest.model_validate(envelope["manifest"])
    bundle = GoldSetCsvLoader().load(TEMPLATES, manifest)
    if compute_gold_set_checksum(bundle) != manifest.gold_set_checksum:
        raise ValueError("Official Gold Set checksum mismatch; refuse to evaluate.")
    if not bundle.retrieval_gold or not bundle.field_gold or not bundle.error_gold:
        raise ValueError("Official templates are empty; cannot score.")
    return envelope, manifest, bundle


def ids_from_planner(question_id: str, question: str) -> list[str]:
    """Production deterministic planner IDs — not Gold answers."""
    agent = ResearchAgentService()
    spec = agent._enrich_research_spec(agent._deterministic_spec(question, question_id), question)
    request = AgentTaskRequest(
        question=question,
        use_qwen=False,
        allow_deterministic_fallback=True,
        data_mode=AgentDataMode.PLAN_ONLY,
        max_sources=8,
        max_records=200,
        iterative_collection=False,
    )
    calls = FieldDrivenSearchPlanner().plan(spec, request, brief=None)
    found: list[str] = []
    for call in calls:
        name = str(call.get("name") or "")
        args = call.get("arguments") or {}
        for key in ("accession", "study_id", "nct_id", "project_id"):
            value = str(args.get(key) or "").strip()
            if value:
                found.append(value)
        if name == "search_civic":
            found.append("CIViC")
        if name == "search_depmap":
            found.append("DepMap")
        if name == "search_trials":
            found.append("AACT")
        if name == "search_gdc" and not args.get("project_id"):
            found.append("TCGA-BRCA")
    return list(dict.fromkeys(found))


def ids_from_agent(
    question_id: str,
    question: str,
    *,
    use_qwen: bool = True,
    allow_deterministic_fallback: bool = False,
) -> RetrievalRun:
    agent = ResearchAgentService()
    result = agent.run(
        AgentTaskRequest(
            question=question,
            use_qwen=use_qwen,
            allow_deterministic_fallback=allow_deterministic_fallback,
            data_mode=AgentDataMode.LIVE,
            max_sources=6,
            max_records=400,
            iterative_collection=True,
            max_collection_rounds=3,
        ),
        task_id=f"official-{question_id}",
    )
    found: list[str] = []
    for call in result.tool_calls:
        status = str(call.status or "").casefold()
        if any(token in status for token in ("失败", "fail", "error")):
            continue
        args = call.arguments or {}
        for key in ("accession", "study_id", "nct_id", "project_id"):
            value = str(args.get(key) or "").strip()
            if value:
                found.append(value)
        if call.tool_name == "search_civic":
            found.append("CIViC")
        if call.tool_name == "search_depmap":
            found.append("DepMap")
        if call.tool_name == "search_trials":
            found.append("AACT")
    for item in result.source_items:
        if item.accession:
            found.append(item.accession)
        if item.source_id:
            found.append(item.source_id)
    for item in result.candidate_sources:
        if item.dataset_id:
            found.append(item.dataset_id)
        if item.accession:
            found.append(item.accession)
    quality_gate = result.quality_gate_report
    return RetrievalRun(
        ids=list(dict.fromkeys(found)),
        model_provider="qwen" if result.used_qwen else result.model_provider,
        model_name=result.model_name,
        used_model=result.used_model,
        used_qwen=result.used_qwen,
        deterministic_fallback_used=use_qwen and not result.used_qwen,
        source_items=result.source_items,
        quality_gate=quality_gate.overall if quality_gate else None,
        publish_allowed=quality_gate.publish_allowed if quality_gate else None,
    )


def validate_retrieved_sources(
    source_items: list[SourceItem],
) -> tuple[SourceValidationSummary | None, list[dict[str, Any]]]:
    unique = {
        (item.source_id.strip(), item.url.strip()): item
        for item in source_items
        if item.source_id.strip() or item.url.strip()
    }
    if not unique:
        return None, []
    details: list[dict[str, Any]] = []
    invalid = 0
    for item in unique.values():
        parsed = urlparse(item.url)
        hostname = (parsed.hostname or "").casefold()
        status = item.status.casefold()
        reason = ""
        if not item.source_id.strip():
            reason = "missing_source_id"
        elif parsed.scheme.casefold() != "https" or not hostname:
            reason = "invalid_https_url"
        elif not any(hostname == host or hostname.endswith(f".{host}") for host in OFFICIAL_SOURCE_HOSTS):
            reason = "non_official_source_host"
        elif any(token in status for token in ("fail", "error", "失败", "错误")):
            reason = "adapter_reported_failure"
        valid = not reason
        invalid += int(not valid)
        details.append(
            {
                "source_id": item.source_id,
                "accession": item.accession,
                "url": item.url,
                "status": item.status,
                "valid": valid,
                "reason": reason or "successful_adapter_result_on_official_https_host",
            }
        )
    return (
        SourceValidationSummary(
            checked_source_count=len(unique),
            fake_source_count=invalid,
        ),
        details,
    )


def collect_observations(
    bundle: GoldSetBundle,
    *,
    retrieval_fn: RetrievalFn | None = None,
    retrieval_label: str | None = None,
    require_qwen: bool = False,
    fail_on_retrieval_error: bool = False,
) -> tuple[
    BenchmarkObservations,
    dict[str, Any],
    int,
    SourceValidationSummary | None,
]:
    retrieve = retrieval_fn or ids_from_planner
    questions: dict[str, str] = {}
    for row in bundle.retrieval_gold:
        questions.setdefault(row.question_id, row.research_question)
    traces: list[dict[str, Any]] = []
    ids_by_question: dict[str, list[str]] = {}
    retrieval_runs: list[RetrievalRun] = []
    source_items: list[SourceItem] = []
    retrieval_errors: list[str] = []
    for question_id, question in questions.items():
        try:
            raw_run = retrieve(question_id, question)
            run = raw_run if isinstance(raw_run, RetrievalRun) else RetrievalRun(ids=list(raw_run or []))
            ids = run.ids
            retrieval_runs.append(run)
            source_items.extend(run.source_items)
            traces.append(
                {
                    "question_id": question_id,
                    "ids": ids,
                    "error": None,
                    "model_provider": run.model_provider or None,
                    "model_name": run.model_name or None,
                    "used_model": run.used_model,
                    "used_qwen": run.used_qwen,
                    "deterministic_fallback_used": run.deterministic_fallback_used,
                    "quality_gate": run.quality_gate,
                    "publish_allowed": run.publish_allowed,
                    "source_count": len(run.source_items),
                }
            )
            ids_by_question[question_id] = ids
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            retrieval_errors.append(f"{question_id}: {error}")
            traces.append(
                {
                    "question_id": question_id,
                    "ids": [],
                    "error": error,
                }
            )
            ids_by_question[question_id] = []

    if fail_on_retrieval_error and retrieval_errors:
        raise ValueError("Formal retrieval failed: " + "; ".join(retrieval_errors))
    if require_qwen and (
        len(retrieval_runs) != len(questions)
        or any(not run.used_qwen or run.deterministic_fallback_used for run in retrieval_runs)
    ):
        raise ValueError("Formal Qwen evaluation requires Qwen on every question without deterministic fallback.")

    field_obs = []
    error_obs = []
    unresolved_high_risk = 0
    for row in bundle.field_gold:
        observation, _trace = observe_field(row)
        field_obs.append(observation)
    for row in bundle.error_gold:
        observation, _trace = observe_error(row)
        error_obs.append(observation)
        if (
            row.risk_level.value == "high"
            and row.expected_detection
            and (not observation.detected or observation.auto_repair_executed)
        ):
            unresolved_high_risk += 1

    source_validation, source_validation_details = validate_retrieved_sources(source_items)
    providers = sorted({run.model_provider for run in retrieval_runs if run.model_provider})
    models = sorted({run.model_name for run in retrieval_runs if run.model_name})

    observations = BenchmarkObservations(
        retrieval=retrieval_observations_from_ids(bundle, ids_by_question),
        fields=field_obs,
        errors=error_obs,
    )
    audit = {
        "split": "official_candidate",
        "not_frozen_test": True,
        "retrieval_method": retrieval_label or getattr(retrieve, "__name__", "injected"),
        "execution": {
            "question_count": len(questions),
            "model_provider": providers[0] if len(providers) == 1 else providers,
            "model_name": models[0] if len(models) == 1 else models,
            "used_model_count": sum(run.used_model for run in retrieval_runs),
            "used_qwen_count": sum(run.used_qwen for run in retrieval_runs),
            "used_qwen_for_all_questions": bool(questions)
            and len(retrieval_runs) == len(questions)
            and all(run.used_qwen for run in retrieval_runs),
            "deterministic_fallback_count": sum(
                run.deterministic_fallback_used for run in retrieval_runs
            ),
            "quality_gate_review_count": sum(
                run.quality_gate == "REVIEW" or run.publish_allowed is False
                for run in retrieval_runs
            ),
        },
        "retrieval_traces": traces,
        "source_validation": source_validation_details,
        "copied_from_development": False,
    }
    return observations, audit, unresolved_high_risk, source_validation


def _copy_run_sidecar(result: EvaluationResult, audit: dict[str, Any]) -> None:
    dest = OFFICIAL_RUNS / result.evaluation_id
    dest.mkdir(parents=True, exist_ok=True)
    for artifact in result.artifacts:
        src = Path(artifact.path) if getattr(artifact, "path", None) else DEFAULT_OUTPUT / result.evaluation_id / artifact.name
        if src.is_file():
            shutil.copy2(src, dest / artifact.name)
    (dest / "AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_official_evaluation(
    *,
    evaluation_id: str | None = None,
    retrieval_fn: RetrievalFn | None = None,
    retrieval: str = "agent",
    use_qwen: bool = True,
    allow_deterministic_fallback: bool = False,
    output_dir: Path | None = None,
    persist_dashboard: bool = True,
) -> EvaluationResult:
    envelope, _manifest, bundle = load_official_bundle()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    eval_id = evaluation_id or f"official-candidate-{stamp}"
    injected_retrieval = retrieval_fn is not None
    if retrieval not in {"planner", "agent"}:
        raise ValueError("retrieval must be 'planner' or 'agent'.")
    retrieval_label = "injected"
    if retrieval_fn is None and retrieval == "agent":
        retrieval_fn = lambda qid, q: ids_from_agent(
            qid,
            q,
            use_qwen=use_qwen,
            allow_deterministic_fallback=allow_deterministic_fallback,
        )
        retrieval_label = "agent_qwen_live" if use_qwen else "agent_deterministic_live"
    elif retrieval_fn is None:
        retrieval_label = "deterministic_planner_plan_only"
    observations, audit, unresolved, source_validation = collect_observations(
        bundle,
        retrieval_fn=retrieval_fn,
        retrieval_label=retrieval_label,
        require_qwen=(
            not injected_retrieval
            and retrieval == "agent"
            and use_qwen
            and not allow_deterministic_fallback
        ),
        fail_on_retrieval_error=(
            not injected_retrieval
            and retrieval == "agent"
            and not allow_deterministic_fallback
        ),
    )
    execution_audit = audit["execution"]
    provider = execution_audit["model_provider"]
    model_name = execution_audit["model_name"]
    execution = EvaluationExecution(
        retrieval_method=audit["retrieval_method"],
        model_provider=provider if isinstance(provider, str) and provider else None,
        model_name=model_name if isinstance(model_name, str) and model_name else None,
        question_count=execution_audit["question_count"],
        used_model_count=execution_audit["used_model_count"],
        used_qwen_count=execution_audit["used_qwen_count"],
        deterministic_fallback_count=execution_audit["deterministic_fallback_count"],
        quality_gate_review_count=execution_audit["quality_gate_review_count"],
        source_validation_method="current_run_adapter_sources_on_allowlisted_official_https_hosts",
    )
    request = EvaluationRequest(
        evaluation_id=eval_id,
        mode=EvaluationMode.GOLD_SET,
        gold_set=bundle,
        observations=observations,
        source_validation=source_validation,
        execution=execution,
        unresolved_high_risk_count=unresolved,
        runtime_quality_review_count=execution.quality_gate_review_count,
        allow_reviewed_unfrozen=True,
    )
    service = EvaluationService(output_dir=output_dir or DEFAULT_OUTPUT)
    result = service.run(request)
    audit.update(
        {
            "evaluation_id": result.evaluation_id,
            "evaluation_status": result.evaluation_status.value,
            "gold_set_id": bundle.manifest.gold_set_id,
            "notice": envelope.get("notice"),
            "requested_execution": {
                "retrieval": retrieval,
                "use_qwen": use_qwen,
                "allow_deterministic_fallback": allow_deterministic_fallback,
            },
            "sdti": result.metrics.sdti.model_dump(mode="json"),
            "evaluated_at": result.evaluated_at.isoformat() if result.evaluated_at else None,
        }
    )
    try:
        if persist_dashboard:
            _copy_run_sidecar(result, audit)
    except OSError:
        pass
    return result


def latest_official_metrics() -> dict[str, Any] | None:
    candidates: list[tuple[str, Path]] = []
    for root in (OFFICIAL_RUNS, DEFAULT_OUTPUT):
        if not root.is_dir():
            continue
        for path in root.glob("*/metrics.json"):
            parent = path.parent.name
            if not parent.startswith("official-candidate"):
                continue
            candidates.append((parent, path))
    newest: dict[str, Any] | None = None
    newest_stamp = ""
    for _name, path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        gold = payload.get("gold_set") or {}
        gold_id = str(gold.get("gold_set_id") or "")
        if "official-candidate" not in gold_id:
            continue
        if str(payload.get("evaluation_id") or "").startswith("development"):
            continue
        stamp = str(payload.get("evaluated_at") or path.parent.name)
        if stamp >= newest_stamp:
            newest_stamp = stamp
            newest = payload
    return newest
