from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.qwen_client import QwenClient, QwenSettings
from backend.app.evaluation.public_qwen_matching import run_qwen_entity, run_qwen_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real Qwen on public schema/entity matching tasks.")
    parser.add_argument("--layer", choices=["schema", "entity"], required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    client = QwenClient(QwenSettings.from_env())
    if not client.available:
        raise SystemExit("Qwen API is not configured; set DASHSCOPE_API_KEY in the local environment.")
    if args.layer == "schema":
        from backend.app.evaluation.public_schema import SCHEMA_DATASETS
        if args.dataset not in SCHEMA_DATASETS:
            raise SystemExit(f"unknown schema dataset: {args.dataset}")
        run_dir = run_qwen_schema(project_root=PROJECT_ROOT, dataset_id=args.dataset, data_root=PROJECT_ROOT / "data" / "benchmarks" / "schema", output_root=args.output_root, client=client)
    else:
        from backend.app.evaluation.public_entity import ENTITY_DATASETS
        if args.dataset not in ENTITY_DATASETS:
            raise SystemExit(f"unknown entity dataset: {args.dataset}")
        run_dir = run_qwen_entity(project_root=PROJECT_ROOT, dataset_id=args.dataset, data_root=PROJECT_ROOT / "data" / "benchmarks" / "entity", output_root=args.output_root, client=client, batch_size=max(1, args.batch_size))
    print(run_dir)


if __name__ == "__main__":
    main()
