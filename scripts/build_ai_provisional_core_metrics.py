"""Build explicitly labelled AI-derived provisional core metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import math


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "evaluation" / "results_deepseek" / "comparison.json"
AI_RESULT = ROOT / "evaluation" / "ai_evaluation_result.json"
CONSENSUS = ROOT / "evaluation" / "goldset_tri_ai_consensus.json"
OUTPUT = ROOT / "evaluation" / "ai_provisional_core_metrics.json"


def main() -> int:
    payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    metrics = (payload.get("summary") or {}).get("metrics") or {}
    ai_result = json.loads(AI_RESULT.read_text(encoding="utf-8")) if AI_RESULT.is_file() else {}
    consensus = json.loads(CONSENSUS.read_text(encoding="utf-8")) if CONSENSUS.is_file() else {}

    def value(key: str) -> float | None:
        raw = metrics.get(key)
        return None if raw is None else float(raw)

    # These are explicitly labelled proxies, not formal Gold Set calculations.
    # The benchmark does not expose a retrieved-set confusion matrix, so rank
    # and the three-model review artifacts are used as transparent development
    # estimates instead of silently presenting official scores.
    recall = value("recall@3") or 0.0
    ranks = [float(row.get("rank")) for row in payload.get("details", []) if row.get("rank")]
    precision = sum(1.0 / rank for rank in ranks) / len(ranks) if ranks else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    agreement = float((ai_result.get("metrics") or {}).get("ai_agreement_rate") or 0.0)
    source_verified = float((ai_result.get("metrics") or {}).get("source_verified_rate") or 0.0)
    review_required = float((ai_result.get("metrics") or {}).get("human_review_required_rate") or 1.0)
    repair = max(0.0, min(1.0, 1.0 - review_required))
    error_f1 = (2 * agreement * source_verified / (agreement + source_verified)) if agreement + source_verified else 0.0
    faithfulness = (value("avg_faithfulness") or 0.0) / 5
    traceability = value("avg_claim_support_rate") or 0.0
    # SDTI is shown on a 0-100 scale; use the five dashboard dimensions.
    sdti_components = [f1, faithfulness, traceability, error_f1, repair]
    sdti = 100 * math.prod(sdti_components) ** (1 / len(sdti_components)) if all(component > 0 for component in sdti_components) else 0.0
    targets = {"retrieval_precision": 0.90, "retrieval_recall": 0.90, "retrieval_f1": 0.90, "faithfulness": 0.95, "traceability": 1.0, "error_precision": 0.90, "error_recall": 0.90, "error_f1": 0.90, "repair_accuracy": 0.90, "sdti": 90.0}
    source_benchmark = "evaluation/results_deepseek/comparison.json"
    source_ai = "evaluation/ai_evaluation_result.json"
    source_consensus = "evaluation/goldset_tri_ai_consensus.json"
    provisional = {
        "retrieval_precision": {
            "value": precision,
            "target": targets["retrieval_precision"],
            "method": "AI proxy: mean reciprocal rank-hit (mean of 1/rank across benchmark cases)",
            "source": [source_benchmark],
        },
        "retrieval_recall": {
            "value": recall,
            "target": targets["retrieval_recall"],
            "method": "AI proxy: DeepSeek benchmark Recall@3",
            "source": [source_benchmark],
        },
        "retrieval_f1": {
            "value": f1,
            "target": targets["retrieval_f1"],
            "method": "AI proxy: harmonic mean of retrieval precision proxy and Recall@3",
            "source": [source_benchmark],
        },
        "faithfulness": {
            "value": faithfulness,
            "target": targets["faithfulness"],
            "method": "AI proxy: DeepSeek Judge average faithfulness score divided by 5",
            "source": [source_benchmark],
        },
        "traceability": {
            "value": traceability,
            "target": targets["traceability"],
            "method": "AI proxy: DeepSeek Judge claim support rate",
            "source": [source_benchmark],
        },
        "error_precision": {"value": agreement, "target": targets["error_precision"], "method": "AI proxy: three-model agreement rate for error/relevance labels", "source": [source_ai, source_consensus]},
        "error_recall": {"value": source_verified, "target": targets["error_recall"], "method": "AI proxy: verified-source coverage used as detected-error coverage", "source": [source_ai, source_consensus]},
        "error_f1": {"value": error_f1, "target": targets["error_f1"], "method": "AI proxy: harmonic mean of agreement and verified-source coverage", "source": [source_ai, source_consensus]},
        "repair_accuracy": {"value": repair, "target": targets["repair_accuracy"], "method": "AI proxy: 1 minus three-model human-review-required rate", "source": [source_ai, source_consensus]},
        "sdti": {"value": sdti, "target": targets["sdti"], "method": "AI proxy: geometric mean of retrieval F1, faithfulness, traceability, error F1 and repair accuracy (0-100)", "source": [source_benchmark, source_ai, source_consensus]},
    }
    result: dict[str, Any] = {
        "status": "AI_PROVISIONAL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": [source_benchmark, source_ai, source_consensus],
        "metrics": provisional,
        "notice": "AI 辅助代理值，仅用于开发查看；不是冻结 Gold Set 正式指标。",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "status": result["status"], "metrics": provisional}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
