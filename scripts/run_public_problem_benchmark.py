from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_problem_understanding import run_public_problem_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the public EBM-NLP PICO span benchmark.")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "problem")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    print(run_public_problem_benchmark(
        project_root=PROJECT_ROOT,
        data_root=args.data_root,
        output_root=args.output_root,
        download=args.download,
    ))


if __name__ == "__main__":
    main()
