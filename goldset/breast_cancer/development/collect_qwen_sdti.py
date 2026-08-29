"""Development SDTI with production Qwen agent retrieval (live tools).

Field/error still use frozen medical rules and Quality V2; Qwen is not allowed
to override those. Does not copy Gold Set into templates/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
for path in (ROOT, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from collect_observations import (
    gold_id_matches,
    load_frozen_bundle,
    observe_error,
    observe_field,
    source_validation,
)
from backend.app.agent.models import AgentDataMode, AgentTaskRequest, AgentTaskResult
from backend.app.agent.qwen_client import QwenClient, QwenSettings, load_local_dotenv
from backend.app.agent.service import ResearchAgentService
from backend.app.evaluation.models import (
    BenchmarkObservations,
    EvaluationMode,
    EvaluationRequest,
    RetrievalObservation,
)
from backend.app.evaluation.service import EvaluationService

RUN_DIR = ROOT / "qwen_runs"
GSE_RE = re.compile(r"\bGSE[1-9]\d{2,6}\b", re.IGNORECASE)
NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
CBIOPORTAL_RE = re.compile(
    r"\b(?:brca_metabric|breast_alpelisib_2020|brca_mskcc_2019|brca_tcga[a-z0-9_]*)\b",
    re.IGNORECASE,
)


def require_qwen() -> QwenClient:
    load_local_dotenv()
    settings = QwenSettings.from_env()
    client = QwenClient(settings=settings)
    if not client.available:
        raise SystemExit("千问不可用：.env 中没有 DASHSCOPE_API_KEY / QWEN_BASE_URL。")
    client.test_connection()
    return client


def _add(found: list[str], value: object) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        found.append(text)


def _call_succeeded(status: str) -> bool:
    text = str(status or "")
    lowered = text.casefold()
    return not any(token in text or token in lowered for token in ("失败", "fail", "error"))


def ids_from_payload(payload: dict[str, Any]) -> list[str]:
    """Count only sources the agent actually returned or successfully fetched."""
    found: list[str] = []
    structured: list[str] = []
    for call in payload.get("tools") or []:
        if not _call_succeeded(str(call.get("status") or "")):
            continue
        args = call.get("arguments") or {}
        for key in ("accession", "study_id", "nct_id", "project_id"):
            _add(found, args.get(key))
        structured.append(json.dumps(args, ensure_ascii=False))
        name = call.get("tool_name")
        if name == "search_civic":
            found.append("CIViC")
        if name == "search_trials":
            found.append("AACT")
        if name == "search_gdc":
            project = str(args.get("project_id") or "").strip()
            found.append(project or "TCGA-BRCA")
        if name == "search_depmap":
            found.append("DepMap")
    for source in payload.get("candidate_sources") or []:
        _add(found, source.get("dataset_id"))
        _add(found, source.get("accession"))
        structured.append(str(source.get("dataset_id") or ""))
        structured.append(str(source.get("accession") or ""))
    for item in payload.get("source_items") or []:
        _add(found, item.get("accession"))
        _add(found, item.get("source_id"))
        structured.append(str(item.get("source_id") or ""))
        structured.append(str(item.get("accession") or ""))
    blob = " ".join(structured)
    found.extend(GSE_RE.findall(blob))
    found.extend(NCT_RE.findall(blob))
    found.extend(CBIOPORTAL_RE.findall(blob))
    if "depmap" in blob.casefold() or "ccle" in blob.casefold():
        found.append("DepMap")
    if "civic" in blob.casefold() and "CIViC" not in found:
        found.append("CIViC")
    return list(dict.fromkeys(found))


def ids_from_agent(result: AgentTaskResult) -> list[str]:
    payload = {
        "tools": [
            {"tool_name": call.tool_name, "status": call.status, "arguments": call.arguments}
            for call in result.tool_calls
        ],
        "source_items": [
            {"source_id": item.source_id, "accession": item.accession}
            for item in result.source_items
        ],
        "candidate_sources": [
            {"dataset_id": item.dataset_id, "accession": item.accession}
            for item in result.candidate_sources
        ],
    }
    return ids_from_payload(payload)


def run_one_question(
    *,
    agent: ResearchAgentService,
    qwen: QwenClient,
    question_id: str,
    question: str,
) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RUN_DIR / f"{question_id}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("used_qwen") is True and "error" not in cached:
            return cached
    request = AgentTaskRequest(
        question=question,
        use_qwen=True,
        allow_deterministic_fallback=False,
        data_mode=AgentDataMode.LIVE,
        max_sources=8,
        max_records=4000,
        iterative_collection=True,
        max_collection_rounds=4,
    )
    result = agent.run(request, qwen_client=qwen, summary_client=qwen)
    if not result.used_qwen:
        raise RuntimeError(f"{question_id} 未使用千问（used_qwen=false）。")
    payload = {
        "question_id": question_id,
        "task_id": result.task_id,
        "used_qwen": result.used_qwen,
        "used_model": result.used_model,
        "agent_mode": result.agent_mode,
        "model_name": result.model_name,
        "status": result.status,
        "ids": ids_from_agent(result),
        "tools": [
            {
                "tool_name": call.tool_name,
                "status": call.status,
                "arguments": call.arguments,
                "record_count": call.record_count,
            }
            for call in result.tool_calls
        ],
        "source_items": [
            {
                "source_id": item.source_id,
                "accession": item.accession,
                "status": item.status,
            }
            for item in result.source_items
        ],
        "candidate_sources": [
            {
                "dataset_id": item.dataset_id,
                "accession": item.accession,
                "source_database": item.source_database,
            }
            for item in result.candidate_sources
        ],
        "row_count": result.modeling_dataset.row_count,
        "analysis_ready": result.readiness.analysis_ready,
        "notice": result.notice,
        "max_collection_rounds": 4,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="只跑指定 question_id，例如 q01_neoadjuvant_pcr")
    args = parser.parse_args()
    qwen = require_qwen()
    envelope, manifest, bundle = load_frozen_bundle()
    questions: dict[str, str] = {}
    for row in bundle.retrieval_gold:
        questions.setdefault(row.question_id, row.research_question)
    if args.only:
        if args.only not in questions:
            raise SystemExit(f"未知 question_id: {args.only}")
        questions = {args.only: questions[args.only]}

    agent = ResearchAgentService()
    traces: list[dict[str, Any]] = []
    ids_by_question: dict[str, list[str]] = {}
    for question_id, question in questions.items():
        print(f"QWEN_RUN {question_id}", flush=True)
        try:
            payload = run_one_question(
                agent=agent,
                qwen=qwen,
                question_id=question_id,
                question=question,
            )
            traces.append(payload)
            ids_by_question[question_id] = (
                ids_from_payload(payload) if payload.get("used_qwen") else []
            )
        except Exception as exc:  # keep remaining questions; do not fake retrieval
            traces.append(
                {
                    "question_id": question_id,
                    "used_qwen": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "ids": [],
                }
            )
            ids_by_question[question_id] = []

    if args.only:
        print(json.dumps(traces, ensure_ascii=False, indent=2), flush=True)
        return

    retrieval = [
        RetrievalObservation(
            question_id=row.question_id,
            dataset_id=row.dataset_id,
            retrieved=any(
                gold_id_matches(row.dataset_id, item)
                for item in ids_by_question.get(row.question_id, [])
            ),
        )
        for row in bundle.retrieval_gold
    ]
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
        retrieval=retrieval,
        fields=field_obs,
        errors=error_obs,
    )
    request = EvaluationRequest(
        evaluation_id="development-xsc-qwen-live-20260829",
        mode=EvaluationMode.GOLD_SET,
        gold_set=bundle,
        observations=observations,
        source_validation=source_validation(),
        unresolved_high_risk_count=unresolved_high_risk,
    )
    result = EvaluationService(output_dir=ROOT / "evaluation_runs").run(request)
    audit = {
        "split": "development",
        "not_frozen_test": True,
        "copied_to_templates": False,
        "planner": "qwen-live-agent",
        "independent_reviewer": manifest.independent_reviewer,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_traces": traces,
        "evaluation_status": result.evaluation_status.value,
        "sdti": result.metrics.sdti.model_dump(mode="json"),
        "notice": (
            "千问 live Agent 在 development 金标准上的观察。字段/错误仍走规则与 Quality V2。"
            "不是 frozen_test，不得填入看板正式 SDTI。"
        ),
    }
    (ROOT / "OBSERVATIONS_QWEN.json").write_text(
        json.dumps(observations.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "OBSERVATION_AUDIT_QWEN.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "evaluation_id": result.evaluation_id,
        "evaluation_status": result.evaluation_status.value,
        "publish_allowed": result.safety.publish_allowed,
        "used_qwen_questions": sum(1 for item in traces if item.get("used_qwen") is True),
        "question_count": len(questions),
        "sdti": result.metrics.sdti.value,
        "retrieval_f1": result.metrics.retrieval_f1.value,
        "faithfulness": result.metrics.faithfulness.value,
        "traceability": result.metrics.traceability.value,
        "error_f1": result.metrics.error_f1.value,
        "repair_accuracy": result.metrics.repair_accuracy.value,
        "gate": result.safety.gate.value if hasattr(result.safety.gate, "value") else str(result.safety.gate),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
