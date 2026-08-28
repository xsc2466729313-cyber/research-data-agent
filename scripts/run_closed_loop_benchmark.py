"""Run a real closed-loop task and persist round-by-round feedback metrics.

This is an operational diagnostic artifact, not a formal benchmark score.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow direct execution from the repository root or from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.agent import AgentTaskRequest, ClosedLoopRequest, ClosedLoopService, ResearchAgentService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded Agent self-correction loop")
    parser.add_argument("--question", default="研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系")
    parser.add_argument("--data-mode", choices=["plan_only", "live"], default="plan_only")
    parser.add_argument("--max-iterations", type=int, default=2)
    parser.add_argument("--use-qwen", action="store_true", help="Use the configured Qwen model for both research rounds")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    request = AgentTaskRequest(
        question=args.question,
        use_qwen=args.use_qwen,
        data_mode=args.data_mode,
        iterative_collection=False,
        max_sources=8,
        max_records=10_000,
    )
    response = ClosedLoopService(ResearchAgentService()).run(
        ClosedLoopRequest(
            initial_request=request,
            max_iterations=args.max_iterations,
            require_two_rounds=True,
        )
    )
    artifact = {
        "artifact_type": "closed_loop_operational_run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formal_score_notice": "本产物仅记录任务内反馈指标，不是正式 benchmark、Repair Accuracy 或 SDTI。",
        "planner_mode": "configured_qwen" if args.use_qwen else "deterministic",
        **response.model_dump(mode="json"),
    }
    output = args.output or Path("evaluation") / "closed_loop" / f"{response.loop_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "loop_id": response.loop_id,
        "status": response.status,
        "completed_iterations": response.completed_iterations,
        "stop_reason": response.stop_reason,
        "output": str(output),
        "improvement_summary": response.improvement_summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
