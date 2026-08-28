from __future__ import annotations

import csv
import io
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_sources: tuple[str, ...]
    difficulty: str = "medium"


def load_cases(path: Path, *, allow_provisional: bool = False) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        payload = json.loads(raw)
        status = str(payload.get("review_status", "approved")).casefold()
        if status not in {"approved", "reviewed", "frozen"} and not allow_provisional:
            continue
        question = str(payload.get("question") or payload.get("research_question") or "").strip()
        expected = payload.get("expected_sources") or payload.get("expected_source_ids") or []
        if not question or not expected:
            raise ValueError(f"评测 Gold Set 第 {line_number} 行缺少 question 或 expected_sources。")
        cases.append(
            EvaluationCase(
                case_id=str(payload.get("case_id") or payload.get("question_id") or f"case-{line_number}"),
                question=question,
                expected_sources=tuple(str(item).strip() for item in expected if str(item).strip()),
                difficulty=str(payload.get("difficulty") or "medium"),
            )
        )
    return cases


def retrieval_metrics(ranks: dict[str, int | None], difficulties: dict[str, str]) -> dict[str, float]:
    count = max(1, len(ranks))
    values = list(ranks.values())
    result = {
        f"recall@{cutoff}": sum(rank is not None and rank <= cutoff for rank in values) / count
        for cutoff in (1, 3, 5)
    }
    result["mrr@3"] = sum(1 / rank if rank is not None and rank <= 3 else 0 for rank in values) / count
    result["ndcg@3"] = sum(
        1 / math.log2(rank + 1) if rank is not None and rank <= 3 else 0 for rank in values
    ) / count
    for difficulty in sorted(set(difficulties.values())):
        selected = [case_id for case_id, level in difficulties.items() if level == difficulty]
        result[f"recall@3_{difficulty}"] = sum(
            ranks[case_id] is not None and ranks[case_id] <= 3 for case_id in selected
        ) / max(1, len(selected))
    return result


def _source_rows(task: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*(task.get("candidate_sources") or []), *(task.get("source_items") or [])]:
        keys = [
            item.get("dataset_id"), item.get("accession"), item.get("source_id"),
            item.get("dataset_name"), item.get("source_name"), item.get("source_database"),
        ]
        identity = "|".join(str(key).strip().casefold() for key in keys if key)
        if identity and identity not in seen:
            seen.add(identity)
            rows.append(item)
    return rows


def source_rank(task: dict[str, Any], expected_sources: tuple[str, ...]) -> int | None:
    rows = _source_rows(task)
    expected = {item.casefold() for item in expected_sources}
    for index, row in enumerate(rows, 1):
        values = {
            str(row.get(key) or "").strip().casefold()
            for key in ("dataset_id", "accession", "source_id", "dataset_name", "source_name", "source_database")
        }
        if values & expected:
            return index
    return None


