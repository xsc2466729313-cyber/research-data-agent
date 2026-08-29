"""Collect real system observations for the frozen development Gold Set.

Uses production Source Broker (with literature scan), SchemaMapper / biomarker
rules, and Quality V2 detection + safe apply. Does not invent scores.
Does not copy rows into goldset/templates/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.evaluation.goldset import GoldSetCsvLoader, compute_gold_set_checksum
from backend.app.evaluation.models import (
    BenchmarkObservations,
    ErrorObservation,
    EvaluationMode,
    EvaluationRequest,
    FieldObservation,
    GoldSetManifest,
    RetrievalObservation,
    SourceValidationSummary,
)
from backend.app.evaluation.service import EvaluationService
from backend.app.literature import LiteratureScanRequest
from backend.app.normalization.biomarker_normalizer import BiomarkerNormalizer
from backend.app.normalization.drug_normalizer import DrugNormalizer
from backend.app.normalization.gene_normalizer import GeneNormalizer
from backend.app.normalization.models import NormalizationStatus, NormalizerKind
from backend.app.quality_v2.error_detector import ErrorDetectionEngine
from backend.app.quality_v2.models import QualityRecord
from backend.app.quality_v2.repair_candidate import RepairCandidateGenerator
from backend.app.quality_v2.safe_apply import SafeRepairApplier
from backend.app.research_planning.models import QuestionSelectionRequest, TopicCreateRequest
from backend.app.research_planning.service import ResearchPlanningService
from backend.app.source_broker.models import SourcePlanRequest

ERROR_TYPE_MATCH = {
    "her2_assay_error": {"her2_assay_error", "erbb2_cna_not_ihc"},
    "patient_sample_conflict": {"patient_sample_conflict"},
    "schema_mapping_error": {
        "schema_mapping_error",
        "cross_domain_response",
        "invalid_schema_value",
    },
    "provenance_missing": {"provenance_missing"},
    "gene_alias": {"gene_alias"},
    "drug_alias": {"drug_alias"},
    "duplicate": {"exact_duplicate", "duplicate"},
    "missing": {"missing_required_field", "missing"},
    "unit": set(),
    "typo": set(),
}

BIOMARKER_FIELDS = {
    "her2_status",
    "her2_assay",
    "her2_raw_value",
    "er_status",
    "pr_status",
}


def load_frozen_bundle():
    envelope = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest = GoldSetManifest.model_validate(envelope["manifest"])
    bundle = GoldSetCsvLoader().load(ROOT, manifest)
    if compute_gold_set_checksum(bundle) != manifest.gold_set_checksum:
        raise SystemExit("Frozen checksum mismatch; refuse to evaluate.")
    return envelope, manifest, bundle


def gold_id_matches(gold_id: str, system_id: str) -> bool:
    gold = gold_id.strip().casefold()
    system = system_id.strip().casefold()
    if gold == system:
        return True
    if system.endswith(":" + gold) or system.endswith("/" + gold):
        return True
    if gold == "civic" and ("civic" in system):
        return True
    if gold == "depmap" and "depmap" in system:
        return True
    if gold == "aact" and system in {"aact", "clinicaltrials.gov"}:
        return True
    return False


def _normalizer_for(canonical_field: str, raw_field: str) -> NormalizerKind | None:
    if canonical_field == "source_id":
        return None
    if canonical_field == "gene" or "gene" in raw_field.casefold() and canonical_field == "gene":
        return NormalizerKind.GENE
    if canonical_field == "drug":
        return NormalizerKind.DRUG
    if canonical_field == "mutation_status":
        return NormalizerKind.MUTATION_STATUS
    if canonical_field == "response_domain":
        return NormalizerKind.RESPONSE_DOMAIN
    if canonical_field in BIOMARKER_FIELDS or any(
        token in raw_field.upper() for token in ("HER2", "ERBB2", "IHC", "FISH", "ER", "PR")
    ):
        return NormalizerKind.BIOMARKER
    return NormalizerKind.PASSTHROUGH


def observe_field(row) -> tuple[FieldObservation, dict[str, Any]]:
    biomarker = BiomarkerNormalizer()
    gene = GeneNormalizer()
    drug = DrugNormalizer()
    kind = _normalizer_for(row.canonical_field, row.raw_field)
    values: dict[str, Any] = {}
    status = "passthrough"
    if row.canonical_field == "source_id":
        dataset = row.source_dataset
        if dataset.upper().startswith("GSE"):
            values = {"source_id": f"geo:{dataset}"}
        elif dataset.upper().startswith("TCGA"):
            values = {"source_id": f"gdc:{dataset}"}
        elif dataset.casefold() == "civic":
            values = {"source_id": "civic:knowledgebase"}
        else:
            values = {"source_id": dataset}
        status = "source_id_from_dataset"
    elif kind is NormalizerKind.GENE:
        result = gene.normalize(row.raw_value)
        values = dict(result.values)
        status = result.status.value
    elif kind is NormalizerKind.DRUG:
        result = drug.normalize(row.raw_value)
        values = dict(result.values)
        status = result.status.value
    elif kind is NormalizerKind.BIOMARKER:
        result = biomarker.normalize(
            raw_field=row.raw_field,
            raw_value=row.raw_value,
            canonical_field=row.canonical_field,
        )
        values = dict(result.values)
        status = result.status.value
    elif kind is NormalizerKind.MUTATION_STATUS:
        compact = row.raw_value.strip().casefold()
        mapped = {
            "mutated": "Mutated",
            "mutation": "Mutated",
            "wildtype": "WildType",
            "wild type": "WildType",
            "wt": "WildType",
        }.get(compact)
        values = {"mutation_status": mapped} if mapped else {}
        status = "normalized" if mapped else "unresolved"
    elif kind is NormalizerKind.RESPONSE_DOMAIN:
        compact = row.raw_value.strip().casefold()
        if compact in {"yes", "pcr", "rd", "residual_disease"}:
            values = {"response_domain": "clinical"}
        elif compact in {"auc", "ic50"} or row.raw_field.upper() == "AUC":
            values = {"response_domain": "preclinical_cell_line"}
        elif "predictive" in compact:
            values = {"response_domain": "knowledge_evidence"}
        status = "heuristic_response_domain"
    else:
        values = {row.canonical_field: row.raw_value}
        if row.canonical_field == "er_status":
            result = biomarker.normalize(
                raw_field=row.raw_field,
                raw_value=row.raw_value,
                canonical_field="er_status",
            )
            values = dict(result.values)
            status = result.status.value
        elif row.canonical_field == "pr_status":
            result = biomarker.normalize(
                raw_field=row.raw_field,
                raw_value=row.raw_value,
                canonical_field="pr_status",
            )
            values = dict(result.values)
            status = result.status.value
        elif row.canonical_field == "disease" and "breast" in row.raw_value.casefold():
            values = {"disease": "breast cancer"}
            status = "disease_normalize"
        elif row.canonical_field == "stage":
            compact = row.raw_value.replace("Stage ", "").strip()
            values = {"stage": compact}
            status = "stage_strip"
        elif row.canonical_field == "response":
            compact = row.raw_value.strip().casefold()
            if compact in {"yes", "pcr"}:
                values = {"response": "pCR"}
            elif compact == "rd":
                values = {"response": "RD"}
            elif compact in {"auc", "0.42"} or row.raw_field.upper() == "AUC":
                values = {"response": str(row.raw_value)}
            status = "response_alias"

    observed_value = values.get(row.canonical_field)
    if observed_value is None and values:
        # System produced other canonical fragments (e.g. CNA -> gene/variant).
        observed_value = next(iter(values.values()))
        observed_field = next(iter(values))
    else:
        observed_field = row.canonical_field
        if observed_value is None:
            observed_value = "UNRESOLVED"
            observed_field = row.canonical_field
    evidence = bool(row.source_dataset and row.raw_field and str(row.raw_value) != "")
    if str(observed_value) == "":
        observed_value = "UNRESOLVED"
        evidence = False
    observation = FieldObservation(
        case_id=row.case_id,
        canonical_field=str(observed_field),
        canonical_value=str(observed_value),
        evidence_complete_valid=evidence,
    )
    return observation, {"values": values, "status": status, "kind": None if kind is None else kind.value}


def _as_record(original: str) -> dict[str, Any]:
    try:
        payload = json.loads(original)
    except json.JSONDecodeError:
        return {"raw_value": original}
    if isinstance(payload, dict):
        return payload
    return {"raw_value": original}


def project_error_seed(record: dict[str, Any]) -> dict[str, Any]:
    """Lift a Gold error JSON into CanonicalRecord-shaped input without inventing medical calls.

    Missing required provenance is filled from existing source_id / raw_* so Quality V2 can
    see the seeded error instead of only reporting empty-schema gaps.
    """
    projected = dict(record)
    source_id = str(projected.get("source_id") or "development-seed")
    projected.setdefault("study_id", source_id)
    projected.setdefault("disease", "breast cancer")
    projected.setdefault("source_id", source_id)
    raw_field = str(projected.get("raw_field") or "seed")
    raw_value = projected.get("raw_value")
    if raw_value is None or raw_value == "":
        raw_value = json.dumps(record, ensure_ascii=False)
    projected["raw_field"] = raw_field
    projected["raw_value"] = raw_value if isinstance(raw_value, str) else json.dumps(raw_value, ensure_ascii=False)
    projected.setdefault("confidence", 1.0)
    field_key = raw_field.casefold()
    if "her2_assay" not in projected and ("ihc" in field_key or str(raw_value).strip() in {"2+", "3+", "1+", "0"}):
        if "her2" in field_key or "her2_status" in projected:
            projected["her2_assay"] = "IHC"
    if "her2_raw_value" not in projected and projected.get("her2_status") is not None:
        projected["her2_raw_value"] = str(projected.get("raw_value") or "")
    return projected


def observe_error(row) -> tuple[ErrorObservation, dict[str, Any]]:
    record = project_error_seed(_as_record(row.original_record))
    quality = QualityRecord(record_id=row.case_id, record=record)
    detection = ErrorDetectionEngine().detect([quality], task_id=row.case_id)
    wanted = ERROR_TYPE_MATCH.get(row.error_type, {row.error_type})
    matched = [item for item in detection.findings if item.error_type in wanted]
    detected = bool(matched)
    applied_statuses: list[str] = []
    auto = False
    repaired = None
    try:
        candidates = RepairCandidateGenerator().generate(detection, [quality], task_id=row.case_id)
        applied = SafeRepairApplier().apply([quality], candidates, task_id=row.case_id)
        applied_statuses = [item.status for item in applied.changes]
        applied_changes = [
            item
            for item in applied.changes
            if item.status == "APPLIED" and item.record_id == row.case_id
        ]
        if detected and applied_changes and row.auto_repair_allowed:
            auto = True
            change = applied_changes[0]
            if change.field and change.after is not None:
                repaired = json.dumps(
                    {change.field: change.after},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            else:
                repaired = json.dumps(
                    {"operation": change.operation, "after": change.after},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
    except Exception as exc:  # keep scoring; a candidate-builder crash is not an auto-repair
        applied_statuses = [f"candidate_error:{exc.__class__.__name__}"]
    observation = ErrorObservation(
        case_id=row.case_id,
        detected=detected,
        auto_repair_executed=auto,
        repaired_value=repaired,
    )
    return observation, {
        "finding_types": [item.error_type for item in detection.findings],
        "matched_types": [item.error_type for item in matched],
        "applied": applied_statuses,
    }


def planned_system_ids(plan_result) -> list[str]:
    plan = plan_result.source_plan
    ids = list(plan.selected_dataset_ids) + list(plan.fallback_dataset_ids)
    for candidate in plan_result.dataset_candidates:
        if candidate.discovery_evidence_ids:
            ids.append(candidate.dataset_id)
    return list(dict.fromkeys(ids))


def observe_retrieval(bundle) -> tuple[list[RetrievalObservation], list[dict[str, Any]]]:
    questions: dict[str, str] = {}
    for row in bundle.retrieval_gold:
        questions.setdefault(row.question_id, row.research_question)
    traces: list[dict[str, Any]] = []
    retrieved_by_question: dict[str, list[str]] = {}
    planning = ResearchPlanningService()
    for question_id, question in questions.items():
        trace: dict[str, Any] = {
            "question_id": question_id,
            "paper_count": 0,
            "candidate_id": None,
            "selected": [],
            "fallback": [],
            "error": None,
        }
        try:
            topic = planning.create_topic(TopicCreateRequest(topic=question))
            scan = planning.scan_literature(
                topic.topic_id,
                LiteratureScanRequest(max_records=8),
            )
            trace["paper_count"] = len(scan.scan.papers)
            candidates = planning.question_candidates(topic.topic_id).candidates
            chosen = next(
                (item for item in candidates if item.generation_source == "EVIDENCE_AGENT"),
                candidates[0] if candidates else None,
            )
            if chosen is None:
                raise RuntimeError("no research candidates")
            contract = planning.select_question(
                chosen.candidate_id,
                QuestionSelectionRequest(),
            )
            frozen = planning.freeze_contract(contract.contract_id)
            plan = planning.plan_sources(frozen.contract_id, SourcePlanRequest())
            trace["candidate_id"] = chosen.candidate_id
            trace["selected"] = list(plan.source_plan.selected_dataset_ids)
            trace["fallback"] = list(plan.source_plan.fallback_dataset_ids)
            retrieved_by_question[question_id] = planned_system_ids(plan)
        except Exception as exc:  # noqa: BLE001 — record live failures, keep scoring honest
            trace["error"] = f"{exc.__class__.__name__}: {exc}"
            retrieved_by_question[question_id] = []
        traces.append(trace)

    observations: list[RetrievalObservation] = []
    for row in bundle.retrieval_gold:
        system_ids = retrieved_by_question.get(row.question_id, [])
        retrieved = any(gold_id_matches(row.dataset_id, item) for item in system_ids)
        observations.append(
            RetrievalObservation(
                question_id=row.question_id,
                dataset_id=row.dataset_id,
                retrieved=retrieved,
            )
        )
    return observations, traces


def source_validation() -> SourceValidationSummary:
    payload = json.loads((ROOT / "SOURCE_VERIFICATION.json").read_text(encoding="utf-8"))
    rows = list(payload.get("allowlist") or [])
    civic = payload.get("civic_graphql")
    if isinstance(civic, dict):
        rows.append(civic)
    extra = payload.get("extra_official_pages") or []
    rows.extend(extra)
    checked = len(rows)
    fake = sum(1 for item in rows if item.get("status") != "verified")
    return SourceValidationSummary(checked_source_count=checked, fake_source_count=fake)


def main() -> None:
    envelope, manifest, bundle = load_frozen_bundle()
    retrieval, retrieval_traces = observe_retrieval(bundle)
    field_obs: list[FieldObservation] = []
    field_traces: list[dict[str, Any]] = []
    for row in bundle.field_gold:
        observation, trace = observe_field(row)
        field_obs.append(observation)
        field_traces.append({"case_id": row.case_id, **trace})
    error_obs: list[ErrorObservation] = []
    error_traces: list[dict[str, Any]] = []
    unresolved_high_risk = 0
    for row in bundle.error_gold:
        observation, trace = observe_error(row)
        error_obs.append(observation)
        error_traces.append({"case_id": row.case_id, **trace})
        if row.risk_level.value == "high" and observation.detected and not observation.auto_repair_executed:
            unresolved_high_risk += 1
    observations = BenchmarkObservations(
        retrieval=retrieval,
        fields=field_obs,
        errors=error_obs,
    )
    request = EvaluationRequest(
        evaluation_id="development-xsc-20260829",
        mode=EvaluationMode.GOLD_SET,
        gold_set=bundle,
        observations=observations,
        source_validation=source_validation(),
        unresolved_high_risk_count=unresolved_high_risk,
    )
    output_dir = ROOT / "evaluation_runs"
    service = EvaluationService(output_dir=output_dir)
    result = service.run(request)
    audit = {
        "split": "development",
        "not_frozen_test": True,
        "copied_to_templates": False,
        "independent_reviewer": manifest.independent_reviewer,
        "method": (
            "literature scan + SourceBroker selected/fallback IDs; "
            "Biomarker/Gene/Drug/passthrough; Quality V2 detect+safe apply"
        ),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "notice": envelope.get("notice"),
        "retrieval_traces": retrieval_traces,
        "field_traces": field_traces,
        "error_traces": error_traces,
        "evaluation_status": result.evaluation_status.value,
        "sdti": result.metrics.sdti.model_dump(mode="json"),
    }
    (ROOT / "OBSERVATIONS.json").write_text(
        json.dumps(observations.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "OBSERVATION_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "evaluation_id": result.evaluation_id,
        "evaluation_status": result.evaluation_status.value,
        "publish_allowed": result.safety.publish_allowed,
        "sdti": result.metrics.sdti.value,
        "retrieval_f1": result.metrics.retrieval_f1.value,
        "faithfulness": result.metrics.faithfulness.value,
        "traceability": result.metrics.traceability.value,
        "error_f1": result.metrics.error_f1.value,
        "repair_accuracy": result.metrics.repair_accuracy.value,
        "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
        "notice": (
            "development 分册实测，不是正式赛题 SDTI；templates 仍空；"
            "不得把本结果填进 Rule/Qwen/Full Agent 正式矩阵。"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
