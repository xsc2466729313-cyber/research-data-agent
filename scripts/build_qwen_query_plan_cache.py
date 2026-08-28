"""Generate Qwen query plans without loading BEIR qrels or corpus."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.qwen_client import QwenClient, QwenClientError, QwenSettings
from backend.app.evaluation.public_retrieval import BEIR_DATASETS, prepare_beir_dataset
from backend.app.retrieval.query_understanding import RetrievalQueryPlan, query_plan_cache_key, validate_query_plan

PROMPT_VERSION = "qwen-query-plan-v1"
SCHEMA_VERSION = "retrieval-query-plan-v1"


def load_queries_without_qrels(dataset_dir: Path) -> dict[str, str]:
    """Only queries.jsonl is read during plan generation."""
    queries: dict[str, str] = {}
    with (dataset_dir / "queries.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            queries[str(row["_id"])] = str(row["text"])
    return queries


def request_plan(client: QwenClient, query: str) -> RetrievalQueryPlan:
    request = {
        "task": "Rewrite a retrieval query as strict JSON.",
        "query": query,
        "schema": {
            "intent": "string", "key_concepts": ["string"],
            "entities": ["string"], "constraints": ["string"],
            "must_keep_terms": ["string"], "keyword_query": "string",
            "paraphrase_query": "string", "evidence_query": "string",
        },
        "rules": [
            "Return JSON only.",
            "Preserve identifiers, numbers, quoted phrases, and negation.",
            "Do not add facts, documents, rankings, or relevance labels.",
        ],
    }
    message = client._chat(
        messages=[
            {"role": "system", "content": "You produce conservative retrieval query plans. Output valid JSON only."},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return RetrievalQueryPlan.model_validate(json.loads(str(message.get("content") or "{}")))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise QwenClientError("Qwen query plan did not satisfy RetrievalQueryPlan.") from exc


def build_cache(*, dataset_ids: list[str], data_root: Path, client: QwenClient, max_queries_per_dataset: int | None) -> dict[str, object]:
    entries: dict[str, dict[str, object]] = {}
    datasets: list[dict[str, object]] = []
    for dataset_id in dataset_ids:
        dataset_dir, manifest = prepare_beir_dataset(dataset_id, data_root, download=False)
        selected = list(sorted(load_queries_without_qrels(dataset_dir).items()))
        if max_queries_per_dataset is not None:
            selected = selected[:max_queries_per_dataset]
        datasets.append({"dataset_id": dataset_id, "source_id": manifest["source_id"], "source_url": manifest["source_url"], "queries_sha256": manifest["queries_sha256"], "query_count_planned": len(selected)})
        for query_id, query in selected:
            key = query_plan_cache_key(query_id=f"{dataset_id}:{query_id}", query=query, model_id=client.settings.model, prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION)
            try:
                plan = request_plan(client, query)
                validation = validate_query_plan(plan, query)
                status, error = ("VALID", None) if validation.valid else ("FALLBACK", None)
            except QwenClientError as exc:
                plan, validation, status, error = None, None, "ERROR", str(exc)
            entries[query] = {"cache_key": key, "dataset_id": dataset_id, "query_id": query_id, "status": status, "plan": plan.model_dump(mode="json") if plan else None, "validation": validation.model_dump(mode="json") if validation else None, "error": error}
    return {"artifact_type": "qwen_query_plan_cache", "created_at": datetime.now(timezone.utc).isoformat(), "model_id": client.settings.model, "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION, "no_qrels_notice": "Only queries.jsonl was read; qrels and corpus were not loaded during plan generation.", "credential_notice": "Credentials are read locally and never written to this artifact.", "datasets": datasets, "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an auditable Qwen plan cache without qrels leakage.")
    parser.add_argument("--dataset", action="append", choices=sorted(BEIR_DATASETS), required=True)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "beir")
    parser.add_argument("--max-queries-per-dataset", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_queries_per_dataset is not None and args.max_queries_per_dataset < 1:
        parser.error("--max-queries-per-dataset must be positive")
    settings = QwenSettings.from_env()
    if not settings.configured:
        raise SystemExit("Qwen is not configured; no cache was written.")
    client = QwenClient(settings=settings)
    try:
        payload = build_cache(dataset_ids=args.dataset, data_root=args.data_root, client=client, max_queries_per_dataset=args.max_queries_per_dataset)
    finally:
        client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    statuses = [str(item["status"]) for item in payload["entries"].values()]
    print(json.dumps({"output": str(args.output), "entries": len(statuses), "valid": statuses.count("VALID"), "fallback": statuses.count("FALLBACK"), "errors": statuses.count("ERROR")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
