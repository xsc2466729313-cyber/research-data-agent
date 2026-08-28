"""Run a reproducible Phase F quality-pipeline smoke evaluation.

This is an operational diagnostic, not a Gold Set benchmark. It reports observed
detector and safety behavior and never labels those counts as accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.quality_v2 import QualityReviewRequest, QualityV2Service
from backend.app.quality_v2.models import QualityRecord


def _fixture_records() -> list[QualityRecord]:
    base = {"study_id": "fixture-study", "disease": "breast cancer", "source_id": "fixture:phase-f", "raw_field": "drug", "raw_value": "Herceptin", "confidence": 0.98, "drug": "Herceptin"}
    her2 = dict(base, raw_field="HER2_IHC", raw_value="2+", her2_assay="IHC", her2_raw_value="2+", her2_status="Positive")
    missing = dict(base)
    missing.pop("source_id")
    return [QualityRecord(record_id="safe-alias", record=base), QualityRecord(record_id="unsafe-her2", record=her2), QualityRecord(record_id="missing-provenance", record=missing)]


def run(output_root: Path) -> Path:
    started = datetime.now(timezone.utc)
    result = QualityV2Service().review(QualityReviewRequest(task_id="phase-f-diagnostic", records=_fixture_records(), recommended_fields=["drug"]))
    payload = {"phase": "F", "pipeline": "quality_v2", "evaluation_status": "DIAGNOSTIC_ONLY", "gold_set": {"used": False, "reason": "No frozen breast-cancer error Gold Set was supplied."}, "run_at": started.isoformat(), "summary": {"record_count": result.detection.checked_record_count, "finding_count": len(result.detection.findings), "safe_candidate_count": result.candidates.summary["safe_candidate_count"], "applied_count": result.applied.applied_count, "review_queue_count": len(result.review_queue), "readiness_status": result.readiness.status, "safety_gate": result.safety_gate.value, "high_risk_auto_repairs": result.candidates.summary["high_risk_auto_repairs"]}, "limitations": ["Counts describe this fixed diagnostic fixture only; Detection F1 and Repair Accuracy are NOT_EVALUATED.", "A frozen, independently reviewed breast-cancer error Gold Set is required for formal metrics."]}
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / started.strftime("%Y%m%dT%H%M%SZ_quality_v2")
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report = "# Quality V2 Phase F Diagnostic\n\n" + "- Evaluation status: `DIAGNOSTIC_ONLY`\n" + f"- Readiness: `{result.readiness.status}`\n" + f"- Safety gate: `{result.safety_gate.value}`\n" + f"- Findings: `{len(result.detection.findings)}`; applied safe repairs: `{result.applied.applied_count}`; review queue: `{len(result.review_queue)}`\n\nDetection F1 and Repair Accuracy remain `NOT_EVALUATED` because no frozen Gold Set was used."
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "public_benchmarks" / "runs")
    args = parser.parse_args()
    print(run(args.output_root))


if __name__ == "__main__":
    main()
