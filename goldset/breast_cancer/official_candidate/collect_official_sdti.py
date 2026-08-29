"""Run official-candidate SDTI from goldset/templates.

Does not copy development observations. Not frozen_test.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.official_run import run_official_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", choices=("planner", "agent"), default="planner")
    parser.add_argument("--use-qwen", action="store_true")
    parser.add_argument("--evaluation-id", default="")
    args = parser.parse_args()
    result = run_official_evaluation(
        evaluation_id=args.evaluation_id or None,
        retrieval=args.retrieval,
        use_qwen=args.use_qwen,
    )
    summary = {
        "evaluation_id": result.evaluation_id,
        "evaluation_status": result.evaluation_status.value,
        "gold_set_id": result.gold_set.gold_set_id if result.gold_set else None,
        "sdti": result.metrics.sdti.value,
        "retrieval_f1": result.metrics.retrieval_f1.value,
        "faithfulness": result.metrics.faithfulness.value,
        "traceability": result.metrics.traceability.value,
        "error_f1": result.metrics.error_f1.value,
        "repair_accuracy": result.metrics.repair_accuracy.value,
        "publish_allowed": result.safety.publish_allowed,
        "notice": result.notice,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
