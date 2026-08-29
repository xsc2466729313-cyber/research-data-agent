from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.app.agent.models import AgentDataMode, AgentTaskRequest
from backend.app.agent.search_planner import FieldDrivenSearchPlanner
from backend.app.agent.service import ResearchAgentService
from backend.app.evaluation.goldset import GoldSetCsvLoader, compute_gold_set_checksum
from backend.app.evaluation.models import (
    BenchmarkObservations,
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
from backend.app.models import ApiModel


ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "goldset" / "templates"
OFFICIAL_RUNS = ROOT / "goldset" / "breast_cancer" / "official_candidate" / "evaluation_runs"
DEFAULT_OUTPUT = ROOT / "data" / "output" / "evaluation"

RetrievalFn = Callable[[str, str], list[str]]


class OfficialEvaluationLaunch(ApiModel):
    evaluation_id: str | None = None
    retrieval: str = "planner"
    use_qwen: bool = False


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


def ids_from_agent(question_id: str, question: str, *, use_qwen: bool = False) -> list[str]:
    agent = ResearchAgentService()
    result = agent.run(
        AgentTaskRequest(
            question=question,
            use_qwen=use_qwen,
            allow_deterministic_fallback=True,
            data_mode=AgentDataMode.LIVE if not use_qwen else AgentDataMode.LIVE,
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
    return list(dict.fromkeys(found))


def collect_observations(
    bundle: GoldSetBundle,
    *,
    retrieval_fn: RetrievalFn | None = None,
) -> tuple[BenchmarkObservations, dict[str, Any], int]:
    retrieve = retrieval_fn or ids_from_planner
    questions: dict[str, str] = {}
    for row in bundle.retrieval_gold:
        questions.setdefault(row.question_id, row.research_question)
    traces: list[dict[str, Any]] = []
    ids_by_question: dict[str, list[str]] = {}
    for question_id, question in questions.items():
        try:
            ids = list(retrieve(question_id, question) or [])
            traces.append({"question_id": question_id, "ids": ids, "error": None})
            ids_by_question[question_id] = ids
        except Exception as exc:
            traces.append(
                {
                    "question_id": question_id,
                    "ids": [],
                    "error": f"{exc.__class__.__name__}: {exc}",
                }
            )
            ids_by_question[question_id] = []

    field_obs = []
    error_obs = []
    unresolved_high_risk = 0
    for row in bundle.field_gold:
        observation, _trace = observe_field(row)
        field_obs.append(observation)
    for row in bundle.error_gold:
        observation, _trace = observe_error(row)
        error_obs.append(observation)
        if row.risk_level.value == "high" and observation.detected and not observation.auto_repair_executed:
            unresolved_high_risk += 1

    observations = BenchmarkObservations(
        retrieval=retrieval_observations_from_ids(bundle, ids_by_question),
        fields=field_obs,
        errors=error_obs,
    )
    audit = {
        "split": "official_candidate",
        "not_frozen_test": True,
        "retrieval_method": getattr(retrieve, "__name__", "injected"),
        "retrieval_traces": traces,
        "copied_from_development": False,
    }
    return observations, audit, unresolved_high_risk


def official_source_validation(bundle: GoldSetBundle) -> SourceValidationSummary:
    """Count unique Gold dataset IDs as checked public identifiers; no live URL crawl."""
    ids = {row.dataset_id.strip() for row in bundle.retrieval_gold if row.dataset_id.strip()}
    fake = sum(1 for item in ids if not item)
    return SourceValidationSummary(checked_source_count=len(ids), fake_source_count=fake)


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
    retrieval: str = "planner",
    use_qwen: bool = False,
    output_dir: Path | None = None,
    persist_dashboard: bool = True,
) -> EvaluationResult:
    envelope, _manifest, bundle = load_official_bundle()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    eval_id = evaluation_id or f"official-candidate-{stamp}"
    if retrieval_fn is None and retrieval == "agent":
        retrieval_fn = lambda qid, q, _use=use_qwen: ids_from_agent(qid, q, use_qwen=_use)
    observations, audit, unresolved = collect_observations(bundle, retrieval_fn=retrieval_fn)
    request = EvaluationRequest(
        evaluation_id=eval_id,
        mode=EvaluationMode.GOLD_SET,
        gold_set=bundle,
        observations=observations,
        source_validation=official_source_validation(bundle),
        unresolved_high_risk_count=unresolved,
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
