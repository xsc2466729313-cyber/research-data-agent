"""Create an auditable end-to-end variant matrix without inventing model scores."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _revision() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def run(output_root: Path) -> Path:
    config_path = PROJECT_ROOT / "configs" / "evaluation_system_v2.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    variants = config["model_comparison"]["compare_variants"]
    created = datetime.now(timezone.utc)
    run_dir = output_root / created.strftime("%Y%m%dT%H%M%SZ_variant_matrix")
    run_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for variant in variants:
        rows.append({
            "variant_id": variant["id"],
            "label": variant["label"],
            "qwen_enabled": bool(variant["qwen_enabled"]),
            "multi_source": bool(variant["multi_source"]),
            "quality_gate": bool(variant["quality_gate"]),
            "adaptive_fitness": bool(variant["adaptive_fitness"]),
            "status": "NOT_EVALUATED",
            "metrics": {},
            "quality_gate_result": "REVIEW",
            "note": "需要同一冻结 Evaluation Contract、同一数据版本、真实模型运行和冻结 Gold Set；本次只登记对照配置。",
        })
    payload = {
        "evaluation_id": run_dir.name,
        "evaluation_version": "end_to_end_variant_matrix_v1",
        "layer": "frozen_goldset_sdti",
        "status": "NOT_EVALUATED",
        "code_revision": _revision(),
        "created_at": created.isoformat(),
        "controls": config["model_comparison"]["required_controls"],
        "variants": rows,
        "limitations": [
            "This artifact registers the exact comparison matrix only; it does not claim a model or system score.",
            "Run after an independently reviewed breast-cancer Gold Set and frozen Evaluation Contract are available.",
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "REPORT.md").write_text("# End-to-End Variant Matrix\n\n状态：`NOT_EVALUATED`。本产物仅冻结五个对照配置和共同控制条件；没有 Gold Set、真实模型运行和 Contract 时不填任何成绩。\n", encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "variant_matrix" / "runs")
    args = parser.parse_args()
    print(run(args.output_root))


if __name__ == "__main__":
    main()
