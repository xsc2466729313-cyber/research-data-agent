# Quality V2 Phase F

Phase F splits quality work into three independently observable stages:

1. `ErrorDetectionEngine.detect_errors()` detects frozen-schema, provenance, normalization, identity and medical-rule findings.
2. `RepairCandidateGenerator.generate_repair_candidates()` turns only detector evidence into auditable candidates. A candidate is not an executed repair.
3. `SafeRepairApplier.apply_safe_repairs()` executes only low-risk, deterministic, allowlisted top-level replacements and exact duplicate quarantine. It preserves `raw_field`, `raw_value`, and `source_id`, records before/after values, and re-runs detection.

`ReadinessEvaluator` reports six hard gates (`required_fields`, `outcome_validity`, `granularity_match`, `provenance_completeness`, `join_safety`, `critical_medical_rules`) plus soft indicators for sample size, missingness, recommended field coverage, source authority, traceability and review burden. The resulting state is `READY`, `READY_WITH_REVIEW`, or `NOT_READY`.

## API

- `POST /api/v2/quality/detect`
- `POST /api/v2/quality/candidates`
- `POST /api/v2/quality/apply`
- `POST /api/v2/quality/review`

The review endpoint composes all stages and returns a review queue. High-risk fields (`HER2`, `ER/PR`, response, patient/sample identity, survival and critical provenance) are never automatically modified. Missing evidence and invalid required values fail closed.

## Evaluation status

`scripts/run_quality_v2_benchmark.py` creates `run.json` and `REPORT.md` under `evaluation/public_benchmarks/runs/`. The supplied fixture is an operational diagnostic only. Detection F1 and Repair Accuracy stay `NOT_EVALUATED` until an independently reviewed, frozen breast-cancer error Gold Set is available.
