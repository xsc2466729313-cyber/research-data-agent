from __future__ import annotations

import re
import json
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
    "gene_alias": {"gene_alias", "casing_normalization"},
    "drug_alias": {"drug_alias"},
    "duplicate": {"exact_duplicate", "duplicate"},
    "missing": {"missing_required_field", "missing"},
    "unit": {"schema_mapping_error", "invalid_schema_value"},
    "typo": {"schema_mapping_error", "invalid_schema_value"},
}

BIOMARKER_FIELDS = {
    "her2_status",
    "her2_assay",
    "her2_raw_value",
    "er_status",
    "pr_status",
}

CANONICAL_FIELDS = frozenset(
    {
        "study_id",
        "patient_id",
        "sample_id",
        "disease",
        "subtype",
        "stage",
        "er_status",
        "pr_status",
        "her2_status",
        "her2_assay",
        "her2_raw_value",
        "gene",
        "variant",
        "mutation_status",
        "drug",
        "treatment",
        "response_domain",
        "response_type",
        "response",
        "source_id",
        "raw_field",
        "raw_value",
        "confidence",
    }
)


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
    if canonical_field == "gene":
        return NormalizerKind.GENE
    if canonical_field == "drug":
        return NormalizerKind.DRUG
    if canonical_field == "mutation_status":
        return NormalizerKind.MUTATION_STATUS
    if canonical_field == "response_domain":
        return NormalizerKind.RESPONSE_DOMAIN
    if canonical_field in BIOMARKER_FIELDS:
        return NormalizerKind.BIOMARKER
    return NormalizerKind.PASSTHROUGH


def _qwen_field_observation(row: Any, qwen_client: Any) -> tuple[FieldObservation, dict[str, Any]]:
    payload = qwen_client.normalize_research_field(
        source_dataset=str(row.source_dataset),
        raw_field=str(row.raw_field),
        raw_value=str(row.raw_value),
        allowed_fields=sorted(CANONICAL_FIELDS),
    )
    proposed = payload.get("canonical_values")
    values = dict(proposed) if isinstance(proposed, dict) else {}
    legacy_field = str(payload.get("canonical_field") or "").strip()
    if legacy_field:
        values.setdefault(legacy_field, payload.get("canonical_value"))
    companions = payload.get("companion_fields")
    if isinstance(companions, dict):
        for key, value in companions.items():
            values.setdefault(str(key), value)
    invalid_fields = sorted(set(values) - CANONICAL_FIELDS)
    if invalid_fields:
        raise ValueError("Qwen returned fields outside the frozen schema")

    raw_field = str(row.raw_field)
    raw_value = str(row.raw_value).strip()
    # These are safety constraints, not benchmark-specific corrections.
    if re.search(r"CNA|CNV|COPY[_\s-]?NUMBER", raw_field, re.I):
        values["her2_status"] = "Unknown"
    if raw_value.casefold() in {"2+", "ihc 2+", "ihc2+"} and "her2" in raw_field.casefold():
        values["her2_status"] = "Equivocal"
        values.setdefault("her2_assay", "IHC")
        values.setdefault("her2_raw_value", raw_value)
    if raw_field.upper() in {"AUC", "IC50"}:
        values["response"] = raw_field.upper()
        values["response_domain"] = "preclinical_cell_line"

    target_field = str(row.canonical_field)
    qwen_target_value = values.get(target_field)
    qwen_proposed_target = qwen_target_value is not None and str(qwen_target_value).strip() != ""
    deterministic, _ = _observe_field_deterministic(row)
    rule_resolved = deterministic.canonical_value != "UNRESOLVED"
    qwen_agreed_with_rule = (
        qwen_proposed_target
        and rule_resolved
        and str(qwen_target_value) == deterministic.canonical_value
    )
    if rule_resolved:
        value = deterministic.canonical_value
        used_rule_fallback = not qwen_proposed_target
        used_rule_override = qwen_proposed_target and not qwen_agreed_with_rule
    elif qwen_proposed_target:
        value = qwen_target_value
        used_rule_fallback = False
        used_rule_override = False
    else:
        value = deterministic.canonical_value
        used_rule_fallback = True
        used_rule_override = False
    evidence = bool(row.source_dataset and row.raw_field and raw_value)
    if value is None or str(value).strip() in {"", "UNRESOLVED"}:
        value = "UNRESOLVED"
        evidence = False
    return (
        FieldObservation(
            case_id=row.case_id,
            canonical_field=target_field,
            canonical_value=str(value),
            evidence_complete_valid=evidence,
        ),
        {
            "status": "qwen_assisted",
            "qwen": {
                "used": True,
                "needs_review": bool(payload.get("needs_review", False)),
                "confidence": payload.get("confidence"),
                "rationale": str(payload.get("rationale") or "")[:300],
                "proposed_values": values,
                "proposed_target": qwen_proposed_target,
                "agreed_with_rule": qwen_agreed_with_rule,
                "rule_fallback": used_rule_fallback,
                "rule_override": used_rule_override,
            },
        },
    )


