from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_retrieval import BEIR_DATASETS, run_public_retrieval_benchmark


def main() -> None:
    project_root = PROJECT_ROOT
    parser = argparse.ArgumentParser(description="Run reproducible public BEIR retrieval benchmarks.")
    parser.add_argument("--dataset", action="append", choices=sorted(BEIR_DATASETS), help="Repeat to run multiple datasets.")
    parser.add_argument(
        "--method",
        action="append",
        choices=["bm25", "project_bm25_tuned_v2", "project_hybrid"],
        help="Repeat to run multiple methods.",
    )
    parser.add_argument("--download", action="store_true", help="Download missing official BEIR archives.")
    parser.add_argument("--data-root", type=Path, default=project_root / "data" / "benchmarks" / "beir")
    parser.add_argument("--output-root", type=Path, default=project_root / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    datasets = args.dataset or ["beir_scifact", "beir_nfcorpus"]
    methods = args.method or ["bm25", "project_bm25_tuned_v2", "project_hybrid"]
    for dataset_id in datasets:
        run_dir = run_public_retrieval_benchmark(
            project_root=project_root,
            dataset_id=dataset_id,
            data_root=args.data_root,
            output_root=args.output_root,
            methods=methods,
            download=args.download,
        )
        print(run_dir)


if __name__ == "__main__":
    main()