class QwenJudge:
    """Use Qwen only to review a planner-ablation output after it is produced."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen3.8-max",
        timeout_seconds: float = 120,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("缺少 DASHSCOPE_API_KEY。")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or "qwen3.8-max"
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._owns_client = client is None

    def evaluate(self, case: EvaluationCase, task: dict[str, Any]) -> dict[str, Any]:
        def compact(items: Any, fields: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
            rows = items if isinstance(items, list) else []
            return [
                {key: item.get(key) for key in fields if item.get(key) is not None}
                for item in rows[:limit]
                if isinstance(item, dict)
            ]

        context = {
            "question": case.question,
            "research_spec": task.get("research_spec"),
            "plan": task.get("plan"),
            "tool_calls": compact(
                task.get("tool_calls"),
                ("tool_name", "arguments", "status", "source_count", "record_count", "message"),
                12,
            ),
            "candidate_sources": compact(
                task.get("candidate_sources"),
                (
                    "dataset_id", "dataset_name", "source_database", "data_type", "sample_count",
                    "has_treatment", "has_response", "public_access", "relevance_score", "accession",
                ),
                20,
            ),
            "source_items": compact(
                task.get("source_items"),
                ("source_id", "source_name", "source_type", "accession", "file_type", "status"),
                30,
            ),
            "dataset_profile": {
                "name": (task.get("modeling_dataset") or {}).get("name"),
                "row_count": (task.get("modeling_dataset") or {}).get("row_count"),
                "patient_count": (task.get("modeling_dataset") or {}).get("patient_count"),
                "sample_count": (task.get("modeling_dataset") or {}).get("sample_count"),
                "columns": [
                    item.get("name")
                    for item in (task.get("modeling_dataset") or {}).get("columns", [])[:100]
                    if isinstance(item, dict)
                ],
            },
            "readiness": task.get("readiness"),
            "summary_zh": str(task.get("summary_zh") or "")[:4000],
        }
        system = (
            "你是独立的科研检索质量评审员。只根据给出的科研问题、检索计划、来源和数据摘要评分，"
            "不要补充外部事实，不要评价医学治疗方案。必须只输出 JSON 对象，字段为："
            "faithfulness、relevance、completeness、retrieval_quality、overall、claim_support_rate、"
            "missing_evidence、unsupported_claims。四个 score 为 1 到 5 的整数，overall 为 1 到 5，"
            "claim_support_rate 为 0 到 1 的数字；每个维度包含 score 和简短 reason。"
        )
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "temperature": 0,
                "enable_thinking": False,
                "max_tokens": 1200,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        return self._normalize(json.loads(self._strip_fence(content)))

    @staticmethod
    def _strip_fence(content: str) -> str:
        match = re.search(r"```(?:json)?\s*(.*?)```", str(content), re.S | re.I)
        return match.group(1).strip() if match else str(content).strip()

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        def numeric(value: Any, default: float) -> float:
            if isinstance(value, dict):
                value = value.get("score", value.get("value", value.get("rate", default)))
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        result: dict[str, Any] = {}
        for key in ("faithfulness", "relevance", "completeness", "retrieval_quality"):
            item = payload.get(key) or {}
            score = max(1, min(5, int(numeric(item, 1))))
            reason = item.get("reason") if isinstance(item, dict) else None
            result[key] = {"score": score, "reason": str(reason or "未提供理由")[:1000]}
        result["overall"] = max(1, min(5, int(numeric(payload.get("overall"), 1))))
        result["claim_support_rate"] = max(
            0.0,
            min(1.0, numeric(payload.get("claim_support_rate"), 0.0)),
        )
        def as_list(value: Any) -> list[Any]:
            if value is None:
                return []
            return [value] if isinstance(value, str) else list(value)

        result["missing_evidence"] = [str(item)[:500] for item in as_list(payload.get("missing_evidence"))][:20]
        result["unsupported_claims"] = [str(item)[:500] for item in as_list(payload.get("unsupported_claims"))][:20]
        return result

    def close(self) -> None:
        if self._owns_client:
            self.client.close()


def evaluate_task(case: EvaluationCase, task: dict[str, Any], latency_ms: float, judge: QwenJudge | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "case_id": case.case_id,
        "difficulty": case.difficulty,
        "query": case.question,
        "expected_sources": list(case.expected_sources),
        "rank": source_rank(task, case.expected_sources),
        "latency_ms": latency_ms,
        "task_id": task.get("task_id"),
    }
    if judge is not None:
        try:
            row["judge_scores"] = judge.evaluate(case, task)
        except Exception as exc:
            row["judge_error"] = f"{type(exc).__name__}: {exc}"
            row["judge_scores"] = {}
    else:
        row["judge_scores"] = {}
    return row


def summarize(rows: list[dict[str, Any]], *, judge_model: str | None) -> dict[str, Any]:
    # Keep repeated runs independent. A plain case_id key would silently retain
    # only the final repeat and make the reported mean depend on loop order.
    run_ids = [f"{row['case_id']}:{row.get('repeat', index)}" for index, row in enumerate(rows, 1)]
    ranks = {run_id: row.get("rank") for run_id, row in zip(run_ids, rows)}
    difficulties = {
        run_id: row.get("difficulty", "medium") for run_id, row in zip(run_ids, rows)
    }
    metrics = retrieval_metrics(ranks, difficulties)
    metrics["avg_latency_ms"] = sum(float(row.get("latency_ms", 0)) for row in rows) / max(1, len(rows))
    valid = [row for row in rows if row.get("judge_scores", {}).get("overall") is not None]
    metrics["judge_valid_rate"] = len(valid) / max(1, len(rows))
    for key in ("faithfulness", "relevance", "completeness", "retrieval_quality"):
        scores = [row["judge_scores"][key]["score"] for row in valid if key in row["judge_scores"]]
        metrics[f"avg_{key}"] = sum(scores) / len(scores) if scores else None
    metrics["avg_overall"] = sum(row["judge_scores"]["overall"] for row in valid) / len(valid) if valid else None
    metrics["avg_claim_support_rate"] = (
        sum(row["judge_scores"].get("claim_support_rate", 0) for row in valid) / len(valid) if valid else None
    )
    return {
        "cases": len(rows),
        "judge_model": judge_model,
        "metrics": metrics,
    }


def write_reports(output_dir: Path, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = summarize(rows, judge_model=metadata.get("judge_model"))
    payload = {"metadata": metadata, "summary": summaries, "details": rows}
    (output_dir / "comparison.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["case_id", "difficulty", "rank", "latency_ms", "task_id", "judge_error"]
    with (output_dir / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    metrics = summaries["metrics"]
    columns = [
        "metric", "value",
    ]
    lines = [
        "# 乳腺癌科研 Agent 检索评测",
        "",
        f"- Gold Set：`{metadata.get('benchmark')}`",
        f"- 评测病例：{len(rows)}",
        f"- 生成模型：`{metadata.get('generation_model', '未记录')}`",
        f"- 千问评审模型：`{metadata.get('judge_model', '未运行')}`",
        f"- 评测状态：`{metadata.get('judge_status', 'unknown')}`",
        "",
        "| " + " | ".join(columns) + " |",
        "| --- | ---: |",
    ]
    for key in (
        "recall@1", "recall@3", "recall@5", "mrr@3", "ndcg@3", "avg_latency_ms",
        "avg_faithfulness", "avg_relevance", "avg_completeness", "avg_retrieval_quality",
        "avg_overall", "avg_claim_support_rate", "judge_valid_rate",
    ):
        value = metrics.get(key)
        lines.append(f"| {key} | {'—' if value is None else f'{float(value):.4f}'} |")
    lines.extend([
        "",
        "## 解释",
        "",
        "Recall/MRR/nDCG 依赖人工审核的 expected_sources；千问评分只评审检索证据和数据摘要，不替代 Gold Set。",
        "评测结果不能解释为临床有效性或治疗建议。",
    ])
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
