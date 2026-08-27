from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.evaluation.public_schema import SCHEMA_DATASETS, run_public_schema_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public Valentine schema matching benchmarks.")
    parser.add_argument("--dataset", action="append", choices=sorted(SCHEMA_DATASETS))
    parser.add_argument("--method", action="append", choices=["exact_normalized_name", "token_jaccard", "project_schema_rule_v1", "project_schema_profile_v2"])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "schema")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    for dataset_id in args.dataset or sorted(SCHEMA_DATASETS):
        print(run_public_schema_benchmark(
            project_root=PROJECT_ROOT,
            dataset_id=dataset_id,
            data_root=args.data_root,
            output_root=args.output_root,
            methods=args.method or ("exact_normalized_name", "token_jaccard", "project_schema_rule_v1", "project_schema_profile_v2"),
            download=args.download,
        ))


if __name__ == "__main__":
    main()
