from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_entity import ENTITY_DATASETS, run_public_entity_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public DeepMatcher entity matching benchmarks.")
    parser.add_argument("--dataset", action="append", choices=sorted(ENTITY_DATASETS))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "entity")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    for dataset_id in args.dataset or sorted(ENTITY_DATASETS):
        print(run_public_entity_benchmark(project_root=PROJECT_ROOT, dataset_id=dataset_id, data_root=args.data_root, output_root=args.output_root, download=args.download))


if __name__ == "__main__":
    main()
