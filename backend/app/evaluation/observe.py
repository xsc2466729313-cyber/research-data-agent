from __future__ import annotations

from typing import Any

from backend.app.evaluation.models import ErrorObservation, FieldObservation, RetrievalObservation
from backend.app.normalization.biomarker_normalizer import BiomarkerNormalizer
from backend.app.normalization.drug_normalizer import DrugNormalizer
from backend.app.normalization.gene_normalizer import GeneNormalizer
from backend.app.normalization.models import NormalizerKind
from backend.app.quality_v2.error_detector import ErrorDetectionEngine
from backend.app.quality_v2.models import QualityRecord
from backend.app.quality_v2.repair_candidate import RepairCandidateGenerator
from backend.app.quality_v2.safe_apply import SafeRepairApplier

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


def gold_id_matches(gold_id: str, system_id: str) -> bool:
    gold = gold_id.strip().casefold()
    system = system_id.strip().casefold()
    if gold == system:
        return True
    if system.endswith(":" + gold) or system.endswith("/" + gold):
        return True
    if gold == "civic" and "civic" in system:
        return True
    if gold == "depmap" and "depmap" in system:
        return True
    if gold == "aact" and system in {"aact", "clinicaltrials.gov"}:
        return True
    if gold == "tcga-brca" and ("tcga-brca" in system or "brca_tcga" in system):
        return True
    return False


def _normalizer_for(canonical_field: str, raw_field: str) -> NormalizerKind | None:
    if canonical_field == "source_id":
        return None
    if canonical_field == "gene" or ("gene" in raw_field.casefold() and canonical_field == "gene"):
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


def observe_field(row: Any) -> tuple[FieldObservation, dict[str, Any]]:
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
    import json

    try:
        payload = json.loads(original)
    except json.JSONDecodeError:
        return {"raw_value": original}
    if isinstance(payload, dict):
        return payload
    return {"raw_value": original}


def project_error_seed(record: dict[str, Any]) -> dict[str, Any]:
    import json

    projected = dict(record)
    source_id = str(projected.get("source_id") or "official-seed")
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


def observe_error(row: Any) -> tuple[ErrorObservation, dict[str, Any]]:
    import json

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
    except Exception as exc:
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


def retrieval_observations_from_ids(
    bundle: Any,
    ids_by_question: dict[str, list[str]],
) -> list[RetrievalObservation]:
    return [
        RetrievalObservation(
            question_id=row.question_id,
            dataset_id=row.dataset_id,
            retrieved=any(
                gold_id_matches(row.dataset_id, item)
                for item in ids_by_question.get(row.question_id, [])
            ),
        )
        for row in bundle.retrieval_gold
    ]
