"""Run a provider-audited, same-condition Qwen/DeepSeek comparison.

This runner records operational observations only. It deliberately does not
invent retrieval or clinical quality scores when a frozen breast-cancer Gold
Set is unavailable. API keys are read from environment variables or local
gitignored env files and are never written to output.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a local env file without printing or persisting secret values."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def env_value(name: str, local: dict[str, str], default: str = "") -> str:
    return str(os.getenv(name) or local.get(name) or default).strip()


def load_cases(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"题集第 {index} 行不是 JSON。") from exc
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValueError(f"题集第 {index} 行缺少 question。")
        cases.append({
            "case_id": str(payload.get("case_id") or f"case-{len(cases) + 1}"),
            "question": question,
        })
    if not cases:
        raise ValueError("题集为空。")
    return cases


def expected_provider(provider: str) -> str:
    return {"qwen": "千问", "deepseek": "DeepSeek"}[provider]


def audit_result(payload: dict[str, Any], provider: str) -> tuple[bool, str | None]:
    """Reject a result whose provider identity does not match the session."""
    label = expected_provider(provider)
    actual = str(payload.get("model_provider") or "")
    used = payload.get("used_model")
    if used is None:
        used = payload.get("used_qwen")
    if bool(used) and actual != label:
        return False, f"provider_mismatch:{actual or 'missing'}"
    if bool(used) and not str(payload.get("model_name") or "").strip():
        return False, "model_name_missing"
    return True, None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_provider: dict[str, dict[str, Any]] = {}
    for provider in sorted({str(row["provider"]) for row in rows}):
        subset = [row for row in rows if row["provider"] == provider]
        valid = [row for row in subset if row["audit_valid"] and row["status"] == "完成"]
        latencies = [float(row["latency_ms"]) for row in valid]
        by_provider[provider] = {
            "runs": len(subset),
            "completed": len(valid),
            "failure_rate": round(1 - (len(valid) / len(subset)), 4) if subset else None,
            "audit_invalid": sum(not row["audit_valid"] for row in subset),
            "latency_ms_mean": round(statistics.fmean(latencies), 2) if latencies else None,
            "latency_ms_stdev": round(statistics.stdev(latencies), 2) if len(latencies) > 1 else 0.0 if latencies else None,
            "tool_calls_mean": round(statistics.fmean([row["tool_calls"] for row in valid]), 2) if valid else None,
            "source_items_mean": round(statistics.fmean([row["source_items"] for row in valid]), 2) if valid else None,
            "dataset_rows_mean": round(statistics.fmean([row["dataset_rows"] for row in valid]), 2) if valid else None,
            "quality_gates": dict(sorted({gate: sum(row["quality_gate"] == gate for row in valid) for gate in {row["quality_gate"] for row in valid}}.items())),
            "formal_quality_metrics": "NOT_EVALUATED_without_frozen_breast_cancer_goldset",
        }
    return by_provider


def safe_error(response: httpx.Response) -> str:
    return f"HTTP_{response.status_code}"


def create_session(client: httpx.Client, provider: str, config: dict[str, str]) -> tuple[str, dict[str, Any]]:
    response = client.post(
        "/api/agent/qwen-sessions",
        json={
            "provider": provider,
            "api_key": config["api_key"],
            "base_url": config["base_url"],
            "model": config["model"],
            "workspace_id": config.get("workspace_id") or None,
            "timeout_seconds": int(config.get("timeout_seconds") or 120),
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{provider} session creation failed: {safe_error(response)}")
    payload = response.json()
    return str(payload["session_id"]), {
        "provider": str(payload.get("provider") or expected_provider(provider)),
        "model": str(payload.get("model") or config["model"]),
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    qwen_env = load_env_file(args.qwen_env)
    deepseek_env = load_env_file(args.deepseek_env)
    provider_configs = {
        "qwen": {
            "api_key": env_value("DASHSCOPE_API_KEY", qwen_env),
            "base_url": env_value("QWEN_BASE_URL", qwen_env, "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "model": env_value("QWEN_MODEL", qwen_env, "qwen-plus"),
            "workspace_id": env_value("QWEN_WORKSPACE_ID", qwen_env),
            "timeout_seconds": env_value("QWEN_TIMEOUT_SECONDS", qwen_env, "120"),
        },
        "deepseek": {
            "api_key": env_value("DEEPSEEK_API_KEY", deepseek_env),
            "base_url": env_value("DEEPSEEK_BASE_URL", deepseek_env, "https://api.deepseek.com/v1"),
            "model": env_value("DEEPSEEK_MODEL", deepseek_env, "deepseek-chat"),
            "workspace_id": "",
            "timeout_seconds": env_value("DEEPSEEK_TIMEOUT_SECONDS", deepseek_env, "120"),
        },
    }
    missing = [provider for provider in args.providers if not provider_configs[provider]["api_key"]]
    if missing and not args.skip_unconfigured:
        raise RuntimeError(f"未配置 {', '.join(missing)} 凭据；密钥只应放在本地 env 文件中。")
    cases = load_cases(args.question_set)[: args.max_cases]
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    client = httpx.Client(base_url=args.local_url.rstrip("/"), timeout=args.http_timeout, follow_redirects=True)
    sessions: dict[str, str] = {}
    session_metadata: dict[str, dict[str, Any]] = {}
    try:
        for provider in args.providers:
            config = provider_configs[provider]
            if not config["api_key"]:
                continue
            session_id, metadata = create_session(client, provider, config)
            sessions[provider] = session_id
            session_metadata[provider] = metadata
        for provider in args.providers:
            if provider not in sessions:
                continue
            for repeat in range(1, args.repeats + 1):
                for case in cases:
                    started = time.perf_counter()
                    base_row: dict[str, Any] = {
                        "case_id": case["case_id"], "repeat": repeat, "provider": provider,
                        "model": session_metadata[provider]["model"], "status": "FAILED",
                        "latency_ms": 0.0, "audit_valid": False, "audit_error": None,
                        "tool_calls": 0, "source_items": 0, "dataset_rows": 0,
                        "quality_gate": "UNKNOWN", "error": None,
                    }
                    try:
                        response = client.post("/api/agent/tasks", json={
                            "question": case["question"], "use_qwen": True,
                            "allow_deterministic_fallback": False, "data_mode": args.data_mode,
                            "max_sources": args.max_sources, "max_records": args.max_records,
                            "iterative_collection": args.iterative_collection,
                            "max_collection_rounds": args.max_rounds,
                            "qwen_session_id": sessions[provider],
                        })
                        base_row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        if response.status_code >= 400:
                            base_row["error"] = safe_error(response)
                        else:
                            payload = response.json()
                            valid, audit_error = audit_result(payload, provider)
                            base_row.update({
                                "status": str(payload.get("status") or "UNKNOWN"),
                                "audit_valid": valid,
                                "audit_error": audit_error,
                                "tool_calls": len(payload.get("tool_calls") or []),
                                "source_items": len(payload.get("source_items") or []),
                                "dataset_rows": int((payload.get("modeling_dataset") or {}).get("row_count") or 0),
                                "quality_gate": str((payload.get("quality_gate_report") or {}).get("overall") or "UNKNOWN"),
                            })
                    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                        base_row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        base_row["error"] = type(exc).__name__
                    rows.append(base_row)
    finally:
        for session_id in sessions.values():
            client.delete(f"/api/agent/qwen-sessions/{session_id}")
        client.close()
    metadata = {
        "protocol_version": "model-comparison-v1",
        "question_set": str(args.question_set), "cases": len(cases),
        "providers_requested": args.providers, "providers_run": sorted(sessions),
        "repeats": args.repeats, "data_mode": args.data_mode,
        "max_sources": args.max_sources, "max_records": args.max_records,
        "iterative_collection": args.iterative_collection, "max_rounds": args.max_rounds,
        "formal_metrics": "NOT_EVALUATED_without_frozen_breast_cancer_goldset",
        "api_keys_written": False,
    }
    return {**metadata, "summary": summarize(rows)}, rows


def write_outputs(output: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    fields = [
        "case_id", "repeat", "provider", "model", "status", "latency_ms",
        "audit_valid", "audit_error", "tool_calls", "source_items", "dataset_rows",
        "quality_gate", "error",
    ]
    safe_rows = [{field: row.get(field) for field in fields} for row in rows]
    (output / "comparison.json").write_text(
        json.dumps({"metadata": metadata, "runs": safe_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(safe_rows)
    lines = ["# Qwen / DeepSeek 同条件对比运行记录", "", "> 本文件只汇总运行审计和工程诊断；正式乳腺癌质量指标在冻结 Gold Set 前保持 `NOT_EVALUATED`。", "", "## 固定条件", ""]
    for key in ("question_set", "cases", "providers_run", "repeats", "data_mode", "max_sources", "max_records", "iterative_collection", "max_rounds"):
        lines.append(f"- `{key}`: {metadata.get(key)}")
    lines.extend(["", "## 提供方摘要", "", "| 提供方 | 运行数 | 完成数 | 失败率 | 平均延迟(ms) | 平均工具调用 | 平均来源数 | 平均数据行数 | 正式质量指标 |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"])
    for provider, summary in metadata["summary"].items():
        lines.append(f"| {provider} | {summary['runs']} | {summary['completed']} | {summary['failure_rate']} | {summary['latency_ms_mean']} | {summary['tool_calls_mean']} | {summary['source_items_mean']} | {summary['dataset_rows_mean']} | `NOT_EVALUATED` |")
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Qwen / DeepSeek 同条件模型对比")
    parser.add_argument("--question-set", type=Path, default=PROJECT_ROOT / "evaluation" / "retrieval_gold.template.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "model_comparison_local")
    parser.add_argument("--local-url", default="http://127.0.0.1:8000")
    parser.add_argument("--qwen-env", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--deepseek-env", type=Path, default=PROJECT_ROOT / "evaluation" / "deepseek.local.env")
    parser.add_argument("--providers", default="qwen,deepseek")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-cases", type=int, default=30)
    parser.add_argument("--data-mode", choices=("live", "plan_only"), default="live")
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--max-records", type=int, default=500)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--http-timeout", type=float, default=300)
    parser.add_argument("--no-iterative-collection", dest="iterative_collection", action="store_false")
    parser.add_argument("--skip-unconfigured", action="store_true")
    args = parser.parse_args()
    args.providers = [item.strip() for item in args.providers.split(",") if item.strip()]
    invalid = set(args.providers) - {"qwen", "deepseek"}
    if invalid or not args.providers or args.repeats < 1:
        parser.error("providers 只能是 qwen/deepseek，且 repeats 至少为 1。")
    try:
        metadata, rows = run(args)
        write_outputs(args.output, metadata, rows)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"错误：{exc}\n")
    print(f"已写入 {args.output}（{len(rows)} 次任务运行；未写入 API Key）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
