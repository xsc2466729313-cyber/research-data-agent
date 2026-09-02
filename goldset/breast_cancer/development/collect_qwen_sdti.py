"""Development SDTI with production Qwen agent retrieval (live tools).

Field/error still use frozen medical rules and Quality V2; Qwen is not allowed
to override those. Does not copy Gold Set into templates/.
"""

from __future__ import annotations

import argparse
import json
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
from backend.app.evaluation.retrieval_selection import final_retrieval_ids
from backend.app.evaluation.service import EvaluationService

RUN_DIR = ROOT / "qwen_runs"


def require_qwen() -> QwenClient:
    load_local_dotenv()
    settings = QwenSettings.from_env()
    client = QwenClient(settings=settings)
    if not client.available:
        raise SystemExit("千问不可用：.env 中没有 DASHSCOPE_API_KEY / QWEN_BASE_URL。")
    client.test_connection()
    return client


def ids_from_payload(payload: dict[str, Any]) -> list[str]:
    """Count final selected/materialized sources, not exploratory discoveries."""
    return final_retrieval_ids(
        payload.get("tools") or [],
        modeling_dataset=payload.get("modeling_dataset"),
        source_datasets=payload.get("source_datasets") or [],
    )


def ids_from_agent(result: AgentTaskResult) -> list[str]:
    return final_retrieval_ids(
        result.tool_calls,
        modeling_dataset=result.modeling_dataset,
        source_datasets=result.source_datasets,
    )


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
        "modeling_dataset": {
            "study_key": result.modeling_dataset.study_key,
            "rows": result.modeling_dataset.rows[:1],
        },
        "source_datasets": [
            {"study_key": item.study_key, "rows": item.rows[:1]}
            for item in result.source_datasets
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
