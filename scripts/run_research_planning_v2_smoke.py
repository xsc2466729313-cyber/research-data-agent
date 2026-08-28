"""Run a Phase C contract smoke check.

This is an integration smoke artifact, not a scientific accuracy benchmark.
It uses an explicitly synthetic local fixture and never reports a model score.
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

from backend.app.literature.models import PaperRecord
from backend.app.research_planning_v2 import ResearchPlanningV2Request, ResearchPlanningV2Service


def fixture() -> PaperRecord:
    return PaperRecord(
        paper_id="fixture:phase-c:001",
        source_id="fixture:phase-c",
        provider="local_regression_fixture",
        title="Fixture breast cancer HER2 PIK3CA neoadjuvant response",
        source_url="https://example.invalid/local-regression-fixture",
        abstract="Synthetic fixture only; not an external publication.",
        sections={"methods": "PIK3CA mutation, HER2 status and pathological complete response were recorded after neoadjuvant treatment."},
    )


def run(output_root: Path) -> Path:
    service = ResearchPlanningV2Service()
    cases = [
        ResearchPlanningV2Request(topic="乳腺癌 PIK3CA 新辅助治疗 pCR", retrieved_papers=[fixture()]),
        ResearchPlanningV2Request(topic="乳腺癌新辅助治疗"),
    ]
    results = [service.plan(case) for case in cases]
    checks = {
        "cases": len(results),
        "evidence_case_source": results[0].question_generation_source,
        "fallback_case_source": results[1].question_generation_source,
        "evidence_pack_items": len(results[0].evidence_pack),
        "fallback_pack_items": len(results[1].evidence_pack),
        "required_fields_with_reason": all(bool(item.reason) for item in results[0].required_fields),
        "source_id_preserved": all(bool(item.source_id) for item in results[0].evidence_pack),
        "raw_value_preserved": all(bool(item.raw_value) for item in results[0].evidence_pack),
        "qwen_calls": sum(int(result.audit.get("qwen_invocation_count", 0)) for result in results),
    }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_phase_c")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "evaluation_id": run_id,
        "evaluation_version": "research-agent-v2-phase-c-smoke",
        "layer": "research_planning",
        "stage": "integration_smoke",
        "fixture_notice": "Synthetic local fixture; no external accuracy score is reported. Evidence IDs are deterministic; candidate IDs are per-run identifiers.",
        "checks": checks,
        "results": [result.model_dump(mode="json") for result in results],
    }
    (run_dir / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Research Agent V2 Phase C smoke report",
        "",
        "> Integration contract checks only. This is not a scientific benchmark or SDTI score.",
        "",
        f"- Cases: {checks['cases']}",
        f"- Evidence case source: `{checks['evidence_case_source']}`",
        f"- Fallback case source: `{checks['fallback_case_source']}`",
        f"- Evidence Pack items: {checks['evidence_pack_items']}",
        f"- Required fields include reasons: `{checks['required_fields_with_reason']}`",
        f"- Source/raw provenance preserved: `{checks['source_id_preserved'] and checks['raw_value_preserved']}`",
        f"- Qwen invocations: `{checks['qwen_calls']}` (deterministic implementation; no Qwen call made)",
        "",
        "Limitations: the fixture is synthetic; runtime data-source verification, real Qwen extraction and domain Gold Set evaluation are not covered.",
    ]
    (run_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "evaluation" / "research_planning_v2" / "runs")
    args = parser.parse_args()
    print(run(args.output_root))


if __name__ == "__main__":
    main()
