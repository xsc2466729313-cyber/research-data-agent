from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.evaluator import QwenJudge, evaluate_task, load_cases, write_reports


def load_local_qwen_config(path: Path) -> None:
    """Load local-only Qwen settings without overriding shell variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"DASHSCOPE_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"}:
            os.environ.setdefault(key, value.strip())


def read_credentials(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("凭据 CSV 为空。")
    if {item.strip() for item in rows[0]} >= {"apiKey", "openAiCompatible"}:
        headers = [item.strip() for item in rows[0]]
        values = rows[1] if len(rows) > 1 else []
        return {headers[index]: values[index].strip() if index < len(values) else "" for index in range(len(headers))}
    mapping: dict[str, str] = {}
    for row in rows:
        if len(row) >= 2:
            mapping[row[0].strip()] = row[1].strip()
    return mapping


def main() -> int:
    load_local_qwen_config(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run breast-cancer Agent retrieval metrics with Qwen review")
    parser.add_argument("--benchmark", type=Path, default=Path("evaluation/retrieval_gold.template.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results_qwen_review"))
    parser.add_argument("--local-url", default="http://127.0.0.1:8000")
    parser.add_argument("--qwen-csv", type=Path, default=None)
    parser.add_argument("--qwen-review-api-key", default=os.getenv("DASHSCOPE_API_KEY", ""))
    parser.add_argument("--qwen-review-base-url", default=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    parser.add_argument("--qwen-review-model", default=os.getenv("QWEN_MODEL", "qwen-plus"))
    parser.add_argument("--max-cases", type=int, default=30)
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--allow-provisional", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.benchmark, allow_provisional=args.allow_provisional)
    cases = cases[: max(0, args.max_cases)]
    if not cases:
        raise SystemExit("没有可评测病例；请审核 Gold Set，或临时使用 --allow-provisional。")
    if not args.skip_judge and not args.qwen_review_api_key.strip():
        raise SystemExit("缺少千问 API Key。请设置 DASHSCOPE_API_KEY 或传入 --qwen-review-api-key。")

    judge = None if args.skip_judge else QwenJudge(
        args.qwen_review_api_key,
        base_url=args.qwen_review_base_url,
        model=args.qwen_review_model,
    )
    qwen_session_id: str | None = None
    metadata = {
        "benchmark": str(args.benchmark),
        "generation_model": "qwen-session-or-deterministic-fallback",
        "generation_provider": "qwen-or-deterministic-fallback",
        "judge_model": None if judge is None else args.qwen_review_model,
        "judge_provider": None if judge is None else "qwen",
        "judge_status": "skipped" if judge is None else "configured",
        "cases_requested": len(cases),
    }
    client = httpx.Client(base_url=args.local_url.rstrip("/"), timeout=300, follow_redirects=True)
    try:
        if args.qwen_csv:
            credential = read_credentials(args.qwen_csv)
            response = client.post(
                "/api/agent/qwen-sessions",
                json={
                    "api_key": credential.get("apiKey", ""),
                    "base_url": credential.get("openAiCompatible", ""),
                    "model": credential.get("model", "qwen3.7-plus") or "qwen3.7-plus",
                    "workspace_id": credential.get("workspaceId") or None,
                    "timeout_seconds": 120,
                },
            )
            response.raise_for_status()
            qwen_session_id = response.json()["session_id"]
            metadata["generation_model"] = response.json().get("model", "qwen3.7-plus")

        rows = []
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
            started = __import__("time").perf_counter()
            response = client.post(
                "/api/agent/tasks",
                json={
                    "question": case.question,
                    "use_qwen": qwen_session_id is not None,
                    "allow_deterministic_fallback": qwen_session_id is None,
                    "data_mode": "live",
                    "max_sources": args.max_sources,
                    "max_records": 500,
                    **({"qwen_session_id": qwen_session_id} if qwen_session_id else {}),
                },
            )
            latency_ms = (__import__("time").perf_counter() - started) * 1000
            response.raise_for_status()
            rows.append(evaluate_task(case, response.json(), latency_ms, judge))
        write_reports(args.output, rows, metadata)
        print(f"报告已写入：{args.output}", flush=True)
    finally:
        if qwen_session_id:
            client.delete(f"/api/agent/qwen-sessions/{qwen_session_id}")
        client.close()
        if judge:
            judge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
