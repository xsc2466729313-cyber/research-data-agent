"""Compare Qwen against DeepSeek only as an isolated planner replacement.

The online Agent and closed loop remain Qwen-only. This script creates separate
in-process experimental runs with the same task set and budgets, then uses Qwen
as the reviewer for both result sets. It is not a production execution path.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.evaluator import QwenJudge, evaluate_task, load_cases, summarize
from backend.app.agent.models import AgentTaskRequest
from backend.app.agent.qwen_client import QwenClient, QwenSettings, parse_dotenv
from backend.app.agent.service import ResearchAgentService


def local_settings(path: Path) -> dict[str, str]:
    return parse_dotenv(path.read_text(encoding="utf-8")) if path.is_file() else {}


def env_or_local(name: str, local: dict[str, str], default: str = "") -> str:
    return str(os.getenv(name) or local.get(name) or default).strip()


def planner_settings(provider: str, qwen_env: dict[str, str], deepseek_env: dict[str, str]) -> QwenSettings:
    if provider == "qwen":
        return QwenSettings(
            provider="qwen",
            api_key=env_or_local("DASHSCOPE_API_KEY", qwen_env) or None,
            base_url=env_or_local("QWEN_BASE_URL", qwen_env, "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model=env_or_local("QWEN_MODEL", qwen_env, "qwen3.8-max"),
            workspace_id=env_or_local("QWEN_WORKSPACE_ID", qwen_env) or None,
            timeout_seconds=float(env_or_local("QWEN_TIMEOUT_SECONDS", qwen_env, "120")),
        )
    if provider == "deepseek":
        return QwenSettings(
            provider="deepseek",
            api_key=env_or_local("DEEPSEEK_API_KEY", deepseek_env) or None,
            base_url=env_or_local("DEEPSEEK_BASE_URL", deepseek_env, "https://api.deepseek.com/v1"),
            model=env_or_local("DEEPSEEK_MODEL", deepseek_env, "deepseek-chat"),
            workspace_id=None,
            timeout_seconds=float(env_or_local("DEEPSEEK_TIMEOUT_SECONDS", deepseek_env, "120")),
        )
    raise ValueError(f"不支持的消融提供方：{provider}")


def variant_summary(rows: list[dict[str, Any]], qwen_judge_model: str) -> dict[str, Any]:
    summary = summarize(rows, judge_model=qwen_judge_model)
    latencies = [float(row.get("latency_ms") or 0) for row in rows]
    summary["latency_ms_stdev"] = round(statistics.stdev(latencies), 2) if len(latencies) > 1 else 0.0
    summary["runs"] = len(rows)
    return summary


RUN_OUTPUT_FIELDS = (
    "case_id",
    "difficulty",
    "repeat",
    "variant",
    "provider",
    "planner_model",
    "status",
    "used_model",
    "used_qwen",
    "reported_provider",
    "reported_model",
    "rank",
    "latency_ms",
    "task_id",
    "tool_calls",
    "source_items",
    "candidate_sources",
    "dataset_rows",
    "quality_gate",
    "analysis_ready",
    "judge_scores",
    "judge_error",
    "run_error",
)


def safe_run_row(row: dict[str, Any]) -> dict[str, Any]:
    """Whitelist persisted fields so credentials and raw task payloads cannot leak."""
    return {key: row.get(key) for key in RUN_OUTPUT_FIELDS}


def run_observations(task: dict[str, Any]) -> dict[str, Any]:
    dataset = task.get("modeling_dataset") or {}
    gate = task.get("quality_gate_report") or {}
    readiness = task.get("readiness") or {}
    return {
        "status": str(task.get("status") or "UNKNOWN"),
        "used_model": bool(task.get("used_model", task.get("used_qwen", False))),
        "used_qwen": bool(task.get("used_qwen", False)),
        "reported_provider": str(task.get("model_provider") or ""),
        "reported_model": str(task.get("model_name") or ""),
        "tool_calls": len(task.get("tool_calls") or []),
        "source_items": len(task.get("source_items") or []),
        "candidate_sources": len(task.get("candidate_sources") or []),
        "dataset_rows": int(dataset.get("row_count") or 0),
        "quality_gate": str(gate.get("overall") or "UNKNOWN"),
        "analysis_ready": bool(readiness.get("analysis_ready", False)),
    }


def build_metadata(
    *,
    qwen_model: str,
    deepseek_model: str,
    benchmark: Path,
    cases: int,
    repeats: int,
    data_mode: str,
    max_sources: int,
    max_records: int,
    max_rounds: int,
) -> dict[str, Any]:
    return {
        "protocol": "planner-replacement-ablation-v2",
        "production_provider": "qwen",
        "production_model": qwen_model,
        "control_group": "Qwen 中间智能体（对照组）",
        "ablation_provider": "deepseek",
        "ablation_model": deepseek_model,
        "experiment_group": "DeepSeek 替换中间智能体（实验组）",
        "review_provider": "qwen",
        "review_model": qwen_model,
        "shared_summary_provider": "qwen",
        "shared_summary_model": qwen_model,
        "replacement_scope": "research question parsing, planning and tool selection only",
        "production_path_modified": False,
        "benchmark": str(benchmark),
        "cases": cases,
        "repeats": repeats,
        "fixed_conditions": {
            "data_mode": data_mode,
            "max_sources": max_sources,
            "max_records": max_records,
            "iterative_collection": True,
            "max_rounds": max_rounds,
            "temperature_policy": "client defaults shared by both variants",
        },
        "formal_metrics": "NOT_EVALUATED_without_frozen_breast_cancer_goldset",
        "qwen_review_role": "auxiliary_diagnostic_not_ground_truth",
        "api_keys_written": False,
    }


def write_report(output: Path, metadata: dict[str, Any], rows_by_variant: dict[str, list[dict[str, Any]]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    summaries = {name: variant_summary(rows, metadata["review_model"]) for name, rows in rows_by_variant.items()}
    safe_rows = {name: [safe_run_row(row) for row in rows] for name, rows in rows_by_variant.items()}
    (output / "planner_replacement_ablation.json").write_text(
        json.dumps({"metadata": metadata, "summary": summaries, "runs": safe_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 中间智能体替换消融：Qwen 与 DeepSeek",
        "",
        "> 生产主链和两轮闭环固定使用 Qwen。这里仅把中间规划/工具选择智能体替换为 DeepSeek，使用相同题集、预算、数据模式和 Qwen 评审器比较结果。没有冻结乳腺癌 Gold Set 时，正式 SDTI 始终为 `NOT_EVALUATED`。",
        "",
        "## 组别定义",
        "",
        "- 对照组：Qwen 中间智能体；与生产配置一致，但在独立实验进程运行。",
        "- 实验组：仅将中间智能体替换为 DeepSeek；数据适配器、预算和后续安全规则不变。",
        "- 共同摘要器：两组的数据层总结固定由 Qwen 生成，避免把摘要风格混入规划消融。",
        "- 评审器：两组统一由 Qwen 评审；评审分只作辅助诊断，不作为 Gold Set 真值。",
        "",
        "| 变体 | 运行数 | Recall@3 | MRR@3 | nDCG@3 | 平均延迟(ms) | 千问评审有效率 | 千问平均总体分(1-5) | 正式 SDTI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, item in summaries.items():
        metrics = item["metrics"]
        overall = "—" if metrics["avg_overall"] is None else f'{metrics["avg_overall"]:.4f}'
        lines.append(
            f"| {name} | {item['runs']} | {metrics['recall@3']:.4f} | {metrics['mrr@3']:.4f} | {metrics['ndcg@3']:.4f} | {metrics['avg_latency_ms']:.2f} | {metrics['judge_valid_rate']:.4f} | {overall} | `NOT_EVALUATED` |"
        )
    (output / "planner_replacement_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Qwen/DeepSeek 中间智能体替换消融；评审固定为 Qwen")
    parser.add_argument("--benchmark", type=Path, default=PROJECT_ROOT / "evaluation" / "retrieval_gold.template.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "planner_replacement_ablation_local")
    parser.add_argument("--qwen-env", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--deepseek-env", type=Path, default=PROJECT_ROOT / "evaluation" / "deepseek.local.env")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-cases", type=int, default=30)
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--max-records", type=int, default=500)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--data-mode", choices=("live", "plan_only"), default="live")
    parser.add_argument("--allow-provisional", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats 至少为 1。")
    qwen_env, deepseek_env = local_settings(args.qwen_env), local_settings(args.deepseek_env)
    qwen_settings = planner_settings("qwen", qwen_env, deepseek_env)
    deepseek_settings = planner_settings("deepseek", qwen_env, deepseek_env)
    if not qwen_settings.configured or not deepseek_settings.configured:
        parser.error("需要本地 Qwen 和 DeepSeek 凭据；两者不得写入 Git。")
    cases = load_cases(args.benchmark, allow_provisional=args.allow_provisional)[: args.max_cases]
    if not cases:
        parser.error("没有可评测病例；需审核 Gold Set 或显式允许 provisional。")
    summary_client = QwenClient(settings=qwen_settings)
    review_client = QwenJudge(qwen_settings.api_key or "", base_url=qwen_settings.base_url, model=qwen_settings.model)
    rows_by_variant: dict[str, list[dict[str, Any]]] = {
        "Qwen 中间智能体（对照组）": [],
        "DeepSeek 替换中间智能体（实验组）": [],
    }
    try:
        for provider, label, settings in (
            ("qwen", "Qwen 中间智能体（对照组）", qwen_settings),
            ("deepseek", "DeepSeek 替换中间智能体（实验组）", deepseek_settings),
        ):
            client = QwenClient(settings=settings)
            service = ResearchAgentService(qwen_client=client)
            try:
                for repeat in range(1, args.repeats + 1):
                    for case_index, case in enumerate(cases, 1):
                        print(
                            f"[{label}] repeat={repeat}/{args.repeats} "
                            f"case={case_index}/{len(cases)} {case.case_id}",
                            flush=True,
                        )
                        started = time.perf_counter()
                        try:
                            result = service.run(
                                AgentTaskRequest(
                                    question=case.question, use_qwen=True, allow_deterministic_fallback=False,
                                    data_mode=args.data_mode, max_sources=args.max_sources, max_records=args.max_records,
                                    iterative_collection=True, max_collection_rounds=args.max_rounds,
                                ),
                                summary_client=summary_client,
                            )
                            task = result.model_dump(mode="json")
                            row = evaluate_task(
                                case,
                                task,
                                (time.perf_counter() - started) * 1000,
                                review_client,
                            )
                            row.update(run_observations(task))
                        except Exception as exc:
                            row = {
                                "case_id": case.case_id,
                                "difficulty": case.difficulty,
                                "rank": None,
                                "latency_ms": (time.perf_counter() - started) * 1000,
                                "status": "FAILED",
                                "run_error": type(exc).__name__,
                                "judge_scores": {},
                            }
                        row.update({"variant": label, "provider": provider, "planner_model": settings.model, "repeat": repeat})
                        rows_by_variant[label].append(row)
                        print(
                            f"  status={row.get('status')} rank={row.get('rank')} "
                            f"judge={'ok' if row.get('judge_scores') else 'error'} "
                            f"latency_ms={float(row.get('latency_ms') or 0):.0f}",
                            flush=True,
                        )
            finally:
                client.close()
    finally:
        review_client.close()
        summary_client.close()
    metadata = build_metadata(
        qwen_model=qwen_settings.model,
        deepseek_model=deepseek_settings.model,
        benchmark=args.benchmark,
        cases=len(cases),
        repeats=args.repeats,
        data_mode=args.data_mode,
        max_sources=args.max_sources,
        max_records=args.max_records,
        max_rounds=args.max_rounds,
    )
    write_report(args.output, metadata, rows_by_variant)
    print(f"已写入 {args.output}；生产主链未被修改，DeepSeek 仅用于消融。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