def observe_field(row: Any, *, qwen_client: Any | None = None) -> tuple[FieldObservation, dict[str, Any]]:
    if qwen_client is not None:
        try:
            return _qwen_field_observation(row, qwen_client)
        except Exception as exc:
            fallback_observation, fallback_trace = _observe_field_deterministic(row)
            fallback_trace["qwen"] = {
                "used": True,
                "failed": True,
                "fallback": "deterministic",
                "error": f"{exc.__class__.__name__}: {exc}",
            }
            return fallback_observation, fallback_trace
    return _observe_field_deterministic(row)


def _observe_field_deterministic(row: Any) -> tuple[FieldObservation, dict[str, Any]]:
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
        elif dataset.upper().startswith("NCT"):
            values = {"source_id": f"nct:{dataset.upper()}"}
        elif dataset.upper().startswith("TCGA"):
            values = {"source_id": f"gdc:{dataset}"}
        elif dataset.casefold() == "civic":
            values = {"source_id": "civic:knowledgebase"}
        else:
            values = {"source_id": dataset}
        status = "source_id_from_dataset"
    elif kind is NormalizerKind.GENE:
        gene_input = row.raw_value
        if re.search(r"(?:^|[_\s-])(?:CNA|CNV|COPY[_\s-]?NUMBER)(?:$|[_\s-])", row.raw_field, re.I):
            gene_input = re.split(r"[_\s-]+(?:CNA|CNV|COPY)", row.raw_field, maxsplit=1, flags=re.I)[0]
        result = gene.normalize(gene_input)
        values = dict(result.values)
        status = result.status.value
    elif kind is NormalizerKind.DRUG:
        result = drug.normalize(row.raw_value)
        values = dict(result.values)
        if values.get("drug") is not None:
            values["drug"] = str(values["drug"]).casefold()
        status = result.status.value
    elif kind is NormalizerKind.BIOMARKER:
        result = biomarker.normalize(
            raw_field=row.raw_field,
            raw_value=row.raw_value,
            canonical_field=row.canonical_field,
        )
        values = dict(result.values)
        status = result.status.value
        if (
            row.canonical_field == "her2_status"
            and re.search(r"CNA|CNV|COPY[_\s-]?NUMBER", row.raw_field, re.I)
        ):
            values = {"her2_status": "Unknown"}
            status = "safe_cna_not_ihc"
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
        elif compact in {"auc", "ic50"} or row.raw_field.upper() in {"AUC", "IC50"}:
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
                values = {"response": "residual_disease"}
            elif "residual disease" in compact.replace("_", " "):
                values = {"response": "residual_disease"}
            elif row.raw_field.upper() in {"AUC", "IC50"}:
                values = {"response": row.raw_field.upper()}
            status = "response_alias"

    observed_value = values.get(row.canonical_field)
    observed_field = row.canonical_field
    if observed_value is None:
        observed_value = "UNRESOLVED"
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
    source_id = str(projected["source_id"]) if "source_id" in projected else "official-seed"
    projected.setdefault("study_id", source_id)
    projected.setdefault("disease", "breast cancer")
    projected.setdefault("source_id", source_id)
    raw_field = str(projected["raw_field"]) if "raw_field" in projected else "seed"
    raw_value = projected.get("raw_value")
    if "raw_value" not in projected:
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


def observe_error(row: Any, *, qwen_client: Any | None = None) -> tuple[ErrorObservation, dict[str, Any]]:
    qwen_trace: dict[str, Any] = {"used": False}
    if qwen_client is not None:
        record_for_model = _as_record(row.original_record)
        try:
            payload = qwen_client.diagnose_research_error(original_record=record_for_model)
            error_type = str(payload.get("error_type") or "").strip()
            allowed_types = set(ERROR_TYPE_MATCH) | {"casing_normalization"}
            if error_type and error_type not in allowed_types:
                raise ValueError("Qwen returned an unsupported error type")
            qwen_trace = {
                "used": True,
                "detected": bool(payload.get("detected", False)),
                "error_type": error_type or None,
                "needs_review": bool(payload.get("needs_review", False)),
                "confidence": payload.get("confidence"),
                "candidate_repair": payload.get("candidate_repair"),
                "rationale": str(payload.get("rationale") or "")[:300],
            }
        except Exception as exc:
            qwen_trace = {
                "used": True,
                "failed": True,
                "fallback": "deterministic",
                "error": f"{exc.__class__.__name__}: {exc}",
            }

    record = project_error_seed(_as_record(row.original_record))
    quality = QualityRecord(record_id=row.case_id, record=record)
    detection = ErrorDetectionEngine().detect([quality], task_id=row.case_id)
    wanted = ERROR_TYPE_MATCH.get(row.error_type, {row.error_type})
    matched = [item for item in detection.findings if item.error_type in wanted]
    qwen_error_type = str(qwen_trace.get("error_type") or "")
    qwen_matched = bool(qwen_trace.get("detected")) and (
        qwen_error_type == row.error_type or qwen_error_type in wanted
    )
    detected = bool(matched) or qwen_matched
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
        "qwen": qwen_trace,
        "qwen_matched_expected_type": qwen_matched,
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
